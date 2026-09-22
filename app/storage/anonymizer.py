# -*- coding: utf-8 -*-
"""
PII 脱敏器 —— 全局安全底座（纯函数模块，零外部依赖，可独立测试）。

设计要点：
1. 【默认脱敏】所有用户生成的文本在进入日志/数据库前必须调用 anonymize()
2. 【归一化优先】全角数字、横线分隔号码等变体必须先归一化再匹配
   （例如 １３８００１３８０００、138-0013-8000 都要能识别为手机号）
3. 【保守取舍】疑似 PII 但无法百分百确认时倾向脱敏（宁可误脱敏，不可漏脱敏）
4. 每次成功脱敏返回动作记录（action 类型），供审计模块记录（不含原文）
5. 纯函数设计：无 IO、无全局状态，方便单元测试与多线程复用

掩码格式规范（与设计方案一致）：
    手机号   138****5678           保留前3后4
    身份证   110***********1234    保留前3后4
    银行卡   6222***********1234   保留前4后4
    邮箱     z******@qq.com        保留首字符与域名
    姓名     张伟 → 张**（我叫张**）
    住址     北京市***区***
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ============================================================
# 脱敏动作类型常量（与 audit_log.action 字段对应，会入库）
# ============================================================
ACTION_MASK_PHONE = "mask_phone"          # 手机号
ACTION_MASK_ID_CARD = "mask_id_card"      # 身份证
ACTION_MASK_BANK_CARD = "mask_bank_card"  # 银行卡
ACTION_MASK_EMAIL = "mask_email"          # 邮箱
ACTION_MASK_NAME = "mask_name"            # 姓名
ACTION_MASK_ADDRESS = "mask_address"      # 住址


@dataclass
class AnonymizeReport:
    """一次脱敏操作的报告：记录"做了什么"，绝不记录原文与密文对照。

    属性:
        actions: 本轮触发的脱敏动作类型列表（去重、按处理顺序）
    """

    actions: list[str] = field(default_factory=list)

    def record(self, action: str) -> None:
        """记录一个脱敏动作（去重）。"""
        if action not in self.actions:
            self.actions.append(action)

    @property
    def has_changes(self) -> bool:
        """是否发生了任何脱敏。"""
        return bool(self.actions)


# ============================================================
# 归一化辅助：全角字符 → 半角
# 覆盖场景：全角数字 １３８００１３８０００、全角字母、全角符号
# ============================================================
_FULLWIDTH_OFFSET = 0xFEE0  # Unicode 全角区与半角区的固定偏移量


def _to_halfwidth(text: str) -> str:
    """将全角可见字符转换为半角（NFKC 兼容思路的轻量实现）。

    说明：不直接用 unicodedata.normalize("NFKC") 是因为它会把
    中文特殊符号也做过度变换，此处只转换 ASCII 全角区间，语义更可控。
    """
    out_chars: list[str] = []
    for ch in text:
        code = ord(ch)
        # 全角 ASCII 区（！到～）与全角空格
        if 0xFF01 <= code <= 0xFF5E:
            out_chars.append(chr(code - _FULLWIDTH_OFFSET))
        elif code == 0x3000:  # 全角空格
            out_chars.append(" ")
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def normalize_for_pii(text: str) -> str:
    """PII 匹配前的归一化：全角→半角 + 去除数字间常见分隔符变体。

    注意：此函数仅用于 PII 检测上下文，返回值用于"检测"而非"替换"——
    替换时需要保留原文其余部分，因此在各 _mask_xxx 内部单独处理。
    """
    return _to_halfwidth(text)


# ============================================================
# 各类型正则与掩码实现
# ============================================================

# --- 手机号 ---
# 语义：1 开头，第二位 3-9，共 11 位（3-4-4 分组），前后不能是数字（避免误切长串数字）
# 边界说明：(?<!\d) / (?!\d) 使用环视而非 \b，因为 \b 在中文语境下行为不稳定
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 分隔符变体：138-0013-8000、138 0013 8000（分隔符可选，从而同时覆盖纯数字形态）
# \s 覆盖全角空格（Python str 模式下 \s 含 \u3000）；位数分组 3+4+4 = 11 位
_PHONE_SEP_RE = re.compile(r"(?<!\d)1[3-9]\d[-\s．.]?\d{4}[-\s．.]?\d{4}(?!\d)")


def _mask_phone(text: str, report: AnonymizeReport) -> str:
    """手机号脱敏：138****5678（保留前3后4）。"""

    def _replace(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        report.record(ACTION_MASK_PHONE)
        # digits 恒为 11 位（正则已保证），前3后4掩码
        return f"{digits[:3]}****{digits[-4:]}"

    # 先匹配带分隔符的变体，再匹配纯数字（顺序重要，防止变体被拆散漏检）
    text = _PHONE_SEP_RE.sub(_replace, text)
    text = _PHONE_RE.sub(_replace, text)
    return text


# --- 身份证 ---
# 18 位：6位地址码 + 8位出生日期（1900-2099 约束）+ 3位顺序码 + 校验位(数字/X)
# 15 位旧格式：6位地址码 + 6位出生日期(YYMMDD) + 3位顺序码
_ID_CARD_18_RE = re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_ID_CARD_15_RE = re.compile(r"(?<!\d)[1-9]\d{5}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)")


def _mask_id_card(text: str, report: AnonymizeReport) -> str:
    """身份证脱敏：110***********1234（保留前3后4）。

    注意：必须先处理 18 位再处理 15 位，否则 15 位正则会
    误匹配 18 位号码的前 15 位。
    """

    def _replace(match: re.Match) -> str:
        digits = match.group(0)
        report.record(ACTION_MASK_ID_CARD)
        return f"{digits[:3]}{'*' * (len(digits) - 7)}{digits[-4:]}"

    text = _ID_CARD_18_RE.sub(_replace, text)
    text = _ID_CARD_15_RE.sub(_replace, text)
    return text


# --- 银行卡 ---
# 13~19 位连续数字，需通过 Luhn 校验（避免误伤 QQ 号、订单号等）
_BANK_CARD_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")


def _luhn_valid(digits: str) -> bool:
    """Luhn 算法校验（银行卡号尾位校验位算法）。

    从右往左，奇数位直接累加，偶数位乘2（超过9则减9），总和模10为0则有效。
    """
    total = 0
    parity = 1  # 最右位从奇数位开始
    for ch in reversed(digits):
        d = int(ch)
        if parity % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        parity += 1
    return total % 10 == 0


def _mask_bank_card(text: str, report: AnonymizeReport) -> str:
    """银行卡脱敏：6222***********1234（保留前4后4），仅对通过 Luhn 校验的串生效。

    保守取舍说明：跳过已被身份证正则处理过的串由调用顺序保证
    （身份证先执行，剩余 13-19 位数字串才进入银行卡检测）。
    """

    def _replace(match: re.Match) -> str:
        digits = match.group(0)
        if not _luhn_valid(digits):
            # Luhn 不通过 → 大概率不是银行卡（订单号/QQ号等），不处理
            return digits
        report.record(ACTION_MASK_BANK_CARD)
        return f"{digits[:4]}{'*' * (len(digits) - 8)}{digits[-4:]}"

    return _BANK_CARD_RE.sub(_replace, text)


# --- 邮箱 ---
# RFC 简化版：本地部分 + @ + 域名（域名至少两级，如 qq.com / example.com.cn）
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _mask_email(text: str, report: AnonymizeReport) -> str:
    """邮箱脱敏：z******@qq.com（保留首字符与完整域名）。"""

    def _replace(match: re.Match) -> str:
        email = match.group(0)
        local, _, domain = email.partition("@")
        report.record(ACTION_MASK_EMAIL)
        # 本地部分只保留首字符，其余以 6 个星号代替（固定星号数避免泄露长度）
        return f"{local[0]}******@{domain}"

    return _EMAIL_RE.sub(_replace, text)


# --- 姓名 ---
# 设计：以【常见姓氏表】为锚点，避免 cue 词误伤普通语句
#   反例动机："想找人聊聊"（"找人聊聊"曾被误判为姓名）、"联系方式"（"方式"被误判）
#   正例目标："我叫张伟"、"我是王小明"、"找李雷转告"、"今天王同学没来上课"
# 常见姓氏（百家姓高频 100 个，覆盖绝大多数真实姓名首字）
_COMMON_SURNAMES = (
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林郑谢罗宋唐韩冯于董萧程曹袁邓许傅沈曾彭吕苏"
    "卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史"
    "顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文"
)
_SURNAME_CLASS = f"[{_COMMON_SURNAMES}]"
# 模式一：指示词（我叫/我是/找/联系）+ 姓氏 + 1~2 字名（共 2~3 字）
_NAME_AFTER_CUE_RE = re.compile(rf"(?P<cue>我叫|我是|找|联系)(?P<name>{_SURNAME_CLASS}[\u4e00-\u9fa5]{{1,2}})")
# 模式二：姓氏 + 称谓（同学/老师/医生/经理/教授）
#   (?![们])：排除"同学们"这类复数泛称，仅命中"王同学"式具体指称
_NAME_TITLE_RE = re.compile(rf"(?P<name>{_SURNAME_CLASS})(?P<title>同学|老师|医生|经理|教授)(?![们])")


def _mask_name(text: str, report: AnonymizeReport) -> str:
    """姓名脱敏：我叫张伟 → 我叫张**；王同学 → 王**。

    掩码规范：姓氏后固定跟 2 个星号 —— 不随名字长度变化，
    避免通过星号数量泄露真实姓名的长度信息。

    保守取舍：姓氏锚点法仍可能漏掉罕见姓氏，但心理服务场景下
    "漏脱敏"的代价远高于"误脱敏"，故采用保守策略。
    """

    def _replace_cue(match: re.Match) -> str:
        report.record(ACTION_MASK_NAME)
        name = match.group("name")
        # 保留姓氏（首字），其余固定打 2 星
        return f"{match.group('cue')}{name[0]}**"

    def _replace_title(match: re.Match) -> str:
        report.record(ACTION_MASK_NAME)
        return f"{match.group('name')}**"

    text = _NAME_AFTER_CUE_RE.sub(_replace_cue, text)
    text = _NAME_TITLE_RE.sub(_replace_title, text)
    return text


# --- 住址 ---
# 连缀模式（区县必需，省市可选 —— 覆盖"海淀区中关村大街1号"式无省市地址）：
#   [省市]? + [区县] + [路/街/巷/道/大街] + [N号]?
# 保守说明：要求"区县 + 道路"双锚点，避免"小区路上"这类日常语被误伤
_ADDRESS_RE = re.compile(
    r"(?:[\u4e00-\u9fa5]{1,6}?(?:省|市))?"          # 可选：省或市
    r"[\u4e00-\u9fa5]{1,6}?(?:区|县)"                # 必需：区或县
    r"[\u4e00-\u9fa5]{1,10}?(?:大街|路|街|巷|道)"    # 道路（大街需在街之前）
    r"(?:\d{1,5}号)?"                                # 可选门牌号
)


def _mask_address(text: str, report: AnonymizeReport) -> str:
    """住址脱敏：北京市海淀区中关村大街1号 → 北京市***。

    策略：将"区县及之后"的细节全部替换为 ***，
    保留省市骨架（若原文含省市）；无省市则整体打码。
    """

    def _replace(match: re.Match) -> str:
        report.record(ACTION_MASK_ADDRESS)
        addr = match.group(0)
        # 保留到省/市的部分，其余打 ***
        province_end = -1
        for i, ch in enumerate(addr):
            if ch in ("省", "市"):
                province_end = i
        kept = addr[: province_end + 1] if province_end >= 0 else ""
        return f"{kept}***"

    return _ADDRESS_RE.sub(_replace, text)


# ============================================================
# 对外主入口
# ============================================================

# 处理顺序管道：手机号 → 身份证 → 银行卡 → 邮箱 → 姓名 → 住址
# 顺序依据：
#   1. 身份证必须在银行卡之前（身份证是 17-18 位数字，会被银行卡正则误吞）
#   2. 手机号最先（11 位，环视边界保证不与其他类型冲突）
#   3. 姓名/住址为中文模式，与数字类无冲突，放最后
_PIPELINE: tuple = (
    _mask_phone,
    _mask_id_card,
    _mask_bank_card,
    _mask_email,
    _mask_name,
    _mask_address,
)


def anonymize(text: str) -> tuple[str, AnonymizeReport]:
    """对文本执行全量 PII 脱敏。

    参数:
        text: 原始文本（用户输入、日志字段等）

    返回:
        (脱敏后文本, 脱敏报告)。报告只含动作类型，不含原文。

    使用规范（安全红线）：
        - 交互层中间件：请求/响应/日志字段写出前调用
        - 数据层仓储：所有 INSERT/UPDATE 前调用（防御纵深第二道防线）
    """
    report = AnonymizeReport()
    result = text

    # 归一化无法直接替换原文（会破坏非 PII 内容），
    # 因此先在归一化副本上探测"是否存在全角数字组成的手机号"，
    # 若存在则同样在原文上跑一遍手机号掩码（掩码函数内部已兼容分隔符变体）
    normalized = _to_halfwidth(result)
    if normalized != result and _PHONE_RE.search(normalized):
        # 原文里用全角数字写的手机号：借助归一化文本定位并替换
        result = _mask_fullwidth_phone(result, report)

    for mask_fn in _PIPELINE:
        result = mask_fn(result, report)

    return result, report


def _mask_fullwidth_phone(text: str, report: AnonymizeReport) -> str:
    """处理全角数字手机号：１３８００１３８０００ → 138****0000。

    实现思路：逐字符扫描，将连续的全角数字段临时转半角后用
    手机号正则探测；命中则整段替换为掩码。
    """
    out: list[str] = []
    buffer: list[str] = []  # 当前累积的"全角数字"段

    def _flush() -> None:
        """将累积段转换半角后检测手机号，再写回输出。"""
        if not buffer:
            return
        segment = "".join(buffer)
        half = _to_halfwidth(segment)
        masked, _ = _PHONE_RE.subn(
            lambda m: f"{m.group(0)[:3]}****{m.group(0)[-4:]}", half
        )
        if masked != half:
            report.record(ACTION_MASK_PHONE)
        out.append(masked)
        buffer.clear()

    for ch in text:
        code = ord(ch)
        # 只把"全角数字"（０-９）收入缓冲段，其余字符触发段结束
        if 0xFF10 <= code <= 0xFF19:
            buffer.append(ch)
        else:
            _flush()
            out.append(ch)
    _flush()
    return "".join(out)


def anonymize_strict(text: str) -> str:
    """便捷方法：只返回脱敏后文本，忽略报告。

    适用于调用方不关心审计动作的场合（如日志脱敏）。
    """
    masked, _ = anonymize(text)
    return masked
