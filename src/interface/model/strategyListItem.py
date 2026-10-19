from __future__ import annotations

from dataclasses import dataclass

from src.work.analysisStrategy import AnalysisStrategy


@dataclass(slots=True)
class StrategyListItem:
    '''策略列表展示项（默认策略/自建策略）。'''

    strategy: AnalysisStrategy
    sourceLabel: str
    sourceKind: str
