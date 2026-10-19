from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from src.interface.model.logItem import LogItem
from src.interface.tools.qtLogHandler import QtLogHandler

logger = logging.getLogger(__name__)


class LogViewModel(QObject):
    '''运行日志页视图模型：日志桥接、级别过滤与暂停跟随。'''

    visibleLevels: tuple[str, ...] = ('DEBUG', 'INFO', 'WARNING', 'ERROR')

    def __init__(self, logHandler: QtLogHandler, parent: QObject | None = None) -> None:
        '''初始化视图模型并将桥接处理器挂载到根日志器。

        Args:
            logHandler: 日志桥接处理器。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._handler = logHandler
        self._levelFilter: set[str] = set(self.visibleLevels)
        self._paused = False
        rootLogger = logging.getLogger()
        if logHandler not in rootLogger.handlers:
            rootLogger.addHandler(logHandler)
        logger.info('界面日志桥接已挂载')

    @property
    def handler(self) -> QtLogHandler:
        '''日志桥接处理器（供视图订阅其信号）。'''
        return self._handler

    @property
    def paused(self) -> bool:
        '''日志跟随是否处于暂停状态。'''
        return self._paused

    def setPaused(self, paused: bool) -> None:
        '''设置日志跟随暂停状态。'''
        self._paused = paused

    def isLevelVisible(self, level: str) -> bool:
        '''判断某级别当前是否可见。'''
        return level in self._levelFilter

    def setSingleLevel(self, level: str | None) -> None:
        '''设置单一级别过滤。

        Args:
            level: 仅显示该级别；None 表示显示全部级别。
        '''
        self._levelFilter = {level} if level is not None else set(self.visibleLevels)

    def toDisplayText(self, entry: dict) -> str | None:
        '''将日志条目转换为可见展示文本。

        Args:
            entry: QtLogHandler 广播的字典。

        Returns:
            str | None: 展示文本，级别被过滤时返回 None。
        '''
        if str(entry.get('level', '')) not in self._levelFilter:
            return None
        return LogItem.fromDict(entry).formatted
