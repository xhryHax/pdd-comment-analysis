from __future__ import annotations

from dataclasses import dataclass

type ScoreMap = dict[str, int | None]


@dataclass(slots=True)
class CommentScore:
    '''单条评论的 LLM 打分结果（中间数据元素）。'''

    comment: str
    scores: ScoreMap
    credibility: float


def clampScore(value: int | float | None) -> int | None:
    '''将分数截断到 0-100 的整数，非法输入返回 None。

    Args:
        value: LLM 输出的原始分数。

    Returns:
        int | None: 截断后的整数分数，无法解析时返回 None。
    '''
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return max(0, min(100, round(number)))


def clampCredibility(value: float | None) -> float:
    '''将置信度截断到 0-1 的小数，非法输入回落到 0.5。

    Args:
        value: LLM 输出的原始置信度。

    Returns:
        float: 截断后的置信度。
    '''
    if value is None:
        return 0.5
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if number != number:  # NaN
        return 0.5
    return max(0.0, min(1.0, number))
