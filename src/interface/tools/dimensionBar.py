from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class DimensionBar(QWidget):
    '''单个维度的得分条目（名称 + 进度条 + 分数）。'''

    def __init__(self, dimensionName: str = '', parent: QWidget | None = None) -> None:
        '''初始化维度条目。

        Args:
            dimensionName: 维度名称。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._nameLabel = QLabel(dimensionName)
        self._nameLabel.setStyleSheet('font-weight: 600;')
        self._scoreLabel = QLabel('--')
        self._scoreLabel.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._scoreLabel.setStyleSheet('font-size: 16px; font-weight: 600;')
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        topLayout = QHBoxLayout()
        topLayout.addWidget(self._nameLabel)
        topLayout.addStretch(1)
        topLayout.addWidget(self._scoreLabel)
        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(4)
        mainLayout.addLayout(topLayout)
        mainLayout.addWidget(self._bar)

    def setValues(self, dimensionName: str, score: float | None, weight: float | None = None) -> None:
        '''更新维度条目数据。

        Args:
            dimensionName: 维度名称。
            score: 维度平均分（None 显示为 --）。
            weight: 维度权重（可选，附加在名称后展示）。
        '''
        title = dimensionName if weight is None else f'{dimensionName}（权重 {weight:.0%}）'
        self._nameLabel.setText(title)
        if score is None:
            self._scoreLabel.setText('--')
            self._bar.setValue(0)
            return
        clamped = max(0.0, min(100.0, float(score)))
        self._scoreLabel.setText(f'{clamped:.1f}')
        self._bar.setValue(round(clamped))
        color = '#C8E6CD' if clamped >= 80 else ('#F4ECD6' if clamped >= 60 else '#EFD4D4')
        self._bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color}; border-radius: 6px; }}',
        )
