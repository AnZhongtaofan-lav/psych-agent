# -*- coding: utf-8 -*-
"""
LLM 客户端 —— OpenAI 兼容 /v1/chat/completions 封装。

安全设计：
1. 【可插拔】未配置 LLM_API_KEY/LLM_BASE_URL 时 is_available=False，
   所有方法返回 None，上层引擎自动走纯规则模式（优雅降级）
2. 【超时与重试】连接 3s / 读取可配（默认 15s）；传输错误重试 1 次；
   总失败 → 返回 None（绝不抛异常穿透到业务层）
3. 【提示词安全约束】系统提示词写入硬性条款：
   严禁输出自伤方法/工具/剂量细节；用户询问方法时必须拒绝并转介热线
4. 【JSON 约束输出】风险/情绪评级要求 JSON 返回；
   解析失败 → None（视为"无贡献"，不影响规则结果）
5. 【隐私】发送给 LLM 的文本已经过入口脱敏（交互层保证）；
   本模块不额外记录请求/响应内容到日志

注意：发送给外部 LLM 的内容仍属于"出域数据"，生产部署应在
网关层配置数据出域审计（本模块在注释中预留该合规提示）。
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.common.config import settings
from app.common.constants import RiskLevel
from app.common.logger import get_logger
from app.core.emotion.emotion_engine import LlmEmotion

logger = get_logger(__name__)

# 连接超时（秒）：快速失败，尽快降级
_CONNECT_TIMEOUT = 3.0
# 传输错误重试次数（仅网络层错误；4xx 语义错误不重试）
_MAX_RETRIES = 1

# ------------------------------------------------------------
# 系统提示词 —— 安全硬约束（所有 LLM 调用共享）
# ------------------------------------------------------------
_SYSTEM_PROMPT = (
    "你是一个心理支持助手的底层模型。你必须遵守以下硬性条款，"
    "任何情况下不得违反：\n"
    "1. 严禁输出任何自我伤害、自杀的方法、工具、剂量或步骤细节；\n"
    "2. 用户询问伤害自己的方法时，必须明确拒绝，"
    "并建议其拨打心理援助热线 12356；\n"
    "3. 严禁肯定、鼓励或美化任何伤害自己的行为；\n"
    "4. 不要做出精神疾病诊断，不做药物建议；\n"
    "5. 语气保持温和、共情、不评判。\n"
    "当被要求输出 JSON 时，只输出 JSON 本身，不要附加任何解释。"
)


def _extract_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中稳健提取 JSON 对象。

    容忍三种常见形态：纯 JSON、```json 围栏、前后混杂说明文字。
    解析失败返回 None（调用方视为无贡献）。
    """
    # 去除 markdown 代码围栏
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    # 截取首个 { 到最后一个 } 之间的内容
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class LlmClient:
    """OpenAI 兼容 LLM 客户端（同步）。

    参数:
        http_client: 可注入的 httpx.Client（测试用 MockTransport）；
            None 时按配置惰性创建
    """

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client
        self._read_timeout = settings.llm_timeout_seconds

    # ------------------------------------------------------------
    # 可用性
    # ------------------------------------------------------------
    @property
    def is_available(self) -> bool:
        """LLM 是否可用（配置层面）。未配置时所有方法直接返回 None。"""
        return settings.llm_enabled

    def _get_http(self) -> httpx.Client:
        """获取 HTTP 客户端（惰性创建，复用连接池）。"""
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(self._read_timeout, connect=_CONNECT_TIMEOUT)
            )
        return self._client

    # ------------------------------------------------------------
    # 底层调用
    # ------------------------------------------------------------
    def _chat(self, user_prompt: str, max_tokens: int = 400) -> str | None:
        """执行一次 chat completion；任何失败返回 None（绝不抛出）。

        失败语义：
            - 未配置 → None
            - 网络错误/超时 → 重试 1 次后仍失败 → None
            - 非 2xx → None
            - 响应结构异常 → None
        """
        if not self.is_available:
            return None

        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        url = settings.llm_base_url.rstrip("/") + "/chat/completions"

        # 合规提示（生产部署）：此处为数据出域点，网关层应配置审计
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._get_http().post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.warning(
                        "LLM 返回非 200 状态: status=%d", response.status_code
                    )
                    return None
                content = response.json()["choices"][0]["message"]["content"]
                return content if isinstance(content, str) else None
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                # 网络/结构错误：记警告（不含请求内容），重试或放弃
                logger.warning(
                    "LLM 调用失败（第 %d 次）: %s", attempt + 1, type(exc).__name__
                )
                if attempt >= _MAX_RETRIES:
                    return None
        return None  # 理论不可达（循环内必 return）

    # ------------------------------------------------------------
    # 业务能力 1：共情回复生成（L0/L1 增强模式）
    # ------------------------------------------------------------
    def complete(self, prompt: str) -> str | None:
        """生成对话回复文本；失败返回 None。"""
        return self._chat(prompt, max_tokens=300)

    # ------------------------------------------------------------
    # 业务能力 2：风险评级（max 融合中的 LLM 侧）
    # ------------------------------------------------------------
    def assess_risk(self, text: str) -> RiskLevel | None:
        """LLM 风险评级：返回 0~3 等级；无法评估返回 None。

        安全语义：返回值交给 RiskEngine 做 max 融合，
        LLM 在此只能"升级"风险，没有任何降级通道。
        """
        prompt = (
            "请评估下面这段用户发言的心理危机风险等级，只输出 JSON：\n"
            '{"level": <0到3的整数>}\n'
            "评级标准：0=无风险；1=情绪低落；2=明显绝望或自伤倾向；"
            "3=自杀/自伤意念或提及方法。\n"
            f"用户发言：{text}"
        )
        content = self._chat(prompt, max_tokens=50)
        if content is None:
            return None
        data = _extract_json(content)
        if data is None or "level" not in data:
            return None
        try:
            level = int(data["level"])
        except (TypeError, ValueError):
            return None
        if level not in (0, 1, 2, 3):
            return None
        return RiskLevel(level)

    # ------------------------------------------------------------
    # 业务能力 3：情绪分类（置信度竞争融合的 LLM 侧）
    # ------------------------------------------------------------
    def classify_emotion(self, text: str) -> LlmEmotion | None:
        """LLM 情绪分类；无法评估返回 None。

        类别词表受控：焦虑/抑郁/愤怒/悲伤/平静/中性，
        越界类别由 emotion_engine 校验丢弃。
        """
        prompt = (
            "请分析下面这段用户发言的主要情绪，只输出 JSON：\n"
            '{"category": "<焦虑|抑郁|愤怒|悲伤|平静|中性>", '
            '"intensity": <0到1的小数>, "confidence": <0到1的小数>}\n'
            f"用户发言：{text}"
        )
        content = self._chat(prompt, max_tokens=80)
        if content is None:
            return None
        data = _extract_json(content)
        if data is None:
            return None
        category = data.get("category")
        intensity = data.get("intensity")
        confidence = data.get("confidence")
        if not isinstance(category, str):
            return None
        try:
            return LlmEmotion(
                category=category,
                intensity=float(intensity),      # 非法值抛异常 → 下方捕获
                confidence=float(confidence),
            )
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------
    # 函数句柄导出（供引擎以函数签名注入）
    # ------------------------------------------------------------
    def as_level_fn(self):
        """导出为 RiskEngine 需要的 LlmLevelFn 签名。"""
        return self.assess_risk

    def as_emotion_fn(self):
        """导出为 EmotionEngine 需要的 LlmEmotionFn 签名。"""
        return self.classify_emotion

    def as_complete_fn(self):
        """导出为 ReplyGenerator 需要的 LlmCompleteFn 签名。"""
        return self.complete
