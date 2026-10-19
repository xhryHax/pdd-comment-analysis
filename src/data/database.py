from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from src.data.pathHelper import projectRoot
from src.work.analysisRecord import AnalysisRecord

logger = logging.getLogger(__name__)


class Database:
    '''SQLite 仓储：用户策略表与分析记录表的建表及 CRUD。

    使用 WAL 模式；所有写入均参数化以避免注入。每次操作创建
    独立连接，保证跨线程（流水线工作线程/界面线程）安全。
    '''

    _userStrategiesDdl: str = '''
        CREATE TABLE IF NOT EXISTS userStrategies (
            strategyId TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            dimensionsJson TEXT NOT NULL,
            ratingPrompt TEXT NOT NULL,
            credibilityPrompt TEXT NOT NULL,
            updatedAt TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    '''

    _analysisRecordsDdl: str = '''
        CREATE TABLE IF NOT EXISTS analysisRecords (
            recordId INTEGER PRIMARY KEY AUTOINCREMENT,
            goodsName TEXT NOT NULL,
            goodsUrl TEXT NOT NULL DEFAULT '',
            strategyId TEXT NOT NULL,
            strategyName TEXT NOT NULL,
            strategySnapshot TEXT NOT NULL,
            totalCommentCount INTEGER NOT NULL,
            validCommentCount INTEGER NOT NULL,
            credibilityThreshold REAL NOT NULL,
            trimPercent REAL NOT NULL,
            correctionFactor REAL,
            finalScore REAL NOT NULL,
            dimensionAverages TEXT NOT NULL,
            dimensionWeightedScores TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    '''

    _analysisIntermediatesDdl: str = '''
        CREATE TABLE IF NOT EXISTS analysisIntermediates (
            intermediateId INTEGER PRIMARY KEY AUTOINCREMENT,
            recordId INTEGER NOT NULL,
            goodsUrl TEXT NOT NULL,
            dataJson TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    '''

    _analysisIntermediatesIndexDdl: str = (
        'CREATE INDEX IF NOT EXISTS idxIntermediatesGoodsUrl'
        ' ON analysisIntermediates(goodsUrl)'
    )

    _aiSummariesDdl: str = '''
        CREATE TABLE IF NOT EXISTS aiSummaries (
            summaryId INTEGER PRIMARY KEY AUTOINCREMENT,
            goodsUrl TEXT NOT NULL,
            recordId INTEGER,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    '''

    _aiSummariesIndexDdl: str = (
        'CREATE INDEX IF NOT EXISTS idxAiSummariesGoodsUrl ON aiSummaries(goodsUrl)'
    )

    def __init__(self, dbPath: Path | str | None = None) -> None:
        '''初始化仓储并确保数据表存在。

        Args:
            dbPath: 数据库文件路径，缺省时使用项目根下 data/analysis.db。
        '''
        self._dbPath: Path = (
            Path(dbPath) if dbPath is not None else projectRoot() / 'data' / 'analysis.db'
        )
        self._dbPath.parent.mkdir(parents=True, exist_ok=True)
        self._ensureTables()

    @property
    def dbPath(self) -> Path:
        '''当前数据库文件路径。'''
        return self._dbPath

    def _connect(self) -> sqlite3.Connection:
        '''创建新的数据库连接（WAL 模式，行转字典）。

        Returns:
            sqlite3.Connection: 已配置的连接实例。
        '''
        conn = sqlite3.connect(self._dbPath)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def _ensureTables(self) -> None:
        '''建表（幂等）。'''
        with self._connect() as conn:
            conn.execute(self._userStrategiesDdl)
            conn.execute(self._analysisRecordsDdl)
            conn.execute(self._analysisIntermediatesDdl)
            conn.execute(self._analysisIntermediatesIndexDdl)
            conn.execute(self._aiSummariesDdl)
            conn.execute(self._aiSummariesIndexDdl)
        logger.debug('数据库表已就绪：%s', self._dbPath)

    # ---------- 用户策略 ----------

    def saveUserStrategy(self, strategyDict: dict[str, Any]) -> None:
        '''保存（插入或覆盖）用户自建策略。

        Args:
            strategyDict: AnalysisStrategy.toDict() 产出的策略字典。
        '''
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO userStrategies
                    (strategyId, name, dimensionsJson, ratingPrompt, credibilityPrompt)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategyId) DO UPDATE SET
                    name = excluded.name,
                    dimensionsJson = excluded.dimensionsJson,
                    ratingPrompt = excluded.ratingPrompt,
                    credibilityPrompt = excluded.credibilityPrompt,
                    updatedAt = datetime('now', 'localtime')
                ''',
                (
                    strategyDict['strategyId'],
                    strategyDict['name'],
                    strategyDict.get('dimensionsJson', '[]'),
                    strategyDict.get('ratingPrompt', ''),
                    strategyDict.get('credibilityPrompt', ''),
                ),
            )
        logger.info('用户策略已保存：%s', strategyDict['strategyId'])

    def deleteUserStrategy(self, strategyId: str) -> bool:
        '''删除用户自建策略。

        Args:
            strategyId: 策略 ID。

        Returns:
            bool: 实际删除返回 True，策略不存在返回 False。
        '''
        with self._connect() as conn:
            cursor = conn.execute(
                'DELETE FROM userStrategies WHERE strategyId = ?', (strategyId,)
            )
        deleted = cursor.rowcount > 0
        logger.info('删除用户策略 %s：%s', strategyId, '成功' if deleted else '不存在')
        return deleted

    def listUserStrategies(self) -> list[dict[str, Any]]:
        '''列出全部用户自建策略（按名称排序）。

        Returns:
            list[dict[str, Any]]: 策略字典列表，其中维度为
            dimensionsJson 原始 JSON 文本，由调用方反序列化。
        '''
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT strategyId, name, dimensionsJson, ratingPrompt, credibilityPrompt'
                ' FROM userStrategies ORDER BY name'
            ).fetchall()
        return [dict(row) for row in rows]

    def getUserStrategy(self, strategyId: str) -> dict[str, Any] | None:
        '''按 ID 读取用户自建策略。

        Args:
            strategyId: 策略 ID。

        Returns:
            dict[str, Any] | None: 策略字典，不存在时返回 None。
        '''
        with self._connect() as conn:
            row = conn.execute(
                'SELECT strategyId, name, dimensionsJson, ratingPrompt, credibilityPrompt'
                ' FROM userStrategies WHERE strategyId = ?',
                (strategyId,),
            ).fetchone()
        return dict(row) if row is not None else None

    # ---------- 分析记录 ----------

    def saveAnalysisRecord(self, record: AnalysisRecord) -> int:
        '''保存分析记录并返回自增 ID。

        Args:
            record: 分析记录实例。

        Returns:
            int: 新记录的 recordId。
        '''
        row = record.toRow()
        with self._connect() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO analysisRecords
                    (goodsName, goodsUrl, strategyId, strategyName, strategySnapshot,
                     totalCommentCount, validCommentCount, credibilityThreshold, trimPercent,
                     correctionFactor, finalScore, dimensionAverages, dimensionWeightedScores)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    row['goodsName'],
                    row['goodsUrl'],
                    row['strategyId'],
                    row['strategyName'],
                    row['strategySnapshot'],
                    row['totalCommentCount'],
                    row['validCommentCount'],
                    row['credibilityThreshold'],
                    row['trimPercent'],
                    row['correctionFactor'],
                    row['finalScore'],
                    row['dimensionAverages'],
                    row['dimensionWeightedScores'],
                ),
            )
        record.recordId = int(cursor.lastrowid or 0)
        logger.info('分析记录已保存：#%d %s', record.recordId, record.goodsName)
        return record.recordId

    def listAnalysisRecords(
        self,
        keyword: str = '',
        limit: int = 200,
    ) -> list[AnalysisRecord]:
        '''查询分析记录列表（最新在前，可按商品名模糊过滤）。

        Args:
            keyword: 商品名关键词，空串表示不过滤。
            limit: 最多返回的条数。

        Returns:
            list[AnalysisRecord]: 记录列表。
        '''
        with self._connect() as conn:
            if keyword:
                rows = conn.execute(
                    'SELECT * FROM analysisRecords WHERE goodsName LIKE ?'
                    ' ORDER BY recordId DESC LIMIT ?',
                    (f'%{keyword}%', limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT * FROM analysisRecords ORDER BY recordId DESC LIMIT ?', (limit,)
                ).fetchall()
        return [AnalysisRecord.fromRow(dict(row)) for row in rows]

    def getAnalysisRecord(self, recordId: int) -> AnalysisRecord | None:
        '''按 ID 读取分析记录。

        Args:
            recordId: 记录 ID。

        Returns:
            AnalysisRecord | None: 记录实例，不存在时返回 None。
        '''
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM analysisRecords WHERE recordId = ?', (recordId,)
            ).fetchone()
        return AnalysisRecord.fromRow(dict(row)) if row is not None else None

    def deleteAnalysisRecord(self, recordId: int) -> bool:
        '''删除指定分析记录。

        Args:
            recordId: 记录 ID。

        Returns:
            bool: 实际删除返回 True，记录不存在返回 False。
        '''
        with self._connect() as conn:
            cursor = conn.execute('DELETE FROM analysisRecords WHERE recordId = ?', (recordId,))
        return cursor.rowcount > 0

    # ---------- 中间数据 ----------

    def saveIntermediateData(self, recordId: int, goodsUrl: str, dataJson: str) -> bool:
        '''保存一次分析的中间数据（LLM 逐条评论的打分结果）。

        Args:
            recordId: 所属分析记录 ID。
            goodsUrl: 商品链接（唯一识别码）。
            dataJson: 中间数据的 JSON 文本。

        Returns:
            bool: 写入成功返回 True。
        '''
        with self._connect() as conn:
            conn.execute(
                'INSERT INTO analysisIntermediates (recordId, goodsUrl, dataJson)'
                ' VALUES (?, ?, ?)',
                (recordId, goodsUrl, dataJson),
            )
        logger.info('中间数据已保存：记录 #%s（%d 字节）', recordId, len(dataJson))
        return True

    def getIntermediateData(
        self,
        goodsUrl: str,
        recordId: int | None = None,
    ) -> list[Any] | None:
        '''读取中间数据。

        优先按记录 ID 精确匹配，其次回落到按商品链接取最新一条。

        Args:
            goodsUrl: 商品链接。
            recordId: 分析记录 ID，提供时优先按 ID 查询。

        Returns:
            list[Any] | None: 反序列化后的中间数据列表；不存在或解析
            失败时返回 None。
        '''
        with self._connect() as conn:
            row = None
            if recordId is not None:
                row = conn.execute(
                    'SELECT dataJson FROM analysisIntermediates WHERE recordId = ?'
                    ' ORDER BY intermediateId DESC LIMIT 1',
                    (recordId,),
                ).fetchone()
            if row is None and goodsUrl:
                row = conn.execute(
                    'SELECT dataJson FROM analysisIntermediates WHERE goodsUrl = ?'
                    ' ORDER BY intermediateId DESC LIMIT 1',
                    (goodsUrl,),
                ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row['dataJson'])
        except json.JSONDecodeError as error:
            logger.warning('中间数据解析失败：%s', error)
            return None
        return data if isinstance(data, list) else None

    # ---------- AI 智能总结 ----------

    def saveAiSummary(
        self,
        goodsUrl: str,
        recordId: int | None,
        question: str,
        answer: str,
    ) -> int:
        '''追加一轮 AI 总结对话。

        Args:
            goodsUrl: 商品链接（不同对话记录的区分键）。
            recordId: 关联的分析记录 ID（冗余，便于联查）。
            question: 用户提问。
            answer: AI 回答。

        Returns:
            int: 新记录的 summaryId。
        '''
        with self._connect() as conn:
            cursor = conn.execute(
                'INSERT INTO aiSummaries (goodsUrl, recordId, question, answer)'
                ' VALUES (?, ?, ?, ?)',
                (goodsUrl, recordId, question, answer),
            )
        summaryId = int(cursor.lastrowid or 0)
        logger.info('AI 总结对话已保存：#%d（recordId=%s）', summaryId, recordId)
        return summaryId

    def listAiSummaries(
        self,
        goodsUrl: str,
        recordId: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        '''按商品链接查询 AI 总结对话（正序，供多轮上下文使用）。

        Args:
            goodsUrl: 商品链接。
            recordId: 提供时仅返回该记录关联的对话。
            limit: 最多返回条数，None 表示不限。

        Returns:
            list[dict[str, Any]]: 对话字典列表，键为 summaryId / goodsUrl /
            recordId / question / answer / createdAt。
        '''
        sql = 'SELECT * FROM aiSummaries WHERE goodsUrl = ?'
        parameters: list[Any] = [goodsUrl]
        if recordId is not None:
            sql += ' AND recordId = ?'
            parameters.append(recordId)
        sql += ' ORDER BY summaryId ASC'
        if limit is not None:
            sql += ' LIMIT ?'
            parameters.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def deleteAiSummaries(self, goodsUrl: str) -> int:
        '''删除某商品链接下的全部 AI 总结对话。

        Args:
            goodsUrl: 商品链接。

        Returns:
            int: 实际删除的对话条数。
        '''
        with self._connect() as conn:
            cursor = conn.execute('DELETE FROM aiSummaries WHERE goodsUrl = ?', (goodsUrl,))
        logger.info('已删除 %s 的 AI 总结对话：%d 条', goodsUrl, cursor.rowcount)
        return cursor.rowcount
