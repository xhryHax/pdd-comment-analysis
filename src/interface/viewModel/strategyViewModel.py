from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, QThread, Signal

from src.data.configAccess import ConfigAccess
from src.data.database import Database
from src.data.strategyFileAccess import StrategyFileAccess
from src.interface.model.strategyListItem import StrategyListItem
from src.work.analysisStrategy import AnalysisStrategy
from src.work.strategyAiService import StrategyAiService

logger = logging.getLogger(__name__)


class AiStrategyWorker(QThread):
    '''后台执行 AI 策略生成的线程。'''

    generateSucceeded = Signal(object)
    generateFailed = Signal(str)

    def __init__(self, service: StrategyAiService, requirement: str, parent: QObject | None = None) -> None:
        '''初始化生成线程。

        Args:
            service: AI 策略生成服务。
            requirement: 用户的自然语言需求。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._service = service
        self._requirement = requirement

    def run(self) -> None:
        '''执行生成并广播结果（勿直接调用）。'''
        try:
            strategy = self._service.generateStrategy(self._requirement)
        except Exception as error:  # noqa: BLE001 - 顶层兜底
            self.generateFailed.emit(str(error))
        else:
            self.generateSucceeded.emit(strategy)


class StrategyViewModel(QObject):
    '''策略管理页视图模型：默认/自建策略的加载、保存与 AI 生成。'''

    strategiesChanged = Signal()
    aiGenerateStarted = Signal()
    aiGenerateSucceeded = Signal(object)
    aiGenerateFailed = Signal(str)

    def __init__(
        self,
        config: ConfigAccess,
        database: Database,
        fileAccess: StrategyFileAccess,
        parent: QObject | None = None,
    ) -> None:
        '''初始化视图模型。

        Args:
            config: 系统配置读写器。
            database: 数据库仓储（用户自建策略）。
            fileAccess: 默认策略文件读写器。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._config = config
        self._database = database
        self._fileAccess = fileAccess
        self._aiService = StrategyAiService(config)
        self._aiWorker: AiStrategyWorker | None = None
        self.items: list[StrategyListItem] = []
        self.refresh()

    @property
    def isGenerating(self) -> bool:
        '''AI 策略是否正在生成中。'''
        if self._aiWorker is None:
            return False
        try:
            return self._aiWorker.isRunning()
        except RuntimeError:
            # C++ 对象已被删除（线程结束并清理）的兜底
            self._aiWorker = None
            return False

    def refresh(self) -> None:
        '''重新加载全部策略（默认在前，自建在后）。'''
        items: list[StrategyListItem] = []
        for data in self._fileAccess.listStrategies():
            try:
                strategy = AnalysisStrategy.fromDict(data)
            except ValueError as error:
                logger.warning('默认策略解析失败，已跳过：%s', error)
                continue
            items.append(StrategyListItem(strategy=strategy, sourceLabel='默认', sourceKind='default'))
        for row in self._database.listUserStrategies():
            try:
                data = dict(row)
                data['dimensions'] = json.loads(row.get('dimensionsJson', '[]'))
                strategy = AnalysisStrategy.fromDict(data)
                strategy.source = 'user'
            except (ValueError, json.JSONDecodeError) as error:
                logger.warning('用户策略解析失败，已跳过：%s', error)
                continue
            items.append(StrategyListItem(strategy=strategy, sourceLabel='自建', sourceKind='user'))
        self.items = items
        logger.info('策略列表已刷新：%d 个', len(items))
        self.strategiesChanged.emit()

    def itemAt(self, index: int) -> StrategyListItem | None:
        '''按索引取策略展示项。'''
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def saveUserStrategy(self, strategy: AnalysisStrategy) -> list[str]:
        '''保存（新建或覆盖）用户自建策略。

        Args:
            strategy: 策略实例（strategyId 为空时自动生成）。

        Returns:
            list[str]: 校验错误列表，为空表示保存成功。
        '''
        if not strategy.strategyId:
            strategy.strategyId = f'strategy{len(self.items) + 1}'
        strategy.source = 'user'
        errors = strategy.validate()
        if errors:
            return errors
        self._database.saveUserStrategy(
            {
                'strategyId': strategy.strategyId,
                'name': strategy.name,
                'dimensionsJson': json.dumps([d.toDict() for d in strategy.dimensions]),
                'ratingPrompt': strategy.ratingPrompt,
                'credibilityPrompt': strategy.credibilityPrompt,
            },
        )
        self.refresh()
        return []

    def deleteUserStrategy(self, strategyId: str) -> bool:
        '''删除用户自建策略。'''
        deleted = self._database.deleteUserStrategy(strategyId)
        if deleted:
            self.refresh()
        return deleted

    def startAiGenerate(self, requirement: str) -> None:
        '''后台启动 AI 策略生成。

        Args:
            requirement: 用户的自然语言需求。

        Raises:
            RuntimeError: 已有生成任务在执行时抛出。
        '''
        if self.isGenerating:
            msg = 'AI 策略生成中，请稍候'
            raise RuntimeError(msg)
        self.aiGenerateStarted.emit()
        worker = AiStrategyWorker(self._aiService, requirement)
        self._aiWorker = worker
        worker.generateSucceeded.connect(self.aiGenerateSucceeded)
        worker.generateFailed.connect(self.aiGenerateFailed)
        # 线程结束后：先清空引用再释放 C++ 对象，
        # 否则残留的包装指针会让 isGenerating 抛 RuntimeError
        worker.finished.connect(lambda w=worker: self._onAiWorkerFinished(w))
        worker.start()

    def _onAiWorkerFinished(self, worker: AiStrategyWorker) -> None:
        '''AI 生成线程结束：清理引用并释放线程对象。

        Args:
            worker: 刚结束的生成线程。
        '''
        if self._aiWorker is worker:
            self._aiWorker = None
        worker.deleteLater()
