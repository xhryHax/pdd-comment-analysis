from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.interface.model.recordListItem import RecordListItem
from src.interface.tools.scoreBadge import ScoreBadge
from src.interface.viewModel.recordsViewModel import RecordsViewModel
from src.work.analysisRecord import AnalysisRecord

# 未选中任何记录时详情区展示的默认文案
DEFAULT_DETAIL_HTML = '<p style="color:#6B6B6B;">选择记录后显示分析</p>'


class RecordsView(QWidget):
    '''分析记录页：记录列表、详情与删除。'''

    recordOpened = Signal(object)

    def __init__(self, viewModel: RecordsViewModel, parent: QWidget | None = None) -> None:
        '''初始化页面并绑定视图模型。

        Args:
            viewModel: 记录页视图模型。
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

        leftPanel = QWidget()
        leftLayout = QVBoxLayout(leftPanel)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.setSpacing(10)
        titleLabel = QLabel('分析记录')
        titleLabel.setProperty('headingLevel', '1')
        leftLayout.addWidget(titleLabel)
        searchLayout = QHBoxLayout()
        self._searchEdit = QLineEdit()
        self._searchEdit.setPlaceholderText('按商品名搜索……')
        refreshButton = QPushButton('刷新')
        refreshButton.setProperty('variant', 'ghost')
        refreshButton.clicked.connect(self._onRefresh)
        self._searchEdit.returnPressed.connect(self._onRefresh)
        searchLayout.addWidget(self._searchEdit, stretch=1)
        searchLayout.addWidget(refreshButton)
        leftLayout.addLayout(searchLayout)
        self._listWidget = QListWidget()
        self._listWidget.setMinimumWidth(360)
        leftLayout.addWidget(self._listWidget, stretch=1)
        rootLayout.addWidget(leftPanel, stretch=2)

        rightPanel = QWidget()
        rightLayout = QVBoxLayout(rightPanel)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setSpacing(10)
        self._detailTitle = QLabel('记录详情')
        self._detailTitle.setProperty('headingLevel', '2')
        rightLayout.addWidget(self._detailTitle)
        self._detailBrowser = QTextBrowser()
        self._detailBrowser.setOpenExternalLinks(True)
        self._detailBrowser.setHtml(DEFAULT_DETAIL_HTML)
        rightLayout.addWidget(self._detailBrowser, stretch=1)
        self._deleteButton = QPushButton('删除此记录')
        self._deleteButton.setProperty('variant', 'danger')
        self._deleteButton.setEnabled(False)
        rightLayout.addWidget(self._deleteButton, alignment=Qt.AlignmentFlag.AlignRight)
        rootLayout.addWidget(rightPanel, stretch=3)

    def _connectSignals(self) -> None:
        '''绑定信号。'''
        self._viewModel.recordsChanged.connect(self._reloadList)
        self._listWidget.currentRowChanged.connect(self._onRowChanged)
        # 再次点击已选中的行时 currentRowChanged 不会触发，
        # 额外监听点击事件以保证每次点击都会刷新并弹出 AI 智能总结窗
        self._listWidget.itemClicked.connect(lambda item: self._onRowChanged(self._listWidget.row(item)))
        self._deleteButton.clicked.connect(self._onDeleteClicked)

    def _onRefresh(self) -> None:
        '''刷新列表。'''
        self._viewModel.refresh(self._searchEdit.text())

    def _reloadList(self) -> None:
        '''重建列表项。'''
        self._listWidget.blockSignals(True)
        self._listWidget.clear()
        for item in self._viewModel.items:
            listWidgetItem = QListWidgetItem()
            listWidgetItem.setSizeHint(QSize(64, 84))
            self._listWidget.addItem(listWidgetItem)
            self._listWidget.setItemWidget(listWidgetItem, self._buildRowWidget(item))
        self._listWidget.blockSignals(False)
        self._showDefaultDetail()

    def _showDefaultDetail(self) -> None:
        '''展示未选中记录时的默认详情（含提示文案）。'''
        self._listWidget.clearSelection()
        self._listWidget.setCurrentRow(-1)
        self._detailTitle.setText('记录详情')
        self._detailBrowser.setHtml(DEFAULT_DETAIL_HTML)
        self._deleteButton.setEnabled(False)

    def _buildRowWidget(self, item: RecordListItem) -> QWidget:
        '''构建单条记录的行控件。'''
        rowWidget = QWidget()
        rowWidget.setStyleSheet('background-color: transparent;')
        rowLayout = QHBoxLayout(rowWidget)
        rowLayout.setContentsMargins(12, 8, 12, 8)
        textLayout = QVBoxLayout()
        nameLabel = QLabel(item.record.goodsName)
        nameLabel.setStyleSheet('font-weight: 600;')
        summaryLabel = QLabel(item.summaryText)
        summaryLabel.setProperty('caption', True)
        textLayout.addWidget(nameLabel)
        textLayout.addWidget(summaryLabel)
        badge = ScoreBadge(item.record.finalScore)
        rowLayout.addLayout(textLayout, stretch=1)
        rowLayout.addWidget(badge)
        return rowWidget

    def _onRowChanged(self, row: int) -> None:
        '''选中行变化时刷新详情，并请求打开该记录的 AI 智能总结窗。

        Args:
            row: 新的当前行索引。
        '''
        item = self._viewModel.itemAt(row)
        if item is None:
            self._deleteButton.setEnabled(False)
            return
        record: AnalysisRecord = item.record
        self._detailTitle.setText(record.goodsName or '记录详情')
        self._detailBrowser.setHtml(self._viewModel.detailText(record))
        self._deleteButton.setEnabled(True)
        self.recordOpened.emit(record)

    def _onDeleteClicked(self) -> None:
        '''删除当前选中记录。'''
        item = self._viewModel.itemAt(self._listWidget.currentRow())
        if item is None or item.record.recordId is None:
            return
        answer = QMessageBox.question(
            self,
            '删除记录',
            f'确定删除记录「{item.record.goodsName}」吗？此操作不可恢复。',
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._viewModel.deleteRecord(item.record.recordId)
