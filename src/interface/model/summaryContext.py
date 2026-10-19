from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SummaryContext:
    '''AI 智能总结的注入数据上下文。

    聚合一次分析的四类注入数据：分析策略（可能已维度重构）、中间数据、
    修正因子与汇总结果；商品链接作为不同对话记录的唯一识别码。
    '''

    goodsUrl: str = ''
    goodsName: str = ''
    recordId: int | None = None
    strategySnapshot: dict[str, Any] = field(default_factory=dict)
    refactored: bool = False
    intermediateData: list[dict[str, Any]] = field(default_factory=list)
    correctionFactor: float | None = None
    finalScore: float = 0.0
    dimensionAverages: dict[str, Any] = field(default_factory=dict)
    dimensionWeightedScores: dict[str, Any] = field(default_factory=dict)
    totalCommentCount: int = 0
    validCommentCount: int = 0
    credibilityThreshold: float = 0.0
    trimPercent: float = 0.0

    @property
    def hasData(self) -> bool:
        '''是否包含任何可用于注入的分析数据。'''
        return bool(self.strategySnapshot or self.intermediateData or self.finalScore)
