from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LogItem:
    '''日志页展示项。'''

    time: str
    level: str
    name: str
    message: str
    formatted: str

    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> LogItem:
        '''从日志桥接字典构建展示项。

        Args:
            data: QtLogHandler 广播的字典。

        Returns:
            LogItem: 日志展示项。
        '''
        return cls(
            time=str(data.get('time', '')),
            level=str(data.get('level', '')),
            name=str(data.get('name', '')),
            message=str(data.get('message', '')),
            formatted=str(data.get('formatted', '')),
        )
