from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from src.data.pathHelper import projectRoot

logger = logging.getLogger(__name__)


class StrategyFileAccess:
    '''默认策略 JSON 文件读写器（config/strategies 目录）。

    每个策略一个 JSON 文件，文件名即策略 ID；内容为策略的
    字典结构（由调用方负责与 AnalysisStrategy 互转）。
    '''

    strategiesDirName: ClassVar = 'strategies'

    def __init__(self, strategiesDirPath: Path | str | None = None) -> None:
        '''初始化策略文件读写器。

        Args:
            strategiesDirPath: 策略目录，缺省时使用项目根下
                config/strategies。
        '''
        self._strategiesDirPath: Path = (
            Path(strategiesDirPath)
            if strategiesDirPath is not None
            else projectRoot() / 'config' / 'strategies'
        )

    @property
    def strategiesDirPath(self) -> Path:
        '''策略目录路径。'''
        return self._strategiesDirPath

    def listStrategies(self) -> list[dict[str, Any]]:
        '''列出目录下全部默认策略字典。

        单个文件损坏时跳过并记录警告，不影响其余策略加载。

        Returns:
            list[dict[str, Any]]: 策略字典列表（按策略 ID 排序）。
        '''
        if not self._strategiesDirPath.is_dir():
            return []
        strategies: list[dict[str, Any]] = []
        for filePath in sorted(self._strategiesDirPath.glob('*.json')):
            data = self._readFile(filePath)
            if data is not None:
                strategies.append(data)
        return strategies

    def loadStrategy(self, strategyId: str) -> dict[str, Any] | None:
        '''按策略 ID 读取默认策略。

        Args:
            strategyId: 策略 ID（即文件名主体）。

        Returns:
            dict[str, Any] | None: 策略字典，不存在或损坏时返回 None。
        '''
        filePath = self._strategiesDirPath / f'{strategyId}.json'
        return self._readFile(filePath)

    def saveStrategy(self, strategyDict: dict[str, Any]) -> Path:
        '''保存（覆盖写入）默认策略文件。

        Args:
            strategyDict: 策略字典，需包含非空 strategyId。

        Returns:
            Path: 写入的文件路径。

        Raises:
            ValueError: strategyId 为空或非法时抛出。
        '''
        strategyId = str(strategyDict.get('strategyId', '')).strip()
        if not strategyId or not strategyId.isidentifier():
            msg = f'非法的策略 ID：{strategyId!r}（需为合法标识符）'
            raise ValueError(msg)
        self._strategiesDirPath.mkdir(parents=True, exist_ok=True)
        filePath = self._strategiesDirPath / f'{strategyId}.json'
        filePath.write_text(
            json.dumps(strategyDict, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        logger.info('默认策略文件已保存：%s', filePath)
        return filePath

    def deleteStrategyFile(self, strategyId: str) -> bool:
        '''删除默认策略文件。

        Args:
            strategyId: 策略 ID。

        Returns:
            bool: 实际删除返回 True，文件不存在返回 False。
        '''
        filePath = self._strategiesDirPath / f'{strategyId}.json'
        if filePath.is_file():
            filePath.unlink()
            logger.info('默认策略文件已删除：%s', filePath)
            return True
        return False

    def _readFile(self, filePath: Path) -> dict[str, Any] | None:
        '''读取并解析单个策略 JSON 文件。

        Args:
            filePath: 文件路径。

        Returns:
            dict[str, Any] | None: 策略字典，失败时返回 None。
        '''
        if not filePath.is_file():
            return None
        try:
            data = json.loads(filePath.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning('策略文件解析失败，已跳过 %s：%s', filePath, error)
            return None
        if not isinstance(data, dict):
            logger.warning('策略文件内容不是对象，已跳过 %s', filePath)
            return None
        return data
