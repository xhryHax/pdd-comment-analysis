from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any, ClassVar

import tomlkit

from src.data.pathHelper import projectRoot

logger = logging.getLogger(__name__)


class ConfigAccess:
    '''TOML 配置文件读写器（读取时以代码内默认值兜底）。

    读取使用标准库 tomllib，写入使用 tomlkit 以尽量保留配置文件
    中的注释与结构；文件缺失或键缺失时自动回落到 defaultConfig。
    '''

    defaultConfig: ClassVar[dict[str, dict[str, Any]]] = {
        'app': {
            'logLevel': 'info',
            'theme': 'light',
        },
        'crawl': {
            'driverPath': 'chromedriver/chromedriver.exe',
            'commentThreshold': 20,
            'commentBatchSize': 50,
            'commentMaxCount': 600,
            'maxScrollRetry': 5,
            'scrollWaitSeconds': 2.0,
            'redirectWaitSeconds': 3,
            'loginTimeoutSeconds': 180,
            'loginCheckInterval': 0.5,
        },
        'analysis': {
            'credibilityThreshold': 0.6,
            'trimPercent': 5,
            'validCommentThreshold': 10,
        },
        'llm': {
            'apiKey': '',
            'baseUrl': 'https://api.deepseek.com',
            'model': 'deepseek-chat',
            'maxConcurrency': 4,
            'batchSize': 50,
            'requestTimeoutSeconds': 120,
            'maxRetries': 3,
        },
        'browser': {
            'timezone': 'Asia/Shanghai',
            'language': 'zh-CN',
            'locale': 'zh_CN',
        },
        'aiSummary': {
            'model': 'deepseek-chat',
            'maxTokens': 1200,
            'temperature': 0.3,
            'historyLimit': 5,
            'intermediateLimit': 100,
        },
    }

    _levelNames: ClassVar[dict[str, int]] = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
    }

    def __init__(self, configPath: Path | str | None = None) -> None:
        '''初始化配置读写器并立即加载配置。

        Args:
            configPath: 配置文件路径，缺省时使用项目根下
                config/settings.toml。
        '''
        self._configPath: Path = (
            Path(configPath) if configPath is not None else projectRoot() / 'config' / 'settings.toml'
        )
        self._data: dict[str, dict[str, Any]] = {}
        self.load()

    @property
    def configPath(self) -> Path:
        '''当前使用的配置文件路径。'''
        return self._configPath

    def load(self) -> None:
        '''从磁盘加载配置并与默认值合并（文件值优先）。

        配置文件不存在时仅使用默认值；文件存在但个别键缺失时，
        以 defaultConfig 中的同名键兜底。
        '''
        merged: dict[str, dict[str, Any]] = {}
        for section, values in self.defaultConfig.items():
            merged[section] = dict(values)
        if self._configPath.is_file():
            try:
                fileData = tomllib.loads(self._configPath.read_text(encoding='utf-8'))
            except (OSError, tomllib.TOMLDecodeError) as error:
                logger.warning('读取配置文件失败，使用默认配置：%s', error)
                fileData = {}
            for section, values in fileData.items():
                if isinstance(values, dict):
                    merged.setdefault(section, {}).update(values)
        self._data = merged

    def get(self, section: str, key: str, default: Any = None) -> Any:
        '''读取指定配置项。

        Args:
            section: 配置节名，如 'llm'。
            key: 配置键名，如 'maxConcurrency'。
            default: 配置项不存在时的返回值。

        Returns:
            Any: 配置值；不存在时返回 default。
        '''
        return self._data.get(section, {}).get(key, default)

    def getInt(self, section: str, key: str, default: int = 0) -> int:
        '''读取整型配置项（无法转换时返回 default）。'''
        value = self.get(section, key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning('配置项 [%s].%s 不是整数：%r', section, key, value)
            return default

    def getFloat(self, section: str, key: str, default: float = 0.0) -> float:
        '''读取浮点型配置项（无法转换时返回 default）。'''
        value = self.get(section, key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning('配置项 [%s].%s 不是浮点数：%r', section, key, value)
            return default

    def getStr(self, section: str, key: str, default: str = '') -> str:
        '''读取字符串配置项（None 转为 default）。'''
        value = self.get(section, key, default)
        if value is None:
            return default
        return str(value)

    def getLogLevel(self) -> int:
        '''读取日志级别常量。

        Returns:
            int: logging 模块的级别常量，非法值回落到 INFO。
        '''
        name = self.getStr('app', 'logLevel', 'info').lower()
        return self._levelNames.get(name, logging.INFO)

    def set(self, section: str, key: str, value: Any) -> None:
        '''更新内存中的配置项（需调用 save 持久化）。

        Args:
            section: 配置节名。
            key: 配置键名。
            value: 新的配置值。
        '''
        self._data.setdefault(section, {})[key] = value

    def setMany(self, values: dict[str, dict[str, Any]]) -> None:
        '''批量更新内存中的配置（需调用 save 持久化）。

        Args:
            values: 形如 {'llm': {'maxConcurrency': 8}} 的嵌套字典。
        '''
        for section, sectionValues in values.items():
            for key, value in sectionValues.items():
                self.set(section, key, value)

    def save(self) -> None:
        '''将当前配置回写到 TOML 文件（保留原文件注释）。

        Raises:
            OSError: 写入文件失败时抛出。
        '''
        doc = tomlkit.document()
        if self._configPath.is_file():
            try:
                doc = tomlkit.parse(self._configPath.read_text(encoding='utf-8'))
            except (OSError, tomlkit.exceptions.ParseError) as error:
                logger.warning('解析原配置文件失败，将重建配置文件：%s', error)
                doc = tomlkit.document()
        for section, sectionValues in self._data.items():
            table = doc.setdefault(section, tomlkit.table())
            for key, value in sectionValues.items():
                table[key] = value
        self._configPath.parent.mkdir(parents=True, exist_ok=True)
        self._configPath.write_text(tomlkit.dumps(doc), encoding='utf-8')
        logger.info('配置已保存：%s', self._configPath)

    def resetDefaults(self) -> None:
        '''恢复全部默认配置并立即回写磁盘。'''
        self._data = {section: dict(values) for section, values in self.defaultConfig.items()}
        self.save()
        logger.info('配置已恢复默认值')

    def snapshot(self) -> dict[str, dict[str, Any]]:
        '''返回当前配置的深拷贝快照。

        Returns:
            dict[str, dict[str, Any]]: 配置数据的副本，修改不影响本实例。
        '''
        return {section: dict(values) for section, values in self._data.items()}
