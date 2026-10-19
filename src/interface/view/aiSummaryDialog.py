from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.interface.model.summaryContext import SummaryContext
from src.interface.viewModel.aiSummaryViewModel import AiSummaryViewModel

# 未选择分析数据 / 无对话时展示的占位文案
EMPTY_HINT = '当前没有可注入的分析数据。\n请先完成一次分析，或在“分析记录”页选择一条记录。'
WAITING_HINT = '_AI 正在生成回答……_'

# 气泡宽度占可视区宽度的比例
BUBBLE_WIDTH_RATIO: float = 0.72
# 用户气泡最小宽度（短提问不至于过窄）
BUBBLE_MIN_WIDTH: int = 96
# AI 气泡最小宽度：短回答（如“好的”）也保持可读宽度
AI_BUBBLE_MIN_WIDTH: int = 180
# AI 气泡最大宽度：宽屏下避免单行过长影响阅读
AI_BUBBLE_MAX_WIDTH: int = 640


class MarkdownBubble(QTextBrowser):
    '''单条 AI 回答气泡：以 Markdown 渲染并自适应尺寸。

    宽度取自然宽度与可用上限的较小值，高度由文档实际高度决定；
    禁用内嵌滚动条，由外层滚动区统一滚动。
    '''

    def __init__(self, parent: QWidget | None = None) -> None:
        '''初始化气泡。

        Args:
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self.setProperty('bubble', 'ai')
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        document = self.document()
        document.setDocumentMargin(10)
        # 注：PySide6 6.11 中 QTextDocument.setMarkdown 默认即 GitHub
        # 方言（含表格等扩展），且未暴露 setMarkdownFeatures，
        # 因此此处无需显式指定方言

    def setMarkdownText(self, text: str, maxWidth: int) -> None:
        '''设置 Markdown 内容并按可用宽度重排尺寸。

        Args:
            text: Markdown 文本。
            maxWidth: 气泡可用最大宽度。
        '''
        self.setMarkdown(text)
        self.applyWidth(maxWidth)

    def applyWidth(self, maxWidth: int) -> None:
        '''按可用宽度重新计算气泡宽高，宽度收敛到 AI 气泡的上下限之间。

        宽度取值顺序：先用上限排版得到换行尺寸，再取自然宽度与上限的
        较小值；最后用 AI_BUBBLE_MIN_WIDTH / AI_BUBBLE_MAX_WIDTH 夹紧，
        短回答不至于过窄、宽屏下也不至于单行过长。

        Args:
            maxWidth: 气泡可用最大宽度（含文档边距）。
        '''
        # 上限：可视区宽度与绝对上限取小
        limit = min(maxWidth, AI_BUBBLE_MAX_WIDTH)
        # 下限：可视区过窄时退化为可用宽度，避免溢出滚动区
        floor = min(AI_BUBBLE_MIN_WIDTH, limit)
        document = self.document()
        document.setTextWidth(limit)
        idealWidth = int(document.idealWidth())
        width = max(floor, min(idealWidth, limit))
        document.setTextWidth(width)
        self.setFixedWidth(width + 2)
        self.setFixedHeight(int(document.size().height()) + 2)


class AiSummaryDialog(QDialog):
    '''AI 智能总结弹窗（非模态）：气泡式多轮问答界面。

    用户消息显示为右侧气泡，AI 回答显示为左侧气泡并以 Markdown 渲染；
    每次提问会把分析策略、中间数据、修正因子与汇总结果一并注入后请求 LLM。
    '''

    def __init__(self, viewModel: AiSummaryViewModel, parent: QWidget | None = None) -> None:
        '''初始化弹窗。

        Args:
            viewModel: AI 总结视图模型。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._aiBubbles: list[MarkdownBubble] = []
        self._userBubbles: list[QLabel] = []
        self.setWindowTitle('AI 智能总结')
        self.resize(760, 600)
        self.setMinimumSize(560, 440)
        self._buildUi()
        self._connectSignals()
        self._syncContext(self._viewModel.context)
        self._renderHistory(self._viewModel.history)

    def _buildUi(self) -> None:
        '''构建弹窗布局。'''
        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(20, 20, 20, 20)
        rootLayout.setSpacing(12)

        titleLabel = QLabel('AI 智能总结')
        titleLabel.setProperty('headingLevel', '1')
        rootLayout.addWidget(titleLabel)

        self._contextLabel = QLabel('未选择分析数据')
        self._contextLabel.setProperty('caption', True)
        self._contextLabel.setWordWrap(True)
        rootLayout.addWidget(self._contextLabel)

        self._scrollArea = QScrollArea()
        self._scrollArea.setWidgetResizable(True)
        self._scrollArea.setFrameShape(QScrollArea.Shape.NoFrame)
        self._chatHost = QWidget()
        self._chatLayout = QVBoxLayout(self._chatHost)
        self._chatLayout.setContentsMargins(6, 6, 6, 6)
        self._chatLayout.setSpacing(12)
        self._emptyHintLabel = QLabel(EMPTY_HINT)
        self._emptyHintLabel.setProperty('caption', True)
        self._emptyHintLabel.setWordWrap(True)
        self._emptyHintLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 对话区固有结构：空态提示 + 末尾弹簧（消息行插在弹簧之前）
        self._chatLayout.addWidget(self._emptyHintLabel)
        self._chatLayout.addStretch(1)
        self._scrollArea.setWidget(self._chatHost)
        rootLayout.addWidget(self._scrollArea, stretch=1)

        self._questionEdit = QTextEdit()
        self._questionEdit.setPlaceholderText(
            '输入你的问题，按 Ctrl+Enter 发送（数据不足时 AI 会直接说明）……',
        )
        self._questionEdit.setMinimumHeight(88)
        self._questionEdit.installEventFilter(self)
        rootLayout.addWidget(self._questionEdit)

        bottomLayout = QHBoxLayout()
        bottomLayout.setSpacing(8)
        self._statusLabel = QLabel('就绪')
        self._statusLabel.setProperty('caption', True)
        bottomLayout.addWidget(self._statusLabel, stretch=1)
        self._sendButton = QPushButton('发送')
        self._sendButton.setProperty('variant', 'primary')
        self._clearButton = QPushButton('清空输入')
        self._clearButton.setProperty('variant', 'ghost')
        self._closeButton = QPushButton('关闭')
        self._closeButton.setProperty('variant', 'ghost')
        bottomLayout.addWidget(self._sendButton)
        bottomLayout.addWidget(self._clearButton)
        bottomLayout.addWidget(self._closeButton)
        rootLayout.addLayout(bottomLayout)

    def _connectSignals(self) -> None:
        '''绑定视图模型信号。'''
        vm = self._viewModel
        vm.contextChanged.connect(self._syncContext)
        vm.historyChanged.connect(self._renderHistory)
        vm.answerStarted.connect(self._onAnswerStarted)
        vm.answerSucceeded.connect(self._onAnswerSucceeded)
        vm.answerFailed.connect(self._onAnswerFailed)
        vm.statusChanged.connect(self._statusLabel.setText)
        self._sendButton.clicked.connect(self._onSendClicked)
        self._clearButton.clicked.connect(self._questionEdit.clear)
        self._closeButton.clicked.connect(self.reject)

    # ---------- 展示 ----------

    def _syncContext(self, context: SummaryContext | None) -> None:
        '''上下文变化时刷新标题区信息。

        Args:
            context: 新的注入数据上下文。
        '''
        if context is None:
            self.setWindowTitle('AI 智能总结')
            self._contextLabel.setText('未选择分析数据')
            self._sendButton.setEnabled(False)
            self._updateEmptyHint(EMPTY_HINT)
            return
        goodsName = context.goodsName or '（未命名商品）'
        strategyName = str(context.strategySnapshot.get('name', '（无）'))
        dimensionCount = len(context.strategySnapshot.get('dimensions') or [])
        self.setWindowTitle(f'AI 智能总结 · {goodsName}')
        factorText = '未介入' if context.correctionFactor is None else f'{context.correctionFactor:.2f}'
        self._contextLabel.setText(
            f'商品：{goodsName} · 记录 #{context.recordId or '—'}\n'
            f'注入数据：分析策略「{strategyName}」（{dimensionCount} 个维度'
            f'{"，已维度重构" if context.refactored else ''}） · 中间数据 '
            f'{len(context.intermediateData)} 条 · 修正因子 {factorText} · '
            f'汇总得分 {context.finalScore:.2f}',
        )
        self._sendButton.setEnabled(True)
        self._updateEmptyHint('暂无对话，输入问题即可基于上述注入数据进行提问。')

    def _updateEmptyHint(self, text: str) -> None:
        '''刷新空态提示文案并按需显隐。

        Args:
            text: 提示文本。
        '''
        hasBubble = bool(self._aiBubbles or self._userBubbles)
        self._emptyHintLabel.setVisible(not hasBubble)
        self._emptyHintLabel.setText(text)

    def availableBubbleWidth(self) -> int:
        '''返回气泡可用最大宽度。

        Returns:
            int: 按可视区宽度折算的气泡宽度上限（像素）。
        '''
        viewportWidth = self._scrollArea.viewport().width()
        if viewportWidth <= 0:
            viewportWidth = self.width()
        return max(BUBBLE_MIN_WIDTH, int(viewportWidth * BUBBLE_WIDTH_RATIO))

    def aiBubbleWidthLimit(self) -> int:
        '''返回 AI 气泡的宽度上限（可视区比例与绝对上限取小）。

        Returns:
            int: AI 气泡宽度上限（像素）。
        '''
        return min(self.availableBubbleWidth(), AI_BUBBLE_MAX_WIDTH)

    def _resetChatArea(self) -> None:
        '''清空全部消息，恢复“空态提示 + 末尾弹簧”结构。'''
        self._aiBubbles = []
        self._userBubbles = []
        while self._chatLayout.count():
            item = self._chatLayout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._emptyHintLabel:
                widget.deleteLater()
        self._chatLayout.addWidget(self._emptyHintLabel)
        self._chatLayout.addStretch(1)

    def _addRow(self, bubbleWidget: QWidget, isUser: bool) -> None:
        '''向对话区追加一条消息（用户靠右，AI 靠左）。

        Args:
            bubbleWidget: 气泡本体控件。
            isUser: 是否为用户消息。
        '''
        rowWidget = QWidget(self._chatHost)
        rowLayout = QHBoxLayout(rowWidget)
        rowLayout.setContentsMargins(0, 0, 0, 0)
        rowLayout.setSpacing(0)
        if isUser:
            rowLayout.addStretch(1)
            rowLayout.addWidget(bubbleWidget)
        else:
            rowLayout.addWidget(bubbleWidget)
            rowLayout.addStretch(1)
        # 插在末尾弹簧之前，保证消息顶部对齐
        self._chatLayout.insertWidget(self._chatLayout.count() - 1, rowWidget)

    def _addUserBubble(self, text: str) -> None:
        '''追加一条用户气泡（右侧）。

        Args:
            text: 用户提问文本。
        '''
        label = QLabel(text)
        label.setProperty('bubble', 'user')
        label.setWordWrap(True)
        label.setMaximumWidth(self.availableBubbleWidth())
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._addRow(label, isUser=True)
        self._userBubbles.append(label)

    def _addAiBubble(self, markdownText: str) -> None:
        '''追加一条 AI 气泡（左侧，Markdown 渲染）。

        Args:
            markdownText: Markdown 文本。
        '''
        bubble = MarkdownBubble(self._chatHost)
        bubble.setMarkdownText(markdownText, self.aiBubbleWidthLimit())
        self._addRow(bubble, isUser=False)
        self._aiBubbles.append(bubble)

    def _renderHistory(self, history: list[dict]) -> None:
        '''渲染对话历史为气泡。

        Args:
            history: 对话字典列表（question / answer / createdAt）。
        '''
        self._resetChatArea()
        for turn in history:
            self._addUserBubble(str(turn.get('question', '')))
            self._addAiBubble(str(turn.get('answer', '')))
        self._updateEmptyHint('暂无对话，输入问题即可基于上述注入数据进行提问。')
        # 首次渲染时滚动区尚未完成布局，宽度按最终可见宽度再校正一次
        QTimer.singleShot(0, self._relayoutBubbles)
        self._scrollToBottom()

    def showEvent(self, event: object) -> None:  # noqa: N802 - Qt 覆写命名
        '''弹窗显示时按真实可视区宽度校正气泡尺寸。

        Args:
            event: Qt 显示事件。
        '''
        super().showEvent(event)  # type: ignore[arg-type]
        self._relayoutBubbles()

    def _relayoutBubbles(self) -> None:
        '''弹窗尺寸变化时重算气泡宽度与高度。'''
        aiWidthLimit = self.aiBubbleWidthLimit()
        for userLabel in self._userBubbles:
            userLabel.setMaximumWidth(self.availableBubbleWidth())
        for bubble in self._aiBubbles:
            bubble.applyWidth(aiWidthLimit)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt 覆写命名
        '''弹窗尺寸变化时重排气泡。

        Args:
            event: Qt 尺寸变化事件。
        '''
        super().resizeEvent(event)
        self._relayoutBubbles()

    def _scrollToBottom(self) -> None:
        '''滚动到对话底部。'''
        scrollBar = self._scrollArea.verticalScrollBar()
        QTimer.singleShot(0, lambda: scrollBar.setValue(scrollBar.maximum()))

    # ---------- 交互 ----------

    def _onSendClicked(self) -> None:
        '''发送按钮点击：立即回填用户气泡与等待气泡。'''
        question = self._questionEdit.toPlainText().strip()
        if not question:
            QMessageBox.information(self, '提示', '请输入你的问题')
            return
        self._questionEdit.clear()
        self._addUserBubble(question)
        self._addAiBubble(WAITING_HINT)
        self._updateEmptyHint('')
        self._scrollToBottom()
        self._viewModel.sendQuestion(question)

    def eventFilter(self, watched: object, event: object) -> bool:  # type: ignore[override]
        '''拦截输入框按键：Ctrl+Enter 发送。

        Args:
            watched: 事件接收对象。
            event: Qt 事件对象。

        Returns:
            bool: 事件已处理返回 True，否则交由父类处理。
        '''
        if watched is self._questionEdit and isinstance(event, QKeyEvent):
            isEnter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            if isEnter and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._onSendClicked()
                return True
        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def _onAnswerStarted(self) -> None:
        '''AI 开始生成：禁用发送按钮。'''
        self._sendButton.setEnabled(False)

    def _onAnswerSucceeded(self, answer: str) -> None:
        '''AI 回答完成：恢复按钮（对话区由 historyChanged 全量重建）。

        Args:
            answer: 回答文本。
        '''
        self._sendButton.setEnabled(True)
        _ = answer

    def _onAnswerFailed(self, message: str) -> None:
        '''AI 回答失败：把等待气泡替换为错误提示并弹出警告。

        Args:
            message: 错误信息。
        '''
        self._sendButton.setEnabled(True)
        if self._aiBubbles:
            lastBubble = self._aiBubbles[-1]
            lastBubble.setMarkdownText(f'**生成失败：**{message}', self.aiBubbleWidthLimit())
        QMessageBox.warning(self, 'AI 智能总结失败', message)
        self._scrollToBottom()
