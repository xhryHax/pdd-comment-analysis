from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from src.data.database import Database
from src.interface.model.recordListItem import RecordListItem
from src.interface.model.summaryContext import SummaryContext
from src.work.analysisRecord import AnalysisRecord

logger = logging.getLogger(__name__)


class RecordsViewModel(QObject):
    '''分析记录页视图模型：记录查询、详情与删除。'''

    recordsChanged = Signal()

    def __init__(self, database: Database, parent: QObject | None = None) -> None:
        '''初始化视图模型。

        Args:
            database: 数据库仓储。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._database = database
        self._keyword = ''
        self.items: list[RecordListItem] = []
        self.refresh()

    @property
    def keyword(self) -> str:
        '''当前搜索关键词。'''
        return self._keyword

    def refresh(self, keyword: str | None = None) -> None:
        '''刷新记录列表（可更新关键词）。

        Args:
            keyword: 新的搜索关键词；None 表示沿用当前关键词。
        '''
        if keyword is not None:
            self._keyword = keyword.strip()
        records = self._database.listAnalysisRecords(self._keyword)
        self.items = [RecordListItem(record=record, summaryText=self._buildSummary(record)) for record in records]
        logger.info('记录列表已刷新：%d 条（关键词 %r）', len(self.items), self._keyword)
        self.recordsChanged.emit()

    def itemAt(self, index: int) -> RecordListItem | None:
        '''按索引取展示项。'''
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def deleteRecord(self, recordId: int) -> bool:
        '''删除指定记录并刷新列表。

        Args:
            recordId: 记录 ID。

        Returns:
            bool: 是否实际删除。
        '''
        deleted = self._database.deleteAnalysisRecord(recordId)
        if deleted:
            self.refresh()
        return deleted

    def summaryContext(self, record: AnalysisRecord) -> SummaryContext:
        '''由历史记录构建 AI 总结的注入数据上下文。

        中间数据从 analysisIntermediates 表按记录 ID 读取（取不到时
        回落到按商品链接取最新一条）。

        Args:
            record: 分析记录。

        Returns:
            SummaryContext: 注入数据上下文。
        '''
        intermediateData = self._database.getIntermediateData(record.goodsUrl, record.recordId)
        return SummaryContext(
            goodsUrl=record.goodsUrl,
            goodsName=record.goodsName,
            recordId=record.recordId,
            strategySnapshot=dict(record.strategySnapshot or {}),
            refactored=bool((record.strategySnapshot or {}).get('refactored', False)),
            intermediateData=intermediateData or [],
            correctionFactor=record.correctionFactor,
            finalScore=record.finalScore,
            dimensionAverages=dict(record.dimensionAverages or {}),
            dimensionWeightedScores=dict(record.dimensionWeightedScores or {}),
            totalCommentCount=record.totalCommentCount,
            validCommentCount=record.validCommentCount,
            credibilityThreshold=record.credibilityThreshold,
            trimPercent=record.trimPercent,
        )

    def detailText(self, record: AnalysisRecord) -> str:
        '''构建记录详情文本（HTML）。

        Args:
            record: 分析记录。

        Returns:
            str: 供 QTextBrowser 展示的 HTML 文本。
        '''
        rows = []
        snapshot = record.strategySnapshot or {}
        for name, average in record.dimensionAverages.items():
            averageText = f'{average:.1f}' if average is not None else '无数据'
            rows.append(f'<tr><td>{name}</td><td>{averageText}</td></tr>')
        factorText = f'{record.correctionFactor:.2f}' if record.correctionFactor is not None else '未介入'
        dimensionRows = ''.join(rows) if rows else '<tr><td colspan="2">无维度数据</td></tr>'
        return f'''
        <h2>{record.goodsName}</h2>
        <p style="color:#6B6B6B;">{record.createdAt} · 策略：{record.strategyName} · 记录 #{record.recordId}</p>
        <p style="font-size:28px; font-weight:600;">最终得分：{record.finalScore:.2f}</p>
        <table width="100%" cellpadding="6" style="border-collapse:collapse;">
        <tr><th align="left">维度</th><th align="left">平均分</th></tr>
        {dimensionRows}
        </table>
        <p>评论总数：{record.totalCommentCount} · 有效评论：{record.validCommentCount}<br/>
        置信度阈值：{record.credibilityThreshold:.2f} · 截尾比例：{record.trimPercent:.0f}%<br/>
        修正因子：{factorText}<br/>
        链接：{record.goodsUrl or '（未记录）'}</p>
        '''

    def _buildSummary(self, record: AnalysisRecord) -> str:
        '''构建列表副标题文本。'''
        strategyLabel = f'策略 {record.strategyName} · 有效 {record.validCommentCount} 条'
        return f'{record.createdAt or ''} · {strategyLabel}'
