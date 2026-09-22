# -*- coding: utf-8 -*-
"""
风险规则加载与匹配 —— 数据驱动的四级分级规则表。

设计说明：
1. 规则数据存于 resources/risk_lexicon.json（规则与代码分离，便于
   心理专家在不改代码的前提下维护词典）
2. 所有正则在加载时一次性编译（避免每轮对话重复编译开销）
3. match() 输入必须是【归一化后文本】——调用方（风险引擎）负责先调用
   normalizer.normalize()，本模块不做二次归一化（单一职责）
4. 返回"最高命中等级"与"命中条目标签列表"：
   - 标签格式 "分组:关键词"（如 "自杀意念:不想活"），用于：
     a) 写入 risk_events 审计（是词典标签，非用户原文，无 PII）
     b) 传入对话策略，让回复能针对性回应
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.common.logger import get_logger

logger = get_logger(__name__)

# 词典文件路径：app/core/risk/risk_rules.py → 上两级 → app/resources/
_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "risk_lexicon.json"


@dataclass(frozen=True)
class LexiconEntry:
    """单条风险规则（不可变，加载后只读共享）。

    属性:
        level: 风险等级 1~3
        group: 语义分组（如 "自杀意念"），用于审计与回复策略
        label: 条目标签 "分组:关键词"，用于审计记录
        keyword: 子串匹配词（与 regex 二选一）
        regex: 已编译正则（与 keyword 二选一）
    """

    level: int
    group: str
    label: str
    keyword: str | None = None
    regex: re.Pattern[str] | None = None


@dataclass
class RuleMatchResult:
    """规则匹配结果。

    属性:
        level: 最高命中等级（0~3）
        entries: 命中的条目标签列表（去重，按等级从高到低排列）
    """

    level: int
    entries: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _load_entries() -> tuple[tuple[LexiconEntry, ...], ...]:
    """加载并编译词典（lru_cache 保证全局只加载一次）。

    返回:
        按等级索引的条目元组：index 1 → L1 条目，index 2 → L2，index 3 → L3。
        index 0 为空占位。

    安全语义：
        词典文件缺失/损坏时抛出异常（fail-fast）——风险规则是安全底线，
        静默降级为"无规则"是绝对不可接受的失败模式。
    """
    raw = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    by_level: list[list[LexiconEntry]] = [[], [], [], []]  # 0~3

    for level_str, level_def in raw["levels"].items():
        level = int(level_str)
        if level not in (1, 2, 3):
            # 未知等级：跳过并告警（词典可扩展 L4 等而不破坏旧数据）
            logger.warning("词典中出现未知风险等级，已跳过: level=%s", level_str)
            continue
        for group_def in level_def["groups"]:
            group = group_def["group"]
            # 关键词条目：子串匹配
            for kw in group_def.get("keywords", []):
                by_level[level].append(
                    LexiconEntry(
                        level=level,
                        group=group,
                        label=f"{group}:{kw}",
                        keyword=kw,
                    )
                )
            # 正则条目：加载时编译，编译失败 fail-fast
            for pattern in group_def.get("regexes", []):
                by_level[level].append(
                    LexiconEntry(
                        level=level,
                        group=group,
                        label=f"{group}:/{pattern}/",
                        regex=re.compile(pattern),
                    )
                )

    logger.info(
        "风险词典加载完成: L1=%d L2=%d L3=%d 条",
        len(by_level[1]), len(by_level[2]), len(by_level[3]),
    )
    return tuple(tuple(entries) for entries in by_level)


class RiskRules:
    """风险规则匹配器。"""

    def __init__(self) -> None:
        # 触发一次加载，把 fail-fast 提前到构造期
        self._entries = _load_entries()

    def match(self, normalized_text: str) -> RuleMatchResult:
        """在归一化文本上执行四级规则匹配。

        匹配策略：
            从 L3 向 L1 逐级扫描，一旦某级命中即停止更低级别的扫描
            （我们只关心最高风险级；低级条目对响应策略无贡献）。
            同级内扫描全部条目，收集完整命中标签（供审计与回复策略）。

        参数:
            normalized_text: normalizer.normalize() 的输出

        返回:
            RuleMatchResult(level=0..3, entries=[...])
        """
        matched_labels: list[str] = []
        highest = 0

        # 从最高级 L3 开始向下扫描（找到即不再降级）
        for level in (3, 2, 1):
            for entry in self._entries[level]:
                hit = False
                if entry.keyword is not None:
                    hit = entry.keyword in normalized_text
                elif entry.regex is not None:
                    hit = entry.regex.search(normalized_text) is not None
                if hit:
                    matched_labels.append(entry.label)
                    highest = level  # 循环入口即最高级，直接记录
            # 该级有命中 → 不再扫描更低级
            if highest == level and matched_labels:
                break

        return RuleMatchResult(level=highest, entries=matched_labels)
