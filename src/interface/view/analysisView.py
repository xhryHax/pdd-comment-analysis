from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.interface.model.strategyListItem import StrategyListItem
from src.interface.model.summaryContext import SummaryContext
from src.interface.tools.dimensionBar import DimensionBar
from src.interface.tools.stageBar import StageBar
from src.interface.viewModel.analysisViewModel import AnalysisViewModel
from src.work.analysisStrategy import AnalysisStrategy

# 环节顺序（与 StageBar.STAGE_LABELS 保持一致），用于进度条兜底
STAGE_ORDER: list[str] = ['login', 'crawl', 'refactor', 'score', 'filter', 'summarize', 'done']

# 右下角悬浮按钮与页面边缘的间距
FLOATING_BUTTON_MARGIN: int = 24

# 各环节进行中的第四行状态文本
STAGE_STATUS_TEXTS: dict[str, str] = {
    'login': '正在打开商品页面，如需登录请在浏览器中完成……',
    'crawl': '正在抓取评论，请稍候……',
    'refactor': '正在进行条数判断与维度重构……',
    'score': '正在调用 LLM 为评论打分，请稍候……',
    'filter': '正在进行有效评论判定……',
    'summarize': '正在汇总出分……',
}


class AnalysisView(QWidget):
    '''新建分析页：链接输入、分环节流程展示、修正因子与结果。'''

    aiSummaryRequested = Signal(object)
    resetRequested = Signal()

    def __init__(self, viewModel: AnalysisViewModel, parent: QWidget | None = None) -> None:
        '''初始化页面并绑定视图模型信号。

        Args:
            viewModel: 新建分析视图模型。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._dimensionBars: list[DimensionBar] = []
        self._buildUi()
        self._connectSignals()

    def _buildUi(self) -> None:
        '''构建页面布局。'''
        rootLayout = QVBoxLayout(self)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        contentWidget = QWidget()
        contentLayout = QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(4, 4, 12, 4)
        contentLayout.setSpacing(16)

        # 输入卡片
        inputCard = QFrame()
        inputCard.setProperty('card', 'true')
        inputLayout = QVBoxLayout(inputCard)
        inputLayout.setContentsMargins(20, 20, 20, 20)
        inputLayout.setSpacing(12)
        titleLabel = QLabel('新建分析')
        titleLabel.setProperty('headingLevel', '1')
        inputLayout.addWidget(titleLabel)
        hintLabel = QLabel('粘贴商品分享链接，选择分析策略后开始。分析过程将打开浏览器，请手动完成登录。')
        hintLabel.setProperty('caption', True)
        hintLabel.setWordWrap(True)
        inputLayout.addWidget(hintLabel)
        formLayout = QHBoxLayout()
        formLayout.setSpacing(10)
        self._urlEdit = QLineEdit()
        self._urlEdit.setPlaceholderText('https://mobile.yangkeduo.com/goods.html?goods_id=...')
        self._urlEdit.setMinimumHeight(40)
        self._urlEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._strategyCombo = QComboBox()
        self._strategyCombo.setMinimumHeight(40)
        # 限制策略下拉宽度，让链接输入框尽可能占据更多宽度
        self._strategyCombo.setMaximumWidth(240)
        self._strategyCombo.setMinimumContentsLength(8)
        self._startButton = QPushButton('开始分析')
        self._startButton.setProperty('variant', 'primary')
        self._startButton.setMinimumHeight(40)
        self._stopButton = QPushButton('停止')
        self._stopButton.setProperty('variant', 'danger')
        self._stopButton.setMinimumHeight(40)
        self._stopButton.setEnabled(False)
        self._resetButton = QPushButton('重置')
        self._resetButton.setProperty('variant', 'ghost')
        self._resetButton.setMinimumHeight(40)
        formLayout.addWidget(self._urlEdit, stretch=1)
        formLayout.addWidget(self._strategyCombo)
        formLayout.addWidget(self._startButton)
        formLayout.addWidget(self._stopButton)
        formLayout.addWidget(self._resetButton)
        inputLayout.addLayout(formLayout)
        contentLayout.addWidget(inputCard)

        # 环节条
        self._stageBar = StageBar()
        contentLayout.addWidget(self._stageBar)

        # 环节详情卡片
        detailCard = QFrame()
        detailCard.setProperty('card', 'soft')
        detailLayout = QGridLayout(detailCard)
        detailLayout.setContentsMargins(20, 20, 20, 20)
        detailLayout.setHorizontalSpacing(24)
        detailLayout.setVerticalSpacing(12)
        self._loginLabel = QLabel('等待开始')
        self._crawlLabel = QLabel('等待开始')
        self._scoreLabel = QLabel('等待开始')
        self._filterLabel = QLabel('等待开始')
        for chip in (self._loginLabel, self._crawlLabel, self._scoreLabel, self._filterLabel):
            chip.setProperty('stageChip', True)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._crawlBar = self._makeBar()
        self._scoreBar = self._makeBar()
        detailLayout.addWidget(self._stageCaption('登录'), 0, 0)
        detailLayout.addWidget(self._loginLabel, 1, 0)
        detailLayout.addWidget(self._stageCaption('抓取'), 0, 1)
        detailLayout.addWidget(self._crawlLabel, 1, 1)
        detailLayout.addWidget(self._crawlBar, 2, 1)
        detailLayout.addWidget(self._stageCaption('打分'), 0, 2)
        detailLayout.addWidget(self._scoreLabel, 1, 2)
        detailLayout.addWidget(self._scoreBar, 2, 2)
        detailLayout.addWidget(self._stageCaption('判定'), 0, 3)
        detailLayout.addWidget(self._filterLabel, 1, 3)
        for column in range(4):
            detailLayout.setColumnStretch(column, 1)
        self._statusLabel = QLabel('')
        self._statusLabel.setProperty('caption', True)
        detailLayout.addWidget(self._statusLabel, 3, 0, 1, 4)
        contentLayout.addWidget(detailCard)

        # 结果卡片
        self._resultCard = QFrame()
        self._resultCard.setProperty('card', 'true')
        resultLayout = QHBoxLayout(self._resultCard)
        resultLayout.setContentsMargins(20, 20, 20, 20)
        resultLayout.setSpacing(28)
        scoreLayout = QVBoxLayout()
        self._finalScoreLabel = QLabel('--')
        self._finalScoreLabel.setProperty('headingLevel', 'display')
        self._finalScoreLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._finalScoreTitle = QLabel('商品质量分')
        self._finalScoreTitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._finalScoreTitle.setProperty('eyebrow', True)
        scoreLayout.addStretch(1)
        scoreLayout.addWidget(self._finalScoreLabel)
        scoreLayout.addWidget(self._finalScoreTitle)
        scoreLayout.addStretch(1)
        resultLayout.addLayout(scoreLayout)
        self._dimensionsHost = QWidget()
        self._dimensionsLayout = QVBoxLayout(self._dimensionsHost)
        self._dimensionsLayout.setContentsMargins(0, 0, 0, 0)
        self._dimensionsLayout.setSpacing(10)
        resultLayout.addWidget(self._dimensionsHost, stretch=1)
        self._resultCard.setVisible(False)
        contentLayout.addWidget(self._resultCard)
        contentLayout.addStretch(1)
        scrollArea.setWidget(contentWidget)
        rootLayout.addWidget(scrollArea)
        self._buildFloatingSummaryButton()

    def _buildFloatingSummaryButton(self) -> None:
        '''构建钉在页面右下角的 AI 智能总结按钮（不随内容滚动）。'''
        self._aiSummaryButton = QPushButton('AI 智能总结', self)
        self._aiSummaryButton.setProperty('variant', 'accent')
        self._aiSummaryButton.setProperty('floating', True)
        self._aiSummaryButton.setMinimumHeight(44)
        self._aiSummaryButton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._relocateFloatingButton()

    def _relocateFloatingButton(self) -> None:
        '''按当前页面尺寸把悬浮按钮摆到右下角。'''
        button = self._aiSummaryButton
        size = button.sizeHint()
        x = max(0, self.width() - size.width() - FLOATING_BUTTON_MARGIN)
        y = max(0, self.height() - size.height() - FLOATING_BUTTON_MARGIN)
        button.setGeometry(x, y, size.width(), size.height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt 覆写命名
        '''页面尺寸变化时同步悬浮按钮位置。

        Args:
            event: Qt 尺寸变化事件。
        '''
        super().resizeEvent(event)
        self._relocateFloatingButton()

    def _makeBar(self) -> QProgressBar:
        '''创建进度条并隐藏文本。'''
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(0)
        return bar

    @staticmethod
    def _stageCaption(text: str) -> QLabel:
        '''构建环节小标题。'''
        label = QLabel(text)
        label.setProperty('stageCaption', True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _connectSignals(self) -> None:
        '''连接视图模型信号到界面更新槽。'''
        vm = self._viewModel
        vm.stageChanged.connect(self._stageBar.setStage)
        vm.stageChanged.connect(self._onStageChanged)
        vm.stageDetail.connect(self._onStageDetail)
        vm.loginWaiting.connect(self._onLoginWaiting)
        vm.crawlProgress.connect(self._onCrawlProgress)
        vm.scoreProgress.connect(self._onScoreProgress)
        vm.filterStats.connect(self._onFilterStats)
        vm.correctionRequired.connect(self._onCorrectionRequired)
        vm.analysisFinished.connect(self._onFinished)
        vm.analysisFailed.connect(self._onFailed)
        self._startButton.clicked.connect(self._onStartClicked)
        self._stopButton.clicked.connect(self._viewModel.stop)
        self._aiSummaryButton.clicked.connect(self._onAiSummaryClicked)
        self._resetButton.clicked.connect(self._onResetClicked)

    # ---------- 策略 ----------

    def setStrategyItems(self, items: list[StrategyListItem]) -> None:
        '''注入策略列表（由主窗口协调刷新）。'''
        self._strategyCombo.clear()
        self._strategyItems = list(items)
        for item in items:
            self._strategyCombo.addItem(f'{item.strategy.name}（{item.sourceLabel}）')
        self._strategyCombo.setEnabled(self._strategyCombo.count() > 0)

    def selectedStrategy(self) -> AnalysisStrategy | None:
        '''返回当前选中的策略。'''
        index = self._strategyCombo.currentIndex()
        if 0 <= index < len(getattr(self, '_strategyItems', [])):
            return self._strategyItems[index].strategy
        return None

    # ---------- 交互 ----------

    def _onStartClicked(self) -> None:
        '''开始分析按钮点击。'''
        url = self._urlEdit.text().strip()
        if not url:
            QMessageBox.warning(self, '提示', '请先输入商品分享链接')
            return
        strategy = self.selectedStrategy()
        if strategy is None:
            QMessageBox.warning(self, '提示', '没有可用的分析策略，请先在策略管理页创建')
            return
        self._resetFlow()
        try:
            self._viewModel.start(url, strategy)
        except RuntimeError as error:
            QMessageBox.warning(self, '提示', str(error))
            return
        self._startButton.setEnabled(False)
        self._stopButton.setEnabled(True)
        self._statusLabel.setText('分析已启动，正在打开浏览器……')

    def _onAiSummaryClicked(self) -> None:
        '''AI 智能总结按钮点击：请求打开总结弹窗。'''
        context = self._viewModel.summaryContext(self._urlEdit.text().strip())
        if not context.goodsUrl and not context.hasData:
            QMessageBox.information(self, '提示', '请先输入商品链接并完成一次分析，或从“分析记录”页选择记录')
            return
        self.aiSummaryRequested.emit(context)

    def _onResetClicked(self) -> None:
        '''重置按钮点击：清空当前输入与全部分析结果展示。'''
        self._urlEdit.clear()
        self._resetFlow()
        self._statusLabel.setText('')
        self._setRunningUi(False)
        self.resetRequested.emit()

    def _resetFlow(self) -> None:
        '''重置流程展示。'''
        self._stageBar.reset()
        self._resultCard.setVisible(False)
        self._crawlBar.setValue(0)
        self._scoreBar.setValue(0)
        for label in (self._loginLabel, self._crawlLabel, self._scoreLabel, self._filterLabel, self._statusLabel):
            label.setText('等待开始')

    def _setRunningUi(self, running: bool) -> None:
        '''更新运行态按钮。'''
        self._startButton.setEnabled(not running)
        self._stopButton.setEnabled(running)

    def _onLoginWaiting(self) -> None:
        '''登录等待提示。'''
        self._loginLabel.setText('等待用户在浏览器中登录……')
        self._statusLabel.setText('请扫描二维码或手动登录，登录完成后流程自动继续')

    def _onStageChanged(self, stageKey: str) -> None:
        '''环节切换：更新第四行状态文本，并为已完成环节的进度条兜底置满。

        Args:
            stageKey: 环节键（login/crawl/refactor/score/filter/
                summarize/done）。
        '''
        statusText = STAGE_STATUS_TEXTS.get(stageKey)
        if statusText is not None:
            self._statusLabel.setText(statusText)
        if stageKey not in STAGE_ORDER:
            return
        stageIndex = STAGE_ORDER.index(stageKey)
        if stageIndex > STAGE_ORDER.index('crawl'):
            # 进入抓取之后的环节时，强制抓取进度条到达 100%
            self._crawlBar.setValue(100)
        if stageIndex > STAGE_ORDER.index('score'):
            # 进入打分之后的环节时，强制打分进度条到达 100%
            self._scoreBar.setValue(100)

    def _onStageDetail(self, stageKey: str, message: str) -> None:
        '''环节详情更新。'''
        mapping = {
            'login': self._loginLabel,
            'crawl': self._crawlLabel,
            'refactor': self._statusLabel,
            'score': self._scoreLabel,
            'filter': self._filterLabel,
            'summarize': self._statusLabel,
        }
        target = mapping.get(stageKey)
        if target is not None:
            target.setText(message)

    def _onCrawlProgress(self, fetched: int, total: int) -> None:
        '''抓取进度更新。'''
        self._crawlLabel.setText(f'已抓取 {fetched} 条评论')
        if total > 0:
            self._crawlBar.setValue(min(100, int(fetched * 100 / total)))

    def _onScoreProgress(self, done: int, total: int) -> None:
        '''打分进度更新。'''
        self._scoreLabel.setText(f'LLM 打分 {done}/{total} 条')
        if total > 0:
            self._scoreBar.setValue(min(100, int(done * 100 / total)))

    def _onFilterStats(self, stats: dict) -> None:
        '''筛选统计更新。'''
        self._filterLabel.setText(
            f'共 {stats.get('total', 0)} 条 · 置信度过滤后 {stats.get('afterCredibility', 0)} 条'
            f' · 截尾后有效 {stats.get('valid', 0)} 条',
        )

    def _onCorrectionRequired(self, validCount: int, threshold: int) -> None:
        '''修正因子介入弹窗。'''
        dialog = CorrectionDialog(self, validCount, threshold)
        if dialog.exec() and dialog.resultValue is not None:
            self._viewModel.provideCorrectionFactor(dialog.resultValue)
        else:
            self._viewModel.provideCorrectionFactor(None)

    def _onFinished(self, payload: dict[str, Any]) -> None:
        '''分析完成：展示结果。'''
        self._setRunningUi(False)
        finalScore = float(payload.get('finalScore', 0.0))
        self._finalScoreLabel.setText(f'{finalScore:.0f}')
        refactored = payload.get('refactored', False)
        self._finalScoreTitle.setText('商品质量分（已维度重构）' if refactored else '商品质量分')
        for bar in self._dimensionBars:
            self._dimensionsLayout.removeWidget(bar)
            bar.deleteLater()
        self._dimensionBars = []
        snapshot = payload.get('strategySnapshot') or {}
        averages: dict = payload.get('dimensionAverages') or {}
        for dimension in snapshot.get('dimensions', []):
            bar = DimensionBar(str(dimension.get('name', '')))
            bar.setValues(
                str(dimension.get('name', '')),
                averages.get(dimension.get('name')),
                float(dimension.get('weight', 0.0)),
            )
            self._dimensionsLayout.addWidget(bar)
            self._dimensionBars.append(bar)
        self._resultCard.setVisible(True)
        recordId = payload.get('recordId')
        recordSuffix = f'（记录 #{recordId}）' if recordId else ''
        self._statusLabel.setText(f'分析完成，最终得分 {finalScore:.2f}{recordSuffix}')

    def _onFailed(self, message: str) -> None:
        '''分析失败提示。'''
        self._setRunningUi(False)
        self._statusLabel.setText(f'分析失败：{message}')
        QMessageBox.critical(self, '分析失败', message)


class CorrectionDialog(QMessageBox):
    '''修正因子输入弹窗（含 0-1 微调框）。'''

    def __init__(self, parent, validCount: int, threshold: int) -> None:
        '''初始化弹窗。

        Args:
            parent: 父窗口。
            validCount: 当前有效评论条数。
            threshold: 有效评论阈值。
        '''
        super().__init__(parent)
        self.resultValue: float | None = None
        self.setWindowTitle('修正因子介入')
        self.setText(
            f'有效评论仅 {validCount} 条（低于阈值 {threshold} 条），'
            '数据不足以完全支撑分析。\n请输入 0-1 的修正因子（表示对结果的信任程度），'
            '取消则按不修正继续。',
        )
        self.spin = QDoubleSpinBox(self)
        self.spin.setRange(0.0, 1.0)
        self.spin.setSingleStep(0.05)
        self.spin.setValue(0.8)
        self.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        self.setDefaultButton(QMessageBox.StandardButton.Ok)
        self.textBox = self.layout()
        if self.textBox is not None:
            self.textBox.addWidget(self.spin, 1, 1)

    def accept(self) -> None:
        '''确定时记录修正因子。'''
        self.resultValue = self.spin.value()
        super().accept()
