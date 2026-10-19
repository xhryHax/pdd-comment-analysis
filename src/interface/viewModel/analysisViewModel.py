from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, Signal

from src.data.configAccess import ConfigAccess
from src.data.database import Database
from src.interface.model.strategyListItem import StrategyListItem
from src.interface.model.summaryContext import SummaryContext
from src.work.analysisPipeline import AnalysisWorker
from src.work.analysisRecord import AnalysisRecord
from src.work.analysisStrategy import AnalysisStrategy
from src.work.browserTools import BrowserTools
from src.work.llmService import LlmService

logger = logging.getLogger(__name__)


class AnalysisViewModel(QObject):
    '''新建分析页视图模型：策略加载、流程启动与结果落库。'''

    stageChanged = Signal(str)
    stageDetail = Signal(str, str)
    loginWaiting = Signal()
    crawlProgress = Signal(int, int)
    scoreProgress = Signal(int, int)
    filterStats = Signal(dict)
    correctionRequired = Signal(int, int)
    analysisFinished = Signal(dict)
    analysisFailed = Signal(str)

    def __init__(
        self,
        config: ConfigAccess,
        database: Database,
        browserTools: BrowserTools,
        llmService: LlmService,
        parent: QObject | None = None,
    ) -> None:
        '''初始化视图模型。

        Args:
            config: 系统配置读写器。
            database: 数据库仓储。
            browserTools: 浏览器采集工具。
            llmService: LLM 打分服务。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._config = config
        self._database = database
        self._browserTools = browserTools
        self._llmService = llmService
        self._worker: AnalysisWorker | None = None
        self._latestContext: SummaryContext | None = None

    @property
    def isRunning(self) -> bool:
        '''当前是否有分析流程在执行。'''
        if self._worker is None:
            return False
        try:
            return self._worker.isRunning()
        except RuntimeError:
            # C++ 对象已被删除（线程结束并清理）的兜底
            self._worker = None
            return False

    def start(self, goodsUrl: str, strategy: AnalysisStrategy) -> None:
        '''启动一次完整分析流程。

        Args:
            goodsUrl: 商品分享链接。
            strategy: 选定的分析策略。

        Raises:
            RuntimeError: 已有流程在执行时抛出。
        '''
        if self.isRunning:
            msg = '已有分析流程在执行，请等待完成后再开始'
            raise RuntimeError(msg)
        worker = AnalysisWorker(
            goodsUrl=goodsUrl,
            strategy=strategy,
            config=self._config,
            browserTools=self._browserTools,
            llmService=self._llmService,
        )
        self._worker = worker
        worker.stageChanged.connect(self.stageChanged)
        worker.stageDetail.connect(self.stageDetail)
        worker.loginWaiting.connect(self.loginWaiting)
        worker.crawlProgress.connect(self.crawlProgress)
        worker.scoreProgress.connect(self.scoreProgress)
        worker.filterStats.connect(self.filterStats)
        worker.correctionRequired.connect(self.correctionRequired)
        worker.analysisFinished.connect(self._onFinished)
        worker.analysisFailed.connect(self.analysisFailed)
        # 线程结束后：先清空引用再释放 C++ 对象，
        # 否则残留的包装指针会让 isRunning/stop 抛 RuntimeError
        worker.finished.connect(lambda w=worker: self._onWorkerFinished(w))
        logger.info('开始分析：%s（策略 %s）', goodsUrl, strategy.name)
        worker.start()

    def _onWorkerFinished(self, worker: AnalysisWorker) -> None:
        '''分析线程结束：清理引用并释放线程对象。

        Args:
            worker: 刚结束的分析线程。
        '''
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def stop(self) -> None:
        '''请求停止当前分析流程。'''
        if self._worker is not None:
            try:
                running = self._worker.isRunning()
            except RuntimeError:
                self._worker = None
                return
            if running:
                self._worker.requestStop()
                logger.info('已请求停止当前分析')

    def provideCorrectionFactor(self, factor: float | None) -> None:
        '''回填修正因子（None 表示用户取消）。'''
        if self._worker is None:
            return
        try:
            self._worker.provideCorrectionFactor(factor)
        except RuntimeError:
            # 流程已结束、线程对象已释放：丢弃本次回填
            self._worker = None

    def _onFinished(self, payload: dict) -> None:
        '''流程完成：落库分析记录并转发结果。'''
        # 将“是否维度重构”并入策略快照一同持久化，
        # 便于历史记录在 AI 总结注入时还原该状态
        snapshot = dict(payload.get('strategySnapshot') or {})
        snapshot['refactored'] = bool(payload.get('refactored', False))
        payload['strategySnapshot'] = snapshot
        record = AnalysisRecord(
            goodsName=str(payload.get('goodsName', '')),
            goodsUrl=str(payload.get('goodsUrl', '')),
            strategyId=str(payload.get('strategyId', '')),
            strategyName=str(payload.get('strategyName', '')),
            strategySnapshot=snapshot,
            totalCommentCount=int(payload.get('totalCommentCount', 0)),
            validCommentCount=int(payload.get('validCommentCount', 0)),
            credibilityThreshold=float(payload.get('credibilityThreshold', 0.0)),
            trimPercent=float(payload.get('trimPercent', 0.0)),
            correctionFactor=payload.get('correctionFactor'),
            finalScore=float(payload.get('finalScore', 0.0)),
            dimensionAverages=dict(payload.get('dimensionAverages') or {}),
            dimensionWeightedScores=dict(payload.get('dimensionWeightedScores') or {}),
        )
        try:
            recordId = self._database.saveAnalysisRecord(record)
            payload['recordId'] = recordId
        except Exception as error:  # noqa: BLE001 - 落库失败不应吞掉分析结果
            logger.error('分析记录保存失败：%s', error)
            payload['recordId'] = None
        self._saveIntermediateData(payload)
        self._latestContext = self._buildContext(payload)
        self.analysisFinished.emit(payload)

    def _saveIntermediateData(self, payload: dict) -> None:
        '''将本轮分析的中间数据落库（供历史记录回溯注入）。

        Args:
            payload: 分析完成载荷。
        '''
        recordId = payload.get('recordId')
        if recordId is None:
            logger.warning('缺少记录 ID，中间数据未保存')
            return
        intermediateData = payload.get('intermediateData') or []
        try:
            self._database.saveIntermediateData(
                int(recordId),
                str(payload.get('goodsUrl', '')),
                json.dumps(intermediateData, ensure_ascii=False),
            )
        except Exception as error:  # noqa: BLE001 - 中间数据失败不影响主流程
            logger.error('中间数据保存失败：%s', error)

    def _buildContext(self, payload: dict) -> SummaryContext:
        '''由分析载荷构建 AI 总结上下文。

        Args:
            payload: 分析完成载荷。

        Returns:
            SummaryContext: 注入数据上下文。
        '''
        return SummaryContext(
            goodsUrl=str(payload.get('goodsUrl', '')),
            goodsName=str(payload.get('goodsName', '')),
            recordId=payload.get('recordId'),
            strategySnapshot=dict(payload.get('strategySnapshot') or {}),
            refactored=bool(payload.get('refactored', False)),
            intermediateData=list(payload.get('intermediateData') or []),
            correctionFactor=payload.get('correctionFactor'),
            finalScore=float(payload.get('finalScore', 0.0)),
            dimensionAverages=dict(payload.get('dimensionAverages') or {}),
            dimensionWeightedScores=dict(payload.get('dimensionWeightedScores') or {}),
            totalCommentCount=int(payload.get('totalCommentCount', 0)),
            validCommentCount=int(payload.get('validCommentCount', 0)),
            credibilityThreshold=float(payload.get('credibilityThreshold', 0.0)),
            trimPercent=float(payload.get('trimPercent', 0.0)),
        )

    def summaryContext(self, goodsUrlFallback: str = '') -> SummaryContext:
        '''返回最近一次分析的注入数据上下文。

        Args:
            goodsUrlFallback: 无历史分析时使用的商品链接。

        Returns:
            SummaryContext: 上下文对象；从未分析过时仅含商品链接。
        '''
        if self._latestContext is not None:
            return self._latestContext
        return SummaryContext(goodsUrl=goodsUrlFallback)

    def clearLatestContext(self) -> None:
        '''清空内存中的最近一次分析上下文（不影响已入库数据）。'''
        self._latestContext = None
        logger.info('已清空最近一次分析上下文')
