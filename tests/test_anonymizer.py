# -*- coding: utf-8 -*-
"""
PII 脱敏器单元测试（对应设计方案测试计划 B1~B9）。

测试原则：
- 覆盖全部 PII 类型：手机号/身份证/银行卡/邮箱/姓名/住址
- 覆盖变体绕过：全角数字、横线分隔
- 覆盖误伤防护：非 PII 数字串不脱敏（固定预期）
- 覆盖审计语义：报告只含动作类型，绝不包含原文片段
"""

from __future__ import annotations

from app.storage.anonymizer import anonymize, anonymize_strict

# ============================================================
# B 组用例：各 PII 类型掩码
# ============================================================


class TestPhoneMasking:
    """手机号脱敏（含分隔符与全角变体）。"""

    def test_b1_plain_phone(self):
        """B1: 纯数字手机号 → 138****8000（保留前3后4）。"""
        masked, report = anonymize("我手机 13800138000")
        assert masked == "我手机 138****8000"
        assert report.actions == ["mask_phone"]

    def test_phone_with_dashes(self):
        """变体：横线分隔 138-0013-8000 也能识别。"""
        masked, _ = anonymize("联系方式 138-0013-8000 请回电")
        assert "138-0013-8000" not in masked
        assert "138****8000" in masked

    def test_b7_fullwidth_phone(self):
        """B7: 全角数字手机号 １３８００１３８０００ → 掩码。"""
        masked, report = anonymize("电话１３８００１３８０００")
        # 全角原文必须被替换掉
        assert "１３８００１３８０００" not in masked
        assert "138****8000" in masked
        assert "mask_phone" in report.actions

    def test_phone_inside_long_digits_not_masked_as_phone(self):
        """误伤防护：16 位数字串中的 11 位前缀不按手机号处理（数字边界环视）。"""
        masked, _ = anonymize("订单号 1380013800012345")
        # 不应出现"手机号掩码 + 尾巴"的混合形态（如 138****80001234 之外的断裂）
        assert "138****8000" not in masked


class TestIdCardMasking:
    """身份证脱敏。"""

    def test_b2_id_card_18(self):
        """B2: 18 位身份证 → 110***********7890（保留前3后4，11 星）。"""
        masked, report = anonymize("身份证 110101199003077890")
        assert masked == "身份证 110***********7890"
        assert "mask_id_card" in report.actions

    def test_id_card_15_legacy(self):
        """旧版 15 位身份证也能识别。"""
        masked, report = anonymize("旧证号 110101900307789")
        assert "110101900307789" not in masked
        assert "mask_id_card" in report.actions

    def test_id_card_with_x_suffix(self):
        """校验位为 X 的身份证。"""
        masked, _ = anonymize("身份证 11010119900307789X")
        assert "11010119900307789X" not in masked
        assert masked.startswith("身份证 110")


class TestBankCardMasking:
    """银行卡脱敏（Luhn 校验防误伤）。"""

    def test_b3_luhn_valid_card(self):
        """B3: 通过 Luhn 校验的 16 位卡号 4111111111111111 → 4111********1111。"""
        masked, report = anonymize("卡号 4111111111111111")
        assert masked == "卡号 4111********1111"
        assert "mask_bank_card" in report.actions

    def test_non_card_digits_not_masked(self):
        """误伤防护：Luhn 不通过的普通长数字串（如时间戳拼接）不脱敏。"""
        # 1234567890123 的 Luhn 校验不通过 → 保持原样
        text = "编号 1234567890123"
        masked, report = anonymize(text)
        assert masked == text
        assert report.actions == []


class TestEmailMasking:
    """邮箱脱敏。"""

    def test_b4_email(self):
        """B4: zhangsan@qq.com → z******@qq.com（保留首字符与域名）。"""
        masked, report = anonymize("邮箱 zhangsan@qq.com")
        assert masked == "邮箱 z******@qq.com"
        assert "mask_email" in report.actions


class TestNameMasking:
    """姓名脱敏。"""

    def test_b5_name_with_cue(self):
        """B5: 我叫张伟 → 我叫张**。"""
        masked, report = anonymize("我叫张伟，你叫什么")
        assert masked == "我叫张**，你叫什么"
        assert "mask_name" in report.actions

    def test_three_char_name(self):
        """三字姓名：我是王小明 → 我是王**。"""
        masked, _ = anonymize("我是王小明")
        assert masked == "我是王**"

    def test_title_name(self):
        """称谓模式：王同学 → 王**。"""
        masked, _ = anonymize("今天王同学没来上课")
        assert masked == "今天王**没来上课"


class TestAddressMasking:
    """住址脱敏。"""

    def test_b6_full_address(self):
        """B6: 完整地址 → 保留省市骨架，区级以下打码。"""
        masked, report = anonymize("我家住北京市海淀区中关村大街1号")
        assert "中关村" not in masked
        assert "大街1号" not in masked
        assert "北京市" in masked
        assert "mask_address" in report.actions

    def test_address_without_city(self):
        """无省市前缀的地址（区+路+号）也能识别。"""
        masked, _ = anonymize("我在海淀区中关村大街1号等你")
        assert "中关村" not in masked


class TestCompositeAndSafety:
    """复合场景与安全语义。"""

    def test_multiple_pii_in_one_text(self):
        """一条文本同时含手机号+邮箱+姓名：全部脱敏，报告记录全部动作。"""
        masked, report = anonymize("我叫李雷，手机 13912345678，邮箱 lilei@qq.com")
        assert "139****5678" in masked
        assert "l******@qq.com" in masked
        assert "李**" in masked
        assert set(report.actions) == {"mask_phone", "mask_email", "mask_name"}

    def test_report_never_contains_original(self):
        """审计语义：报告动作列表中绝不出现原文片段。"""
        _, report = anonymize("我手机 13800138000")
        for action in report.actions:
            assert "13800138000" not in action

    def test_clean_text_untouched(self):
        """无 PII 文本保持原样，报告为空。"""
        text = "今天心情不太好，想找人聊聊。"
        masked, report = anonymize(text)
        assert masked == text
        assert report.actions == []

    def test_empty_string(self):
        """空串安全（不抛异常）。"""
        masked, report = anonymize("")
        assert masked == ""
        assert report.actions == []

    def test_convenience_wrapper(self):
        """anonymize_strict 便捷方法返回纯文本。"""
        assert anonymize_strict("手机 13800138000") == "手机 138****8000"
