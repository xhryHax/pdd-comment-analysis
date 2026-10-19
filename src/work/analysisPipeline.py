from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

from src.data.configAccess import ConfigAccess
from src.work import aggregator
from src.work.analysisStrategy import AnalysisStrategy
from src.work.browserTools import BrowserTools, LoginStatus
from src.work.commentScore import CommentScore
from src.work.llmService import LlmService

logger = logging.getLogger(__name__)


class AnalysisWorker(QThread):
    '''分析流程状态机（运行于独立线程）。

    按环节编排完整分析流程：登录等待 → 抓取 → 条数判断/维度
    重构 → LLM 打分 → 有效评论判定/修正因子 → 汇总；逐环节通
    过信号上报进度；修正因子环节挂起等待 UI 回填后继续。
    '''

    stageChanged = Signal(str)
    stageDetail = Signal(str, str)
    loginWaiting = Signal()
    goodsNameReady = Signal(str)
    crawlProgress = Signal(int, int)
    scoreProgress = Signal(int, int)
    filterStats = Signal(dict)
    correctionRequired = Signal(int, int)
    analysisFinished = Signal(dict)
    analysisFailed = Signal(str)

    _correctionWaitSeconds: float = 300.0

    def __init__(
        self,
        goodsUrl: str,
        strategy: AnalysisStrategy,
        config: ConfigAccess,
        browserTools: BrowserTools,
        llmService: LlmService,
        parent=None,
    ) -> None:
        '''初始化分析工作线程。

        Args:
            goodsUrl: 商品分享链接。
            strategy: 用户选择的分析策略。
            config: 系统配置读写器。
            browserTools: 浏览器采集工具。
            llmService: LLM 打分服务。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._goodsUrl = goodsUrl
        self._strategy = strategy
        self._config = config
        self._browserTools = browserTools
        self._llmService = llmService
        self._stopRequested = False
        self._correctionEvent = threading.Event()
        self._correctionValue: float | None = None

    def requestStop(self) -> None:
        '''请求停止分析（在环节边界处生效）。'''
        self._stopRequested = True

    def provideCorrectionFactor(self, value: float | None) -> None:
        '''回填用户提供的修正因子以继续流程。

        Args:
            value: 0-1 的修正因子；None 表示用户取消（不修正）。
        '''
        self._correctionValue = value
        self._correctionEvent.set()

    def run(self) -> None:
        '''执行完整分析流程（勿直接调用，由 start 触发）。'''
        try:
            payload = self._runStages()
        except Exception as error:  # noqa: BLE001 - 顶层兜底，统一上报
            logger.exception('分析流程异常终止')
            self.analysisFailed.emit(str(error))
            return
        finally:
            self._browserTools.close()
        if payload is not None:
            self.stageChanged.emit('done')
            self.analysisFinished.emit(payload)

    def _runStages(self) -> dict | None:
        '''顺序执行各分析环节并返回结果载荷。'''
        # 环节 1：打开页面与登录等待
        self.stageChanged.emit('login')
        loginStatus = self._browserTools.openGoodsPage(self._goodsUrl)
        if loginStatus is LoginStatus.needLogin:
            self.loginWaiting.emit()
            if not self._browserTools.waitForLogin():
                self.analysisFailed.emit('等待登录超时，分析已终止')
                return None
        if self._stopRequested:
            return None
        goodsName = self._browserTools.getGoodsName() or '未知商品'
        self.goodsNameReady.emit(goodsName)

        # 环节 2：进入评论页并抓取原数据
        self.stageChanged.emit('crawl')
        if not self._browserTools.openCommentPage():
            self.analysisFailed.emit('无法进入评论区，分析已终止')
            return None
        comments: list[str] = []
        total = self._config.getInt('crawl', 'commentMaxCount', 600)
        for batch in self._browserTools.getCommentSet():
            comments.extend(batch)
            self.crawlProgress.emit(len(comments), total)
            if self._stopRequested:
                return None
        self.stageDetail.emit('crawl', f'共抓取评论 {len(comments)} 条')

        # 环节 3：条数判断与维度重构
        self.stageChanged.emit('refactor')
        commentThreshold = self._config.getInt('crawl', 'commentThreshold', 20)
        refactored = len(comments) < commentThreshold
        if refactored:
            usedStrategy = self._strategy.refactored()
            self.stageDetail.emit(
                'refactor',
                f'评论数 {len(comments)} 低于阈值 {commentThreshold}，已维度重构为 '
                f'{len(usedStrategy.dimensions)} 个强调维度',
            )
        else:
            usedStrategy = self._strategy.normalized()

        # 环节 4：LLM 并发打分
        self.stageChanged.emit('score')

        def onScoreProgress(done: int, totalCount: int) -> None:
            self.scoreProgress.emit(done, totalCount)

        scores: list[CommentScore] = self._llmService.scoreComments(
            comments,
            usedStrategy,
            onProgress=onScoreProgress,
        )
        if self._stopRequested:
            return None

        # 环节 5：有效评论判定（置信度过滤 + 加权得分截尾）
        self.stageChanged.emit('filter')
        credibilityThreshold = self._config.getFloat('analysis', 'credibilityThreshold', 0.6)
        trimPercent = self._config.getFloat('analysis', 'trimPercent', 5.0)
        afterCredibility = aggregator.filterByCredibility(scores, credibilityThreshold)
        validScores = aggregator.trimExtremes(
            afterCredibility,
            usedStrategy.weightMap(),
            trimPercent,
        )
        self.filterStats.emit(
            {
                'total': len(scores),
                'afterCredibility': len(afterCredibility),
                'valid': len(validScores),
            },
        )

        # 修正因子介入
        validCommentThreshold = self._config.getInt('analysis', 'validCommentThreshold', 10)
        correctionFactor: float | None = None
        if len(validScores) < validCommentThreshold:
            self.stageDetail.emit(
                'filter',
                f'有效评论 {len(validScores)} 条低于阈值 {validCommentThreshold}，等待修正因子介入',
            )
            self.correctionRequired.emit(len(validScores), validCommentThreshold)
            if not self._correctionEvent.wait(timeout=self._correctionWaitSeconds):
                self.stageDetail.emit('filter', '等待修正因子超时，按不修正继续')
            elif self._correctionValue is not None:
                correctionFactor = max(0.0, min(1.0, self._correctionValue))

        # 环节 6：汇总出分
        self.stageChanged.emit('summarize')
        result = aggregator.aggregate(validScores, usedStrategy, correctionFactor)
        return {
            'goodsName': goodsName,
            'goodsUrl': self._goodsUrl,
            'strategyId': self._strategy.strategyId,
            'strategyName': self._strategy.name,
            'strategySnapshot': usedStrategy.toDict(),
            'refactored': refactored,
            'totalCommentCount': len(comments),
            'scoredCommentCount': len(scores),
            'validCommentCount': len(validScores),
            'credibilityThreshold': credibilityThreshold,
            'trimPercent': trimPercent,
            'correctionFactor': correctionFactor,
            'finalScore': result.finalScore,
            'dimensionAverages': result.dimensionAverages,
            'dimensionWeightedScores': result.dimensionWeightedScores,
            'intermediateData': [
                {'comment': item.comment, 'scores': dict(item.scores), 'credibility': item.credibility}
                for item in scores
            ],
        }
