from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Dimension:
    '''分析策略中的单个维度项。'''

    name: str
    description: str
    weight: float
    emphasized: bool

    def toDict(self) -> dict[str, Any]:
        '''序列化为可写入 JSON 的字典。

        Returns:
            dict[str, Any]: 维度项的字典表示。
        '''
        return {
            'name': self.name,
            'description': self.description,
            'weight': self.weight,
            'emphasized': self.emphasized,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> Dimension:
        '''从字典反序列化维度项。

        Args:
            data: 形如 {'name': ..., 'description': ..., 'weight': ...,
                'emphasized': ...} 的字典。

        Returns:
            Dimension: 反序列化后的维度项。

        Raises:
            ValueError: 数据缺少必需键或权重无法转为浮点数时抛出。
        '''
        try:
            return cls(
                name=str(data['name']),
                description=str(data['description']),
                weight=float(data['weight']),
                emphasized=bool(data['emphasized']),
            )
        except KeyError as error:
            msg = f'维度数据缺少必需键：{error}'
            raise ValueError(msg) from error
        except (TypeError, ValueError) as error:
            msg = f'维度权重无法解析：{error}'
            raise ValueError(msg) from error


@dataclass(slots=True)
class AnalysisStrategy:
    '''商品分析策略（维度集合 + 评分/置信度提示词）。'''

    strategyId: str
    name: str
    dimensions: list[Dimension] = field(default_factory=list)
    ratingPrompt: str = ''
    credibilityPrompt: str = ''
    source: str = 'user'

    sourceNames: ClassVar[dict[str, str]] = {'default': '默认', 'user': '自建'}

    def totalWeight(self) -> float:
        '''返回全部维度的权重之和。

        Returns:
            float: 权重总和。
        '''
        return sum(dimension.weight for dimension in self.dimensions)

    def normalized(self) -> AnalysisStrategy:
        '''返回权重归一化后的策略副本。

        权重总和为 0 或无维度时原样返回副本。

        Returns:
            AnalysisStrategy: 权重之和为 1 的新策略实例。
        '''
        total = self.totalWeight()
        if total <= 0:
            logger.warning('策略 %s 权重总和为 %s，跳过归一化', self.strategyId, total)
            return AnalysisStrategy(
                strategyId=self.strategyId,
                name=self.name,
                dimensions=list(self.dimensions),
                ratingPrompt=self.ratingPrompt,
                credibilityPrompt=self.credibilityPrompt,
                source=self.source,
            )
        dimensions = [
            Dimension(
                name=dimension.name,
                description=dimension.description,
                weight=dimension.weight / total,
                emphasized=dimension.emphasized,
            )
            for dimension in self.dimensions
        ]
        return AnalysisStrategy(
            strategyId=self.strategyId,
            name=self.name,
            dimensions=dimensions,
            ratingPrompt=self.ratingPrompt,
            credibilityPrompt=self.credibilityPrompt,
            source=self.source,
        )

    def refactored(self) -> AnalysisStrategy:
        '''维度重构：仅保留强调维度并归一化权重。

        评论数不足时调用；若不存在任何强调维度则退化为全维度
        归一化（并记录警告）。

        Returns:
            AnalysisStrategy: 重构后的新策略实例。
        '''
        emphasizedDimensions = [dimension for dimension in self.dimensions if dimension.emphasized]
        if not emphasizedDimensions:
            logger.warning('策略 %s 不含强调维度，维度重构退化为全维度归一化', self.strategyId)
            emphasizedDimensions = list(self.dimensions)
        total = sum(dimension.weight for dimension in emphasizedDimensions)
        if total <= 0:
            total = 1.0
        dimensions = [
            Dimension(
                name=dimension.name,
                description=dimension.description,
                weight=dimension.weight / total,
                emphasized=True,
            )
            for dimension in emphasizedDimensions
        ]
        return AnalysisStrategy(
            strategyId=self.strategyId,
            name=self.name,
            dimensions=dimensions,
            ratingPrompt=self.ratingPrompt,
            credibilityPrompt=self.credibilityPrompt,
            source=self.source,
        )

    def weightMap(self) -> dict[str, float]:
        '''返回维度名到权重的映射。

        Returns:
            dict[str, float]: {维度名: 权重} 映射。
        '''
        return {dimension.name: dimension.weight for dimension in self.dimensions}

    def toDict(self) -> dict[str, Any]:
        '''序列化为可写入 JSON 的字典。

        Returns:
            dict[str, Any]: 策略的字典表示。
        '''
        return {
            'strategyId': self.strategyId,
            'name': self.name,
            'dimensions': [dimension.toDict() for dimension in self.dimensions],
            'ratingPrompt': self.ratingPrompt,
            'credibilityPrompt': self.credibilityPrompt,
            'source': self.source,
        }

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> AnalysisStrategy:
        '''从字典反序列化策略。

        Args:
            data: 策略字典，dimensions 为维度字典列表。

        Returns:
            AnalysisStrategy: 反序列化后的策略实例。

        Raises:
            ValueError: 缺少必需键或维度数据非法时抛出。
        '''
        try:
            dimensions = [Dimension.fromDict(item) for item in data['dimensions']]
        except KeyError as error:
            msg = f'策略数据缺少必需键：{error}'
            raise ValueError(msg) from error
        weights = [dimension.weight for dimension in dimensions]
        if any(weight < 0 for weight in weights):
            msg = '策略存在负权重维度'
            raise ValueError(msg)
        return cls(
            strategyId=str(data.get('strategyId', '')),
            name=str(data.get('name', '')),
            dimensions=dimensions,
            ratingPrompt=str(data.get('ratingPrompt', '')),
            credibilityPrompt=str(data.get('credibilityPrompt', '')),
            source=str(data.get('source', 'user')),
        )

    def validate(self) -> list[str]:
        '''校验策略完整性，返回错误信息列表。

        Returns:
            list[str]: 错误信息列表，为空表示校验通过。
        '''
        errors: list[str] = []
        if not self.strategyId:
            errors.append('缺少策略 ID')
        if not self.name:
            errors.append('缺少策略名称')
        if not self.dimensions:
            errors.append('至少需要一个维度')
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            errors.append('维度名称存在重复')
        if self.totalWeight() <= 0:
            errors.append('维度权重总和必须大于 0')
        if not self.ratingPrompt:
            errors.append('缺少评分提示词')
        if not self.credibilityPrompt:
            errors.append('缺少置信度提示词')
        return errors
