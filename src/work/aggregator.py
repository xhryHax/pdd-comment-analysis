from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.work.analysisStrategy import AnalysisStrategy
from src.work.commentScore import CommentScore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AggregateResult:
    '''汇总计算的最终结果。'''

    finalScore: float
    dimensionAverages: dict[str, float | None] = field(default_factory=dict)
    dimensionWeightedScores: dict[str, float | None] = field(default_factory=dict)
    totalCommentCount: int = 0
    validCommentCount: int = 0
    correctionFactor: float | None = None


def filterByCredibility(
    scores: list[CommentScore],
    threshold: float,
) -> list[CommentScore]:
    '''按置信度阈值过滤评论。

    Args:
        scores: 全部中间数据条目。
        threshold: 置信度阈值，低于该值的条目被排除。

    Returns:
        list[CommentScore]: 置信度达标的条目列表。
    '''
    kept = [item for item in scores if item.credibility >= threshold]
    excluded = len(scores) - len(kept)
    logger.info('置信度过滤：%d 条中保留 %d 条（阈值 %.2f，排除 %d 条）', len(scores), len(kept), threshold, excluded)
    return kept


def weightedTotal(
    score: CommentScore,
    weights: dict[str, float],
) -> float | None:
    '''计算单条评论的加权总得分。

    仅对非 None 的维度按权重加权（在已出现的维度上重新归一
    权重），全部维度为 None 时返回 None。

    Args:
        score: 单条评论的打分结果。
        weights: 维度名到权重的映射。

    Returns:
        float | None: 加权总得分，无任何有效维度时返回 None。
    '''
    total = 0.0
    weightSum = 0.0
    for name, weight in weights.items():
        value = score.scores.get(name)
        if value is None:
            continue
        total += value * weight
        weightSum += weight
    if weightSum <= 0:
        return None
    return total / weightSum


def trimExtremes(
    scores: list[CommentScore],
    weights: dict[str, float],
    trimPercent: float,
) -> list[CommentScore]:
    '''按加权总得分的截尾均值方式去除两端极端评论。

    Args:
        scores: 置信度过滤后的条目。
        weights: 维度名到权重的映射。
        trimPercent: 每端截去的百分比（0-50）。

    Returns:
        list[CommentScore]: 去除最高与最低两端各 trimPercent% 后
        的剩余条目（保持原相对顺序）。
    '''
    usable = [item for item in scores if weightedTotal(item, weights) is not None]
    skipped = len(scores) - len(usable)
    if skipped:
        logger.info('截尾前排除无有效维度得分的评论 %d 条', skipped)
    count = len(usable)
    if count == 0:
        return []
    percent = max(0.0, min(50.0, trimPercent))
    trimCount = int(count * percent / 100)
    if trimCount == 0:
        return usable
    ranked = sorted(usable, key=lambda item: (weightedTotal(item, weights) or 0.0))
    trimmed = ranked[trimCount : count - trimCount]
    keptSet = {id(item) for item in trimmed}
    result = [item for item in usable if id(item) in keptSet]
    logger.info('截尾：按加权总得分去除最高/最低两端各 %d 条（%.1f%%），保留 %d 条', trimCount, percent, len(result))
    return result


def aggregate(
    scores: list[CommentScore],
    strategy: AnalysisStrategy,
    correctionFactor: float | None = None,
) -> AggregateResult:
    '''汇总计算最终商品质量分数。

    各维度在有效评论上取均值，按权重求加权得分后求和得到
    最终分数；若提供修正因子则再相乘。

    Args:
        scores: 有效评论的打分结果列表。
        strategy: 当前使用的（已重构/归一化的）策略。
        correctionFactor: 修正因子（0-1），None 表示无修正。

    Returns:
        AggregateResult: 汇总结果。
    '''
    dimensionAverages: dict[str, float | None] = {}
    dimensionWeightedScores: dict[str, float | None] = {}
    weights = strategy.weightMap()
    for dimension in strategy.dimensions:
        values = [
            item.scores[dimension.name]
            for item in scores
            if item.scores.get(dimension.name) is not None
        ]
        average = (sum(values) / len(values)) if values else None
        dimensionAverages[dimension.name] = average
        dimensionWeightedScores[dimension.name] = average * dimension.weight if average is not None else None
    knownValues = [value for value in dimensionWeightedScores.values() if value is not None]
    finalScore = sum(knownValues)
    if finalScore > 100.0:
        finalScore = 100.0
    if correctionFactor is not None:
        finalScore *= correctionFactor
    result = AggregateResult(
        finalScore=round(finalScore, 2),
        dimensionAverages=dimensionAverages,
        dimensionWeightedScores=dimensionWeightedScores,
        totalCommentCount=len(scores),
        validCommentCount=len(scores),
        correctionFactor=correctionFactor,
    )
    logger.info(
        '汇总：有效评论 %d 条，最终分数 %.2f（修正因子 %s）',
        len(scores),
        result.finalScore,
        correctionFactor,
    )
    return result
