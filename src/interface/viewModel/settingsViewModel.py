from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from src.data.configAccess import ConfigAccess
from src.work.llmService import LlmService

logger = logging.getLogger(__name__)


class SettingsViewModel(QObject):
    '''系统设置页视图模型：参数读写、连接测试与恢复默认。'''

    saved = Signal()
    connectionTested = Signal(bool, str)

    def __init__(self, config: ConfigAccess, parent: QObject | None = None) -> None:
        '''初始化视图模型。

        Args:
            config: 系统配置读写器。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._config = config

    def snapshot(self) -> dict[str, dict[str, Any]]:
        '''返回当前配置快照（供表单填充）。'''
        return self._config.snapshot()

    def save(self, values: dict[str, dict[str, Any]]) -> None:
        '''批量保存配置并回写磁盘。

        Args:
            values: 形如 {'llm': {'maxConcurrency': 8}} 的嵌套字典。
        '''
        self._config.setMany(values)
        self._config.save()
        self.saved.emit()

    def resetDefaults(self) -> dict[str, dict[str, Any]]:
        '''恢复默认配置并返回默认快照。'''
        self._config.resetDefaults()
        return self._config.snapshot()

    def testConnection(self) -> None:
        '''测试 DeepSeek API 连通性并广播结果（同步执行）。'''
        try:
            reply = LlmService(self._config).testConnection()
        except Exception as error:  # noqa: BLE001 - 测试结果统一广播
            logger.warning('API 连接测试失败：%s', error)
            self.connectionTested.emit(False, str(error))
        else:
            logger.info('API 连接测试成功：%s', reply)
            self.connectionTested.emit(True, reply)
