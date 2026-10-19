from __future__ import annotations

from dataclasses import dataclass

from src.work.analysisRecord import AnalysisRecord


@dataclass(slots=True)
class RecordListItem:
    '''记录列表展示项。'''

    record: AnalysisRecord
    summaryText: str

    @property
    def title(self) -> str:
        '''列表主标题（商品名 + 时间）。'''
        createdAt = self.record.createdAt or '未知时间'
        return f'{self.record.goodsName}  ·  {createdAt}'
