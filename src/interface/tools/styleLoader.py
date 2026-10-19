from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.data.pathHelper import projectRoot

logger = logging.getLogger(__name__)

# 主题注册表：主题名 -> QSS 文件名（位于 resources/style/ 下）
THEMES: dict[str, str] = {
    'light': 'main.qss',
    'dark': 'dark.qss',
}

# 当前已应用的主题名（供非 QSS 的内联样式控件取色）
_currentTheme: str = 'light'

# 主题切换回调列表（参数为新主题名）
_themeListeners: list[Callable[[str], None]] = []


def addThemeChangedListener(callback: Callable[[str], None]) -> None:
    '''注册主题切换回调（内联取色控件借此刷新自身展示）。

    Args:
        callback: 回调函数，参数为切换后的主题名。
    '''
    _themeListeners.append(callback)


def currentTheme() -> str:
    '''返回当前已应用的主题名（'light' 或 'dark'）。

    Returns:
        str: 最近一次 loadTheme 成功应用的主题名。
    '''
    return _currentTheme


def stylePathFor(themeName: str) -> Path:
    '''返回主题名对应的 QSS 文件路径（未知主题回落到浅色）。

    Args:
        themeName: 主题名（'light' / 'dark'）。

    Returns:
        Path: QSS 文件的绝对路径。
    '''
    name = themeName if themeName in THEMES else 'light'
    return projectRoot() / 'resources' / 'style' / THEMES[name]


def loadQss(app: QApplication, qssPath: Path | str | None = None) -> None:
    '''为应用加载全局 QSS 样式表。

    Args:
        app: 应用实例。
        qssPath: QSS 文件路径，缺省时使用项目根下
            resources/style/main.qss。

    Raises:
        FileNotFoundError: 样式文件不存在时抛出。
    '''
    path = Path(qssPath) if qssPath is not None else projectRoot() / 'resources' / 'style' / 'main.qss'
    if not path.is_file():
        msg = f'样式文件不存在：{path}'
        raise FileNotFoundError(msg)
    app.setStyleSheet(path.read_text(encoding='utf-8'))
    logger.info('全局 QSS 已加载：%s', path)


def loadTheme(app: QApplication, themeName: str) -> None:
    '''按主题名加载全局 QSS 并记录当前主题。

    Args:
        app: 应用实例。
        themeName: 主题名（'light' / 'dark'），未知值回落到 'light'。

    Raises:
        FileNotFoundError: 样式文件不存在时抛出。
    '''
    global _currentTheme
    resolved = themeName if themeName in THEMES else 'light'
    path = stylePathFor(resolved)
    loadQss(app, path)
    _currentTheme = resolved
    for callback in _themeListeners:
        callback(resolved)
    logger.info('主题已切换：%s（%s）', resolved, path.name)
