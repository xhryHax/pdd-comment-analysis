from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.interface.model.logItem import LogItem
from src.interface.tools.styleLoader import addThemeChangedListener, currentTheme
from src.interface.viewModel.logViewModel import LogViewModel

# 各日志级别在不同主题下的文字色
LEVEL_COLORS: dict[str, dict[str, str]] = {
    'DEBUG': {'light': '#6B6B6B', 'dark': '#8B949E'},
    'INFO': {'light': '#1F1D3D', 'dark': '#F2F2F2'},
    'WARNING': {'light': '#B07A1E', 'dark': '#E5B567'},
    'ERROR': {'light': '#FF3D8B', 'dark': '#F87171'},
}


class LogView(QWidget):
    '''运行日志页：实时日志流、级别过滤与跟随控制。'''

    maxVisibleBlocks: int = 2000

    def __init__(self, viewModel: LogViewModel, parent: QWidget | None = None) -> None:
        '''初始化页面并订阅日志桥接信号。

        Args:
            viewModel: 日志页视图模型。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._buildUi()
        self._connectSignals()
        self._appendHistory()
        addThemeChangedListener(lambda _themeName: self._rebuildVisible())

    def _levelColor(self, level: str) -> str:
        '''返回日志级别在当前主题下的文字色。

        Args:
            level: 日志级别名（DEBUG/INFO/WARNING/ERROR）。

        Returns:
            str: 十六进制颜色值。
        '''
        entry = LEVEL_COLORS.get(level)
        if entry is None:
            return '#F2F2F2' if currentTheme() == 'dark' else '#000000'
        return entry.get(currentTheme(), entry['light'])

    def _buildUi(self) -> None:
        '''构建页面布局。'''
        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(10)
        titleLabel = QLabel('运行日志')
        titleLabel.setProperty('headingLevel', '1')
        rootLayout.addWidget(titleLabel)

        toolRow = QHBoxLayout()
        toolRow.setSpacing(8)
        levelHint = QLabel('筛选：')
        levelHint.setProperty('caption', True)
        toolRow.addWidget(levelHint)
        self._levelButtons: dict[str, QPushButton] = {}
        for level in self._viewModel.visibleLevels:
            button = QPushButton(level)
            button.setProperty('variant', 'ghost')
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setFixedHeight(30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.toggled.connect(lambda checked, name=level: self._onLevelToggled(name, checked))
            toolRow.addWidget(button)
            self._levelButtons[level] = button
        self._pauseButton = QPushButton('暂停跟随')
        self._pauseButton.setProperty('variant', 'ghost')
        self._pauseButton.setCheckable(True)
        self._pauseButton.setFixedHeight(30)
        toolRow.addWidget(self._pauseButton)
        clearButton = QPushButton('清空')
        clearButton.setProperty('variant', 'ghost')
        clearButton.setFixedHeight(30)
        clearButton.clicked.connect(self._onClearClicked)
        toolRow.addWidget(clearButton)
        toolRow.addStretch(1)
        rootLayout.addLayout(toolRow)

        self._logEdit = QPlainTextEdit()
        self._logEdit.setReadOnly(True)
        self._logEdit.setMaximumBlockCount(self.maxVisibleBlocks)
        font = QFont('Consolas')
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._logEdit.setFont(font)
        rootLayout.addWidget(self._logEdit, stretch=1)

    def _connectSignals(self) -> None:
        '''绑定信号。'''
        self._viewModel.handler.hub.logEmitted.connect(self._onLogEmitted)
        self._pauseButton.toggled.connect(self._onPauseToggled)

    def _appendHistory(self) -> None:
        '''回放桥接缓冲中的历史日志。'''
        for entry in self._viewModel.handler.buffer:
            text = self._viewModel.toDisplayText(entry)
            if text is not None:
                self._appendLine(entry, text)

    def _onLogEmitted(self, entry: dict) -> None:
        '''实时追加一条日志。'''
        text = self._viewModel.toDisplayText(entry)
        if text is not None:
            self._appendLine(entry, text)

    def _appendLine(self, entry: dict, text: str) -> None:
        '''以级别着色追加一行日志并按需跟随滚动。'''
        item = LogItem.fromDict(entry)
        color = self._levelColor(item.level)
        self._logEdit.appendHtml(
            f'<span style="color:{color};">{text.replace(chr(60), '&lt;').replace(chr(62), '&gt;')}</span>',
        )
        if not self._viewModel.paused:
            scrollbar = self._logEdit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _onLevelToggled(self, level: str, checked: bool) -> None:
        '''切换级别过滤：选中仅显示该级别，取消选中恢复显示全部。'''
        self._viewModel.setSingleLevel(level if checked else None)
        self._rebuildVisible()

    def _onPauseToggled(self, paused: bool) -> None:
        '''切换跟随暂停。'''
        self._viewModel.setPaused(paused)
        self._pauseButton.setText('恢复跟随' if paused else '暂停跟随')

    def _onClearClicked(self) -> None:
        '''清空日志视图。'''
        self._logEdit.clear()

    def _rebuildVisible(self) -> None:
        '''按当前过滤条件重建日志视图。'''
        self._logEdit.clear()
        self._appendHistory()
