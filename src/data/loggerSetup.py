from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import ClassVar

from src.data.pathHelper import projectRoot

_LEVEL_NAMES: dict[str, int] = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
}


def maskSecret(secret: str) -> str:
    '''对敏感字符串（如 API Key）做掩码处理，用于日志输出。

    Args:
        secret: 原始敏感字符串。

    Returns:
        str: 掩码后的字符串，长度不足时统一返回 '***'。
    '''
    if len(secret) <= 8:
        return '***'
    return f'{secret[:4]}****{secret[-4:]}'


def resolveLevel(levelName: str) -> int:
    '''将级别名称解析为 logging 常量。

    Args:
        levelName: 级别名称（debug/info/warning/error，不区分大小写）。

    Returns:
        int: 对应的 logging 级别常量，非法名称回落到 INFO。
    '''
    return _LEVEL_NAMES.get(levelName.lower(), logging.INFO)


class LoggerSetup:
    '''系统日志初始化器（控制台 + 按大小轮转的文件）。

    日志文件写入 data/logs/app.log，按大小轮转以避免膨胀；
    重复调用 setup 时仅调整级别，不重复挂载处理器。界面实时
    日志 Handler 由 interface/tools 中的部件另行挂载。
    '''

    logDirName: ClassVar[str] = 'logs'
    logFileName: ClassVar[str] = 'app.log'
    maxBytes: ClassVar[int] = 5 * 1024 * 1024
    backupCount: ClassVar[int] = 3
    formatTemplate: ClassVar[str] = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

    _fileHandler: RotatingFileHandler | None = None

    @classmethod
    def logFilePath(cls, logDirPath: Path | None = None) -> Path:
        '''返回日志文件路径。

        Args:
            logDirPath: 日志目录，缺省时使用项目根下 data/logs。

        Returns:
            Path: 日志文件的绝对路径。
        '''
        baseDir = logDirPath if logDirPath is not None else projectRoot() / 'data' / cls.logDirName
        return baseDir / cls.logFileName

    @classmethod
    def setup(cls, levelName: str = 'info', logDirPath: Path | None = None) -> logging.Logger:
        '''初始化根日志器（幂等，可重复调用）。

        Args:
            levelName: 日志级别名称。
            logDirPath: 日志目录，缺省时使用 data/logs。

        Returns:
            logging.Logger: 配置完成的根日志器。
        '''
        rootLogger = logging.getLogger()
        level = resolveLevel(levelName)
        rootLogger.setLevel(level)
        if cls._fileHandler is not None:
            rootLogger.setLevel(level)
            return rootLogger
        formatter = logging.Formatter(cls.formatTemplate)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        rootLogger.addHandler(consoleHandler)

        logFile = cls.logFilePath(logDirPath)
        logFile.parent.mkdir(parents=True, exist_ok=True)
        fileHandler = RotatingFileHandler(
            logFile,
            maxBytes=cls.maxBytes,
            backupCount=cls.backupCount,
            encoding='utf-8',
        )
        fileHandler.setFormatter(formatter)
        rootLogger.addHandler(fileHandler)
        cls._fileHandler = fileHandler
        rootLogger.info('日志系统初始化完成，日志文件：%s', logFile)
        return rootLogger
