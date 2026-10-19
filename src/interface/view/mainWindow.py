from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    '''主窗口：侧边导航 + QStackedWidget 页面切换。'''

    # 页面切换后发出（参数为切换后的页面索引），供浮层（如 AI 总结弹窗）自行隐藏
    pageSwitched = Signal(int)

    navMarks: list[tuple[str, str]] = [
        ('※', '新建分析'),
        ('▤', '分析记录'),
        ('✚', '策略管理'),
        ('⚙', '系统设置'),
        ('≣', '运行日志'),
    ]

    def __init__(self, pages: list[QWidget], parent=None) -> None:
        '''初始化主窗口。

        Args:
            pages: 与导航项顺序一致的页面控件列表。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self.setWindowTitle('拼多多商品评论分析')
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self._navButtons: list[QPushButton] = []

        self._stackedWidget = QStackedWidget()
        for page in pages:
            self._stackedWidget.addWidget(page)

        navBar = QFrame()
        navBar.setProperty('navBar', True)
        navBar.setFixedWidth(184)
        navLayout = QVBoxLayout(navBar)
        navLayout.setContentsMargins(16, 28, 16, 16)
        navLayout.setSpacing(6)
        titleLabel = QLabel('评论分析')
        titleLabel.setProperty('navTitle', True)
        subtitleLabel = QLabel('COMMENT ANALYZER')
        subtitleLabel.setStyleSheet('color: #C5B0F4; font-size: 10px; letter-spacing: 2px;')
        navLayout.addWidget(titleLabel)
        navLayout.addWidget(subtitleLabel)
        navLayout.addSpacing(18)
        for index, (mark, title) in enumerate(self.navMarks):
            navButton = QPushButton()
            navButton.setProperty('navButton', True)
            navButton.setCursor(Qt.CursorShape.PointingHandCursor)
            navButton.setCheckable(True)
            buttonLayout = QHBoxLayout(navButton)
            buttonLayout.setContentsMargins(4, 0, 4, 0)
            buttonLayout.setSpacing(10)
            markLabel = QLabel(mark)
            markLabel.setFixedWidth(18)
            markLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
            titleLabel = QLabel(title)
            buttonLayout.addWidget(markLabel)
            buttonLayout.addWidget(titleLabel)
            buttonLayout.addStretch(1)
            navButton.clicked.connect(lambda checked, idx=index: self.switchTo(idx))
            navLayout.addWidget(navButton)
            self._navButtons.append(navButton)
        navLayout.addStretch(1)
        versionLabel = QLabel('v0.1.0')
        versionLabel.setStyleSheet('color: rgba(255,255,255,0.35); font-size: 11px;')
        navLayout.addWidget(versionLabel)

        centralWidget = QWidget()
        centralLayout = QHBoxLayout(centralWidget)
        centralLayout.setContentsMargins(24, 24, 24, 24)
        centralLayout.setSpacing(20)
        centralLayout.addWidget(navBar)
        centralLayout.addWidget(self._stackedWidget, stretch=1)
        self.setCentralWidget(centralWidget)
        self.switchTo(0)

    def switchTo(self, index: int) -> None:
        '''切换到指定页面并更新导航高亮。

        Args:
            index: 页面索引。
        '''
        index = max(0, min(index, self._stackedWidget.count() - 1))
        self._stackedWidget.setCurrentIndex(index)
        for buttonIndex, button in enumerate(self._navButtons):
            active = buttonIndex == index
            button.setChecked(active)
            button.setProperty('navActive', active)
            style = button.style()
            style.unpolish(button)
            style.polish(button)
        self.pageSwitched.emit(index)
