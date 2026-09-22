# -*- coding: utf-8 -*-
"""
LLM 客户端测试（httpx MockTransport，无真实网络）。

覆盖目标：
1. 未配置 → 全部方法返回 None（可插拔降级）
2. 正常返回 / JSON 围栏解析 / 非法输出丢弃
3. 网络故障 → 重试后静默降级，绝不抛异常穿透
4. 系统提示词安全硬约束存在性
"""

from __future__ import annotations

import httpx
import pytest

from app.common.constants import RiskLevel
from app.core.llm import client as llm_module
from app.core.llm.client import LlmClient, _extract_json, _SYSTEM_PROMPT


class FakeSettings:
    """测试用配置替身（替换 client 模块内的 settings 绑定）。"""

    llm_base_url = "http://mock-llm/v1"
    llm_api_key = "test-key"
    llm_model = "test-model"
    llm_timeout_seconds = 1.0
    llm_enabled = True


def _client_with(handler) -> LlmClient:
    """构造注入 MockTransport 的客户端并启用测试配置。"""
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return LlmClient(http_client=http)


@pytest.fixture()
def enable_llm(monkeypatch):
    """将 client 模块的 settings 替换为测试替身。"""
    monkeypatch.setattr(llm_module, "settings", FakeSettings())


def _ok_handler(content: str):
    """返回固定内容的 200 响应处理器。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


class TestAvailability:
    """可插拔语义。"""

    def test_not_configured_returns_none(self):
        """未配置 LLM（默认测试环境）→ complete 返回 None，不发起请求。"""
        # 使用真实 settings：测试环境无 LLM 配置
        assert LlmClient().complete("你好") is None

    def test_system_prompt_has_safety_constraints(self):
        """系统提示词必须包含安全硬约束（热线 12356 与方法禁令）。"""
        assert "12356" in _SYSTEM_PROMPT
        assert "严禁" in _SYSTEM_PROMPT


class TestChatCompletion:
    """对话回复生成。"""

    def test_success(self, enable_llm):
        client = _client_with(_ok_handler("听起来你最近不容易，愿意多说说吗？"))
        assert client.complete("我有点累") == "听起来你最近不容易，愿意多说说吗？"

    def test_non_200_returns_none(self, enable_llm):
        """非 200 响应 → None（不抛异常）。"""
        client = _client_with(lambda req: httpx.Response(500))
        assert client.complete("我有点累") is None

    def test_network_error_degrades(self, enable_llm):
        """持续网络错误 → 重试耗尽后返回 None（绝不抛穿透）。"""

        def broken(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = _client_with(broken)
        assert client.complete("我有点累") is None

    def test_malformed_response_degrades(self, enable_llm):
        """响应结构异常（缺 choices）→ None。"""
        client = _client_with(lambda req: httpx.Response(200, json={"unexpected": 1}))
        assert client.complete("我有点累") is None


class TestRiskAssessment:
    """LLM 风险评级。"""

    def test_plain_json(self, enable_llm):
        client = _client_with(_ok_handler('{"level": 2}'))
        assert client.assess_risk("文本") == RiskLevel.L2_HIGH_RISK

    def test_json_in_code_fence(self, enable_llm):
        """容忍 ```json 围栏包裹。"""
        client = _client_with(_ok_handler('```json\n{"level": 3}\n```'))
        assert client.assess_risk("文本") == RiskLevel.L3_CRISIS

    def test_out_of_range_level(self, enable_llm):
        """越界等级（9）→ None（视为无贡献）。"""
        client = _client_with(_ok_handler('{"level": 9}'))
        assert client.assess_risk("文本") is None

    def test_garbage_output(self, enable_llm):
        """非 JSON 输出 → None。"""
        client = _client_with(_ok_handler("我觉得这个人有点难过"))
        assert client.assess_risk("文本") is None


class TestEmotionClassification:
    """LLM 情绪分类。"""

    def test_success(self, enable_llm):
        content = '{"category": "焦虑", "intensity": 0.8, "confidence": 0.9}'
        client = _client_with(_ok_handler(content))
        result = client.classify_emotion("文本")
        assert result is not None
        assert result.category == "焦虑"
        assert result.intensity == pytest.approx(0.8)

    def test_invalid_numeric_values(self, enable_llm):
        """数值字段非法 → None（fail-safe）。"""
        content = '{"category": "焦虑", "intensity": "高", "confidence": 0.9}'
        client = _client_with(_ok_handler(content))
        assert client.classify_emotion("文本") is None


class TestJsonExtraction:
    """JSON 提取工具函数。"""

    def test_extract_plain(self):
        assert _extract_json('{"level": 1}') == {"level": 1}

    def test_extract_with_noise(self):
        assert _extract_json('好的，结果如下：{"level": 1} 请查收') == {"level": 1}

    def test_extract_failure(self):
        assert _extract_json("完全没有 JSON") is None
        assert _extract_json("{broken") is None
