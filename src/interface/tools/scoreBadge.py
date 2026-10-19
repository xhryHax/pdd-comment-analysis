from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

SCORE_GRADES: list[tuple[int, str, str]] = [
    (80, '优', '#C8E6CD'),
    (60, '中', '#F4ECD6'),
    (0, '差', '#EFD4D4'),
]


class ScoreBadge(QLabel):
    '''分数等级徽章（按分数着优/中/差色块）。'''

    def __init__(self, score: float = 0.0, parent=None) -> None:
        '''初始化徽章。

        Args:
            score: 分数（0-100）。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(52, 28)
        self.setScore(score)

    def setScore(self, score: float) -> None:
        '''更新分数并刷新展示。

        Args:
            score: 分数（0-100）。
        '''
        clamped = max(0.0, min(100.0, float(score)))
        for threshold, grade, color in SCORE_GRADES:
            if clamped >= threshold:
                background = color
                text = f'{grade} {clamped:.0f}'
                break
        else:
            background, text = '#EFD4D4', f'差 {clamped:.0f}'
        self.setText(text)
        self.setStyleSheet(
            f'background-color: {background}; color: #101010; border-radius: 14px;'
            ' font-weight: 600; padding: 2px 10px;'
        )
