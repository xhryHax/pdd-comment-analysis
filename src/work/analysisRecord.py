from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnalysisRecord:
    '''一次分析的完整记录（持久化于 SQLite）。'''

    recordId: int | None = None
    goodsName: str = ''
    goodsUrl: str = ''
    strategyId: str = ''
    strategyName: str = ''
    strategySnapshot: dict[str, Any] = field(default_factory=dict)
    totalCommentCount: int = 0
    validCommentCount: int = 0
    credibilityThreshold: float = 0.0
    trimPercent: float = 0.0
    correctionFactor: float | None = None
    finalScore: float = 0.0
    dimensionAverages: dict[str, float | None] = field(default_factory=dict)
    dimensionWeightedScores: dict[str, float | None] = field(default_factory=dict)
    createdAt: str = ''

    def toRow(self) -> dict[str, Any]:
        '''转换为数据库行（嵌套结构序列化为 JSON 文本）。

        Returns:
            dict[str, Any]: 与 user_records 表列对应的字典。
        '''
        return {
            'recordId': self.recordId,
            'goodsName': self.goodsName,
            'goodsUrl': self.goodsUrl,
            'strategyId': self.strategyId,
            'strategyName': self.strategyName,
            'strategySnapshot': json.dumps(self.strategySnapshot, ensure_ascii=False),
            'totalCommentCount': self.totalCommentCount,
            'validCommentCount': self.validCommentCount,
            'credibilityThreshold': self.credibilityThreshold,
            'trimPercent': self.trimPercent,
            'correctionFactor': self.correctionFactor,
            'finalScore': self.finalScore,
            'dimensionAverages': json.dumps(self.dimensionAverages, ensure_ascii=False),
            'dimensionWeightedScores': json.dumps(self.dimensionWeightedScores, ensure_ascii=False),
            'createdAt': self.createdAt,
        }

    @classmethod
    def fromRow(cls, row: dict[str, Any]) -> AnalysisRecord:
        '''从数据库行反序列化记录。

        Args:
            row: 数据库返回的行字典。

        Returns:
            AnalysisRecord: 反序列化后的记录实例。
        '''
        return cls(
            recordId=row.get('recordId'),
            goodsName=row.get('goodsName', ''),
            goodsUrl=row.get('goodsUrl', ''),
            strategyId=row.get('strategyId', ''),
            strategyName=row.get('strategyName', ''),
            strategySnapshot=json.loads(row.get('strategySnapshot') or '{}'),
            totalCommentCount=int(row.get('totalCommentCount', 0)),
            validCommentCount=int(row.get('validCommentCount', 0)),
            credibilityThreshold=float(row.get('credibilityThreshold', 0.0)),
            trimPercent=float(row.get('trimPercent', 0.0)),
            correctionFactor=(
                float(row['correctionFactor']) if row.get('correctionFactor') is not None else None
            ),
            finalScore=float(row.get('finalScore', 0.0)),
            dimensionAverages=json.loads(row.get('dimensionAverages') or '{}'),
            dimensionWeightedScores=json.loads(row.get('dimensionWeightedScores') or '{}'),
            createdAt=row.get('createdAt', ''),
        )
