from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

from src.data.configAccess import ConfigAccess
from src.data.database import Database
from src.interface.model.summaryContext import SummaryContext
from src.work.aiSummaryService import AiSummaryService

logger = logging.getLogger(__name__)


class AiSummaryWorker(QThread):
    '''后台执行 AI 总结问答的线程。'''

    answerSucceeded = Signal(str)
    answerFailed = Signal(str)

    def __init__(
        self,
        service: AiSummaryService,
        context: SummaryContext,
        history: list[dict],
        question: str,
        parent: QObject | None = None,
    ) -> None:
        '''初始化问答线程。

        Args:
            service: AI 总结服务。
            context: 注入数据上下文。
            history: 历史对话（按时间正序）。
            question: 用户本轮提问。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._service = service
        self._context = context
        self._history = history
        self._question = question

    def run(self) -> None:
        '''执行问答并广播结果（勿直接调用）。'''
        try:
            answer = self._service.ask(self._context, self._history, self._question)
        except Exception as error:  # noqa: BLE001 - 顶层兜底
            self.answerFailed.emit(str(error))
        else:
            self.answerSucceeded.emit(answer)


class AiSummaryViewModel(QObject):
    '''AI 智能总结视图模型：上下文切换、多轮问答与对话持久化。

    以商品链接（goodsUrl）作为不同分析记录的唯一识别码，同一链接下
    的问答按轮追加存储；每轮请求将注入数据与历史对话一并提交。
    '''

    contextChanged = Signal(object)
    historyChanged = Signal(object)
    answerStarted = Signal()
    answerSucceeded = Signal(str)
    answerFailed = Signal(str)
    statusChanged = Signal(str)

    def __init__(
        self,
        config: ConfigAccess,
        database: Database,
        parent: QObject | None = None,
    ) -> None:
        '''初始化视图模型。

        Args:
            config: 系统配置读写器。
            database: 数据库仓储（对话记录）。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._config = config
        self._database = database
        self._service = AiSummaryService(config)
        self._worker: AiSummaryWorker | None = None
        self._context: SummaryContext | None = None
        self._history: list[dict] = []
        self._pendingQuestion = ''

    @property
    def context(self) -> SummaryContext | None:
        '''当前注入数据上下文。'''
        return self._context

    @property
    def history(self) -> list[dict]:
        '''当前商品的对话历史（按时间正序）。'''
        return self._history

    @property
    def isAnswering(self) -> bool:
        '''是否正在等待 LLM 回答。'''
        if self._worker is None:
            return False
        try:
            return self._worker.isRunning()
        except RuntimeError:
            # C++ 对象已被删除（线程结束并清理）的兜底
            self._worker = None
            return False

    def setContext(self, context: SummaryContext | None) -> None:
        '''切换注入数据上下文并重新加载该商品的对话历史。

        Args:
            context: 新的上下文；None 表示清空。
        '''
        if context is None:
            self.clearContext()
            return
        self._context = context
        self.refreshHistory()
        goodsName = context.goodsName or '（未命名商品）'
        logger.info('AI 总结上下文已切换：%s（recordId=%s）', goodsName, context.recordId)
        if not context.hasData:
            self.statusChanged.emit('当前没有可注入的分析数据，请先完成一次分析或从记录中选择记录')
        self.contextChanged.emit(self._context)

    def clearContext(self) -> None:
        '''清空上下文与对话历史（不删除数据库内容）。'''
        self._context = None
        self._history = []
        self.historyChanged.emit([])
        self.contextChanged.emit(None)
        self.statusChanged.emit('未选择分析数据')

    def refreshHistory(self) -> None:
        '''按当前上下文的商品链接重新加载对话历史。'''
        if self._context is None or not self._context.goodsUrl:
            self._history = []
            self.historyChanged.emit(self._history)
            return
        self._history = self._database.listAiSummaries(self._context.goodsUrl)
        self.historyChanged.emit(self._history)

    def sendQuestion(self, question: str) -> None:
        '''提交一轮提问（后台请求 LLM 并持久化结果）。

        Args:
            question: 用户提问文本。
        '''
        question = question.strip()
        if self._context is None:
            self.answerFailed.emit('未指定注入数据上下文，无法发起提问')
            return
        if not question:
            self.answerFailed.emit('提问内容不能为空')
            return
        if self.isAnswering:
            self.answerFailed.emit('上一次提问仍在生成中，请稍候')
            return
        self._pendingQuestion = question
        self.answerStarted.emit()
        self.statusChanged.emit('AI 正在生成回答……')
        worker = AiSummaryWorker(
            self._service,
            self._context,
            list(self._history),
            question,
        )
        self._worker = worker
        worker.answerSucceeded.connect(self._onAnswerSucceeded)
        worker.answerFailed.connect(self.answerFailed)
        # 线程结束后：先清空引用再释放 C++ 对象，
        # 否则残留的包装指针会让 isAnswering 抛 RuntimeError
        worker.finished.connect(lambda w=worker: self._onWorkerFinished(w))
        worker.start()

    def _onAnswerSucceeded(self, answer: str) -> None:
        '''回答成功：落库后刷新历史。

        Args:
            answer: LLM 回答文本。
        '''
        context = self._context
        if context is not None and context.goodsUrl:
            try:
                self._database.saveAiSummary(
                    context.goodsUrl,
                    context.recordId,
                    self._pendingQuestion,
                    answer,
                )
            except Exception as error:  # noqa: BLE001 - 落库失败不影响展示本轮结果
                logger.error('AI 总结对话保存失败：%s', error)
                self.statusChanged.emit(f'AI 总结已生成，但保存失败：{error}')
            else:
                self.statusChanged.emit('AI 总结已生成并保存')
        else:
            self.statusChanged.emit('AI 总结已生成，但缺少商品链接未保存')
        self._pendingQuestion = ''
        self.refreshHistory()
        self.answerSucceeded.emit(answer)

    def _onWorkerFinished(self, worker: AiSummaryWorker) -> None:
        '''问答线程结束：清理引用并释放线程对象。

        Args:
            worker: 刚结束的问答线程。
        '''
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
