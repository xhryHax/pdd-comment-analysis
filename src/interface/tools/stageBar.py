from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.interface.tools.styleLoader import currentTheme

STAGE_LABELS: list[tuple[str, str]] = [
    ('login', '登录'),
    ('crawl', '抓取'),
    ('refactor', '重构'),
    ('score', '打分'),
    ('filter', '判定'),
    ('summarize', '汇总'),
]

# 各主题下环节状态的取色（pending/active 脉动一档/done）
_STAGE_PALETTES: dict[str, dict[str, str]] = {
    'light': {
        'pending': '#E6E6E6',
        'active': '#FF3D8B',
        'activeDim': '#C72B67',
        'done': '#000000',
    },
    'dark': {
        'pending': '#3D3A39',
        'active': '#00D992',
        'activeDim': '#10B981',
        'done': '#00D992',
    },
}


class StageBar(QWidget):
    '''分析流程环节指示条。

    横向展示各环节，当前环节以强调色高亮并带呼吸脉动动画；
    已完成环节以强调色圆点标记。
    '''

    stageReached = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        '''初始化环节指示条。

        Args:
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._currentIndex = -1
        self._phase = 0
        self._dots: dict[str, QLabel] = {}
        self._labels: dict[str, QLabel] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        for index, (stageKey, stageLabel) in enumerate(STAGE_LABELS):
            if index > 0:
                line = QLabel('—')
                line.setProperty('caption', True)
                layout.addWidget(line)
            dot = QLabel('●')
            dot.setMinimumSize(18, 18)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label = QLabel(stageLabel)
            label.setProperty('caption', True)
            layout.addWidget(dot)
            layout.addWidget(label)
            self._dots[stageKey] = dot
            self._labels[stageKey] = label
        self._pulseTimer = QTimer(self)
        self._pulseTimer.setInterval(600)
        self._pulseTimer.timeout.connect(self._onPulse)
        self._setAllState('pending')

    def setStage(self, stageKey: str) -> None:
        '''切换当前环节（之前的环节标记为完成）。

        Args:
            stageKey: 环节键（login/crawl/refactor/score/filter/
                summarize/done）。
        '''
        keys = [key for key, _ in STAGE_LABELS]
        if stageKey == 'done':
            self._currentIndex = len(keys) - 1
            self._setAllState('done')
            self._pulseTimer.stop()
            return
        if stageKey not in keys:
            return
        self._currentIndex = keys.index(stageKey)
        for index, key in enumerate(keys):
            state = 'active' if index == self._currentIndex else ('done' if index < self._currentIndex else 'pending')
            self._setStageState(key, state)
        self._phase = 0
        if not self._pulseTimer.isActive():
            self._pulseTimer.start()
        self.stageReached.emit()

    def reset(self) -> None:
        '''重置为初始（全部待定）状态。'''
        self._currentIndex = -1
        self._pulseTimer.stop()
        self._setAllState('pending')

    def _onPulse(self) -> None:
        '''当前环节的呼吸脉动动画帧。'''
        if self._currentIndex < 0:
            return
        keys = [key for key, _ in STAGE_LABELS]
        activeKey = keys[self._currentIndex]
        self._phase = (self._phase + 1) % 2
        palette = _STAGE_PALETTES.get(currentTheme(), _STAGE_PALETTES['light'])
        color = palette['active'] if self._phase == 0 else palette['activeDim']
        self._dots[activeKey].setStyleSheet(f'color: {color}; font-size: 14px;')
        self._labels[activeKey].setStyleSheet(f'color: {color}; font-weight: 600;')

    def _setAllState(self, state: str) -> None:
        '''将全部环节置为同一状态。'''
        for key in self._dots:
            self._setStageState(key, state)

    def _setStageState(self, stageKey: str, state: str) -> None:
        '''设置单个环节的展示状态。'''
        palette = _STAGE_PALETTES.get(currentTheme(), _STAGE_PALETTES['light'])
        color = palette.get(state, palette['pending'])
        self._dots[stageKey].setStyleSheet(f'color: {color}; font-size: 14px;')
        self._labels[stageKey].setStyleSheet(f'color: {color};')
