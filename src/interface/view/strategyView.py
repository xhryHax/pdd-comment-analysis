from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.interface.model.strategyListItem import StrategyListItem
from src.interface.viewModel.strategyViewModel import StrategyViewModel
from src.work.analysisStrategy import AnalysisStrategy, Dimension


class StrategyView(QWidget):
    '''策略管理页：策略列表、表单编辑与 AI 生成。'''

    def __init__(self, viewModel: StrategyViewModel, parent: QWidget | None = None) -> None:
        '''初始化页面并绑定视图模型。

        Args:
            viewModel: 策略页视图模型。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._buildUi()
        self._connectSignals()
        self._reloadList()

    def _buildUi(self) -> None:
        '''构建页面布局。'''
        rootLayout = QHBoxLayout(self)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(16)

        # 左：策略列表 + AI 生成
        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.setSpacing(10)
        titleLabel = QLabel('策略管理')
        titleLabel.setProperty('headingLevel', '1')
        leftLayout.addWidget(titleLabel)
        self._newButton = QPushButton('＋ 新建策略')
        self._newButton.setProperty('variant', 'ghost')
        leftLayout.addWidget(self._newButton)
        self._listWidget = QListWidget()
        self._listWidget.setMinimumWidth(260)
        leftLayout.addWidget(self._listWidget, stretch=1)
        aiCard = QFrame()
        aiCard.setProperty('card', 'soft')
        aiLayout = QVBoxLayout(aiCard)
        aiLayout.setContentsMargins(16, 16, 16, 16)
        aiLayout.setSpacing(8)
        aiTitle = QLabel('AI 生成策略')
        aiTitle.setProperty('headingLevel', '2')
        aiLayout.addWidget(aiTitle)
        aiHint = QLabel('用一句话描述品类与关注点，例如“为机械键盘设计分析策略，重点关注手感和耐用性”。')
        aiHint.setProperty('caption', True)
        aiHint.setWordWrap(True)
        aiLayout.addWidget(aiHint)
        self._aiRequirementEdit = QLineEdit()
        self._aiRequirementEdit.setPlaceholderText('输入你的需求……')
        aiLayout.addWidget(self._aiRequirementEdit)
        self._aiGenerateButton = QPushButton('生成策略')
        self._aiGenerateButton.setProperty('variant', 'accent')
        aiLayout.addWidget(self._aiGenerateButton)
        leftLayout.addWidget(aiCard)
        rootLayout.addWidget(leftPanel, stretch=2)

        # 右：编辑表单
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        formHost = QWidget()
        formLayout = QVBoxLayout(formHost)
        formLayout.setContentsMargins(4, 4, 8, 4)
        formLayout.setSpacing(12)

        rowLayout = QHBoxLayout()
        self._nameEdit = QLineEdit()
        self._nameEdit.setPlaceholderText('策略名称（如：显示器）')
        nameLabel = QLabel('策略名')
        nameLabel.setProperty('eyebrow', True)
        rowLayout.addWidget(nameLabel)
        rowLayout.addWidget(self._nameEdit, stretch=1)
        formLayout.addLayout(rowLayout)

        dimensionLabel = QLabel('维度（名称 / 含义描述 / 权重 / 是否强调）')
        dimensionLabel.setProperty('eyebrow', True)
        formLayout.addWidget(dimensionLabel)
        self._dimensionTable = QTableWidget(0, 4)
        self._dimensionTable.setHorizontalHeaderLabels(['名称', '含义描述', '权重', '强调'])
        self._dimensionTable.verticalHeader().setVisible(False)
        self._dimensionTable.verticalHeader().setDefaultSectionSize(40)
        header = self._dimensionTable.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._dimensionTable.setColumnWidth(0, 150)
        self._dimensionTable.setColumnWidth(2, 96)
        self._dimensionTable.setColumnWidth(3, 96)
        formLayout.addWidget(self._dimensionTable)
        dimensionButtonRow = QHBoxLayout()
        self._addDimensionButton = QPushButton('＋ 添加维度')
        self._addDimensionButton.setProperty('variant', 'ghost')
        self._removeDimensionButton = QPushButton('－ 删除选中维度')
        self._removeDimensionButton.setProperty('variant', 'danger')
        self._weightSumLabel = QLabel('权重总和：--')
        self._weightSumLabel.setProperty('caption', True)
        dimensionButtonRow.addWidget(self._addDimensionButton)
        dimensionButtonRow.addWidget(self._removeDimensionButton)
        dimensionButtonRow.addStretch(1)
        dimensionButtonRow.addWidget(self._weightSumLabel)
        formLayout.addLayout(dimensionButtonRow)

        ratingLabel = QLabel('评分提示词（ratingPrompt）')
        ratingLabel.setProperty('eyebrow', True)
        formLayout.addWidget(ratingLabel)
        self._ratingEdit = QTextEdit()
        self._ratingEdit.setFixedHeight(120)
        formLayout.addWidget(self._ratingEdit)
        credibilityLabel = QLabel('置信度提示词（credibilityPrompt）')
        credibilityLabel.setProperty('eyebrow', True)
        formLayout.addWidget(credibilityLabel)
        self._credibilityEdit = QTextEdit()
        self._credibilityEdit.setFixedHeight(100)
        formLayout.addWidget(self._credibilityEdit)

        actionRow = QHBoxLayout()
        self._saveButton = QPushButton('保存策略')
        self._saveButton.setProperty('variant', 'primary')
        self._deleteButton = QPushButton('删除自建策略')
        self._deleteButton.setProperty('variant', 'danger')
        self._selectedIdLabel = QLabel('')
        self._selectedIdLabel.setProperty('caption', True)
        actionRow.addWidget(self._saveButton)
        actionRow.addWidget(self._deleteButton)
        actionRow.addStretch(1)
        actionRow.addWidget(self._selectedIdLabel)
        formLayout.addLayout(actionRow)
        formLayout.addStretch(1)
        scrollArea.setWidget(formHost)
        rootLayout.addWidget(scrollArea, stretch=3)

    def _connectSignals(self) -> None:
        '''绑定信号。'''
        self._viewModel.strategiesChanged.connect(self._reloadList)
        self._viewModel.aiGenerateSucceeded.connect(self._onAiGenerated)
        self._viewModel.aiGenerateFailed.connect(self._onAiFailed)
        self._listWidget.currentRowChanged.connect(self._onRowChanged)
        self._newButton.clicked.connect(self._onNewClicked)
        self._saveButton.clicked.connect(self._onSaveClicked)
        self._deleteButton.clicked.connect(self._onDeleteClicked)
        self._addDimensionButton.clicked.connect(self._addDimensionRow)
        self._removeDimensionButton.clicked.connect(self._removeSelectedDimension)
        self._aiGenerateButton.clicked.connect(self._onAiGenerateClicked)
        self._dimensionTable.itemChanged.connect(self._updateWeightSum)

    # ---------- 列表 ----------

    def _reloadList(self) -> None:
        '''重建策略列表。'''
        self._listWidget.blockSignals(True)
        self._listWidget.clear()
        for item in self._viewModel.items:
            listWidgetItem = QListWidgetItem(f'{item.strategy.name}（{item.sourceLabel}）')
            self._listWidget.addItem(listWidgetItem)
        self._listWidget.blockSignals(False)
        if self._viewModel.items:
            self._listWidget.setCurrentRow(0)

    def _onRowChanged(self, row: int) -> None:
        '''选中策略后填充表单。'''
        item = self._viewModel.itemAt(row)
        if item is None:
            return
        strategy = item.strategy
        self._nameEdit.setText(strategy.name)
        self._ratingEdit.setPlainText(strategy.ratingPrompt)
        self._credibilityEdit.setPlainText(strategy.credibilityPrompt)
        self._dimensionTable.setRowCount(0)
        for dimension in strategy.dimensions:
            self._appendDimensionRow(dimension)
        self._updateWeightSum()
        editable = item.sourceKind == 'user'
        self._saveButton.setEnabled(True)
        self._deleteButton.setEnabled(editable)
        self._selectedIdLabel.setText(
            f'当前：{strategy.strategyId}（{item.sourceLabel}）'
            if editable
            else f'当前：{strategy.strategyId}（默认策略，保存为自建副本）',
        )

    # ---------- 编辑 ----------

    def _onNewClicked(self) -> None:
        '''新建空白策略表单。'''
        self._nameEdit.clear()
        self._ratingEdit.clear()
        self._credibilityEdit.clear()
        self._dimensionTable.setRowCount(0)
        self._appendDimensionRow(Dimension(name='', description='', weight=1.0, emphasized=True))
        self._selectedIdLabel.setText('当前：新策略（未保存）')
        self._deleteButton.setEnabled(False)

    def _appendDimensionRow(self, dimension: Dimension) -> None:
        '''追加一行维度。'''
        rowIndex = self._dimensionTable.rowCount()
        self._dimensionTable.insertRow(rowIndex)
        nameItem = QTableWidgetItem(dimension.name)
        descriptionItem = QTableWidgetItem(dimension.description)
        weightSpin = QDoubleSpinBox()
        weightSpin.setRange(0.0, 1.0)
        weightSpin.setSingleStep(0.05)
        weightSpin.setValue(dimension.weight)
        emphasizedCheck = QCheckBox('强调')
        emphasizedCheck.setChecked(dimension.emphasized)
        emphasizedCheck.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dimensionTable.setItem(rowIndex, 0, nameItem)
        self._dimensionTable.setItem(rowIndex, 1, descriptionItem)
        self._dimensionTable.setCellWidget(rowIndex, 2, weightSpin)
        self._dimensionTable.setCellWidget(rowIndex, 3, emphasizedCheck)
        self._updateWeightSum()

    def _addDimensionRow(self) -> None:
        '''添加空白维度行。'''
        self._appendDimensionRow(Dimension(name='', description='', weight=0.1, emphasized=False))

    def _removeSelectedDimension(self) -> None:
        '''删除选中的维度行。'''
        selectedRows = sorted(
            {index.row() for index in self._dimensionTable.selectedIndexes()},
            reverse=True,
        )
        for row in selectedRows:
            self._dimensionTable.removeRow(row)
        self._updateWeightSum()

    def _updateWeightSum(self, *_args) -> None:
        '''刷新权重总和显示与归一化提示。'''
        total = 0.0
        for row in range(self._dimensionTable.rowCount()):
            spin = self._dimensionTable.cellWidget(row, 2)
            if isinstance(spin, QDoubleSpinBox):
                total += spin.value()
        self._weightSumLabel.setText(f'权重总和：{total:.2f}' + ('' if abs(total - 1.0) < 0.01 else '（保存时自动归一化）'))

    def _collectStrategy(self) -> AnalysisStrategy:
        '''从表单收集策略实例。'''
        dimensions: list[Dimension] = []
        for row in range(self._dimensionTable.rowCount()):
            nameItem = self._dimensionTable.item(row, 0)
            descriptionItem = self._dimensionTable.item(row, 1)
            spin = self._dimensionTable.cellWidget(row, 2)
            check = self._dimensionTable.cellWidget(row, 3)
            name = (nameItem.text().strip() if nameItem is not None else '')
            if not name or not isinstance(spin, QDoubleSpinBox):
                continue
            dimensions.append(
                Dimension(
                    name=name,
                    description=descriptionItem.text().strip() if descriptionItem is not None else '',
                    weight=spin.value(),
                    emphasized=bool(check.isChecked()) if isinstance(check, QCheckBox) else False,
                ),
            )
        return AnalysisStrategy(
            strategyId='',
            name=self._nameEdit.text().strip(),
            dimensions=dimensions,
            ratingPrompt=self._ratingEdit.toPlainText().strip(),
            credibilityPrompt=self._credibilityEdit.toPlainText().strip(),
            source='user',
        )

    def _onSaveClicked(self) -> None:
        '''保存表单中的策略。'''
        strategy = self._collectStrategy()
        if not strategy.strategyId:
            strategy.strategyId = self._suggestStrategyId(strategy.name)
        errors = self._viewModel.saveUserStrategy(strategy)
        if errors:
            QMessageBox.warning(self, '保存失败', '；'.join(errors))
        else:
            QMessageBox.information(self, '保存成功', f'策略「{strategy.name}」已保存')

    def _suggestStrategyId(self, name: str) -> str:
        '''根据策略名生成不冲突的策略 ID。'''
        existing = {item.strategy.strategyId for item in self._viewModel.items}
        base = ''.join(ch for ch in name if ch.isalnum() or '\u4e00' <= ch <= '\u9fff') or 'strategy'
        candidate = base
        suffix = 2
        while candidate in existing:
            candidate = f'{base}{suffix}'
            suffix += 1
        return candidate

    def _onDeleteClicked(self) -> None:
        '''删除当前选中的自建策略。'''
        item = self._viewModel.itemAt(self._listWidget.currentRow())
        if item is None or item.sourceKind != 'user':
            return
        answer = QMessageBox.question(
            self,
            '删除策略',
            f'确定删除自建策略「{item.strategy.name}」吗？',
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._viewModel.deleteUserStrategy(item.strategy.strategyId)

    # ---------- AI 生成 ----------

    def _onAiGenerateClicked(self) -> None:
        '''启动 AI 生成。'''
        requirement = self._aiRequirementEdit.text().strip()
        if not requirement:
            QMessageBox.warning(self, '提示', '请先输入策略需求描述')
            return
        if not self._viewModel.isGenerating:
            self._aiGenerateButton.setEnabled(False)
            self._aiGenerateButton.setText('生成中……')
            self._viewModel.startAiGenerate(requirement)

    def _onAiGenerated(self, strategy: AnalysisStrategy) -> None:
        '''AI 生成成功：填充表单供预览确认。'''
        self._aiGenerateButton.setEnabled(True)
        self._aiGenerateButton.setText('生成策略')
        self._nameEdit.setText(strategy.name)
        self._ratingEdit.setPlainText(strategy.ratingPrompt)
        self._credibilityEdit.setPlainText(strategy.credibilityPrompt)
        self._dimensionTable.setRowCount(0)
        for dimension in strategy.dimensions:
            self._appendDimensionRow(dimension)
        self._selectedIdLabel.setText('AI 生成草稿（未保存，请确认后点击保存策略）')
        self._deleteButton.setEnabled(False)
        QMessageBox.information(self, '生成完成', 'AI 已生成策略草稿，请在表单中确认后保存。')

    def _onAiFailed(self, message: str) -> None:
        '''AI 生成失败提示。'''
        self._aiGenerateButton.setEnabled(True)
        self._aiGenerateButton.setText('生成策略')
        QMessageBox.critical(self, '生成失败', message)
