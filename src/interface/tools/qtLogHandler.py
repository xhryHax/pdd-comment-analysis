from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, Signal


class LogSignalHub(QObject):
    '''日志信号中转站（供日志页订阅）。'''

    logEmitted = Signal(dict)


class QtLogHandler(logging.Handler):
    '''将日志记录转发为 Qt 信号的桥接处理器。'''

    maxBufferEntries: int = 500

    def __init__(self) -> None:
        '''初始化桥接处理器并建立信号中转站与环形缓冲。'''
        super().__init__()
        self.hub = LogSignalHub()
        self.buffer: list[dict] = []
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        '''格式化日志记录并广播（供日志页实时展示）。

        Args:
            record: 日志记录对象。
        '''
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 - 日志桥接不可再抛异常
            message = record.getMessage()
        entry = {
            'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
            'formatted': message,
        }
        self.buffer.append(entry)
        if len(self.buffer) > self.maxBufferEntries:
            del self.buffer[: len(self.buffer) - self.maxBufferEntries]
        self.hub.logEmitted.emit(entry)
