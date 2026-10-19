from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, ClassVar

from openai import OpenAI

from src.data.configAccess import ConfigAccess
from src.data.loggerSetup import maskSecret
from src.work.analysisStrategy import AnalysisStrategy
from src.work.commentScore import CommentScore, clampCredibility, clampScore

logger = logging.getLogger(__name__)

type ProgressCallback = Callable[[int, int], None]


class LlmService:
    '''DeepSeek LLM 服务：评论并发分批打分与结果解析。

    使用 OpenAI SDK 调用 DeepSeek API；评论按批拆分后以线程池
    并发请求，失败批次按指数退避重试；输出解析对 JSON 瑕疵与
    评论 key 未命中做容错处理。
    '''

    _scoreOutputContract: ClassVar[str] = (
        '输出要求：仅输出一个 JSON 对象（不要输出任何其他文字），'
        '以每条评论原文作为顶层键，值是一个包含各维度分数与可信度的对象，形如：\n'
        '{"某条评论原文": {"维度A": 80, "维度B": null, "credibility": 0.8}, ...}\n'
        '维度名必须与给定维度列表完全一致；未提及或无法判断输出 null；'
        'credibility 为 0-1 的小数。'
    )

    def __init__(self, config: ConfigAccess) -> None:
        '''初始化 LLM 服务（客户端惰性创建）。

        Args:
            config: 系统配置读写器，用于读取 API Key、模型与并发参数。
        '''
        self._config = config
        self._client: OpenAI | None = None

    def _requireClient(self) -> OpenAI:
        '''获取（必要时创建）DeepSeek 客户端。

        Returns:
            OpenAI: 已配置的客户端实例。

        Raises:
            ValueError: API Key 未配置时抛出。
        '''
        if self._client is not None:
            return self._client
        apiKey = self._config.getStr('llm', 'apiKey', '')
        if not apiKey:
            msg = '未配置 DeepSeek API Key，请先在设置页填写'
            raise ValueError(msg)
        baseUrl = self._config.getStr('llm', 'baseUrl', 'https://api.deepseek.com')
        timeout = self._config.getFloat('llm', 'requestTimeoutSeconds', 120.0)
        self._client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)
        logger.info(
            'DeepSeek 客户端就绪（baseUrl=%s，apiKey=%s）',
            baseUrl,
            maskSecret(apiKey),
        )
        return self._client

    def testConnection(self) -> str:
        '''测试 API 连通性。

        Returns:
            str: 成功时返回模型回复文本，失败时抛出异常。

        Raises:
            ValueError: API Key 未配置。
            Exception: 请求失败时原样抛出。
        '''
        client = self._requireClient()
        model = self._config.getStr('llm', 'model', 'deepseek-chat')
        response = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': '回复“连接成功”四个字'}],
            max_tokens=16,
        )
        return str(response.choices[0].message.content or '').strip()

    # ---------- 评论打分 ----------

    def scoreComments(
        self,
        comments: list[str],
        strategy: AnalysisStrategy,
        onProgress: ProgressCallback | None = None,
    ) -> list[CommentScore]:
        '''并发分批为评论打分，返回中间数据。

        重复评论文本仅发送一次并复用结果；个别批次最终失败时
        跳过该批并记录错误，不影响其余批次。

        Args:
            comments: 原始评论文本列表。
            strategy: 当前分析策略（已重构/归一化）。
            onProgress: 进度回调，参数为 (已完成评论条数, 总条数)。

        Returns:
            list[CommentScore]: 与输入顺序一致的打分结果列表。
        '''
        if not comments:
            return []
        uniqueComments: list[str] = []
        uniqueIndexByText: dict[str, int] = {}
        for text in comments:
            trimmed = text.strip()
            if trimmed and trimmed not in uniqueIndexByText:
                uniqueIndexByText[trimmed] = len(uniqueComments)
                uniqueComments.append(trimmed)
        duplicateCount = len(comments) - len(uniqueComments)
        if duplicateCount:
            logger.info('检测到重复评论 %d 条，去重后发送 %d 条', duplicateCount, len(uniqueComments))

        batchSize = self._config.getInt('llm', 'batchSize', 50)
        batches = [
            uniqueComments[start : start + batchSize] for start in range(0, len(uniqueComments), batchSize)
        ]
        resultByText: dict[str, CommentScore] = {}
        failedBatches = 0
        doneCount = 0
        with ThreadPoolExecutor(max_workers=self._config.getInt('llm', 'maxConcurrency', 4)) as pool:
            futures = {pool.submit(self._scoreBatch, batch, strategy): batch for batch in batches}
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    batchResults = future.result()
                except Exception as error:  # noqa: BLE001 - 单批失败不应中断整体
                    failedBatches += 1
                    logger.error(
                        '评论批次（%d 条）最终失败，已跳过：%s',
                        len(batch),
                        error,
                    )
                    batchResults = []
                for item in batchResults:
                    resultByText[item.comment] = item
                doneCount += len(batch)
                if onProgress is not None:
                    onProgress(doneCount, len(uniqueComments))
        if failedBatches:
            logger.warning('共 %d/%d 个批次失败，结果仅基于成功批次', failedBatches, len(batches))
        results: list[CommentScore] = []
        for text in comments:
            trimmed = text.strip()
            hit = resultByText.get(trimmed)
            if hit is not None:
                results.append(hit)
            else:
                results.append(
                    CommentScore(comment=text.strip(), scores={}, credibility=clampCredibility(None)),
                )
        return results

    def _scoreBatch(self, batch: list[str], strategy: AnalysisStrategy) -> list[CommentScore]:
        '''请求单个批次的打分并解析（含指数退避重试）。

        Args:
            batch: 本批评论文本。
            strategy: 当前分析策略。

        Returns:
            list[CommentScore]: 本批打分结果。

        Raises:
            RuntimeError: 重试耗尽仍失败时抛出。
        '''
        client = self._requireClient()
        model = self._config.getStr('llm', 'model', 'deepseek-chat')
        maxRetries = self._config.getInt('llm', 'maxRetries', 3)
        systemPrompt = self._buildSystemPrompt(strategy)
        userPrompt = self._buildUserPrompt(batch, strategy)
        lastError: Exception | None = None
        for attempt in range(maxRetries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': systemPrompt},
                        {'role': 'user', 'content': userPrompt},
                    ],
                    response_format={'type': 'json_object'},
                )
                content = str(response.choices[0].message.content or '')
                parsed = self._parseScoreJson(content, strategy)
                logger.info('批次打分成功：%d 条评论', len(parsed))
                return parsed
            except Exception as error:  # noqa: BLE001 - 统一重试
                lastError = error
                waitSeconds = min(2.0 * (2**attempt), 30.0)
                logger.warning(
                    '批次请求失败（第 %d/%d 次），%.1f 秒后重试：%s',
                    attempt + 1,
                    maxRetries + 1,
                    waitSeconds,
                    error,
                )
                time.sleep(waitSeconds)
        msg = f'批次重试 {maxRetries + 1} 次后仍失败：{lastError}'
        raise RuntimeError(msg)

    def _buildSystemPrompt(self, strategy: AnalysisStrategy) -> str:
        '''构建打分请求的 system 提示词。'''
        return f'{strategy.ratingPrompt}\n\n{strategy.credibilityPrompt}\n\n{self._scoreOutputContract}'

    def _buildUserPrompt(self, batch: list[str], strategy: AnalysisStrategy) -> str:
        '''构建打分请求的 user 提示词（维度说明 + 评论列表）。'''
        dimensionLines = [
            f'- {dimension.name}：{dimension.description}'
            for dimension in strategy.dimensions
        ]
        commentLines = [f'{index}. {text}' for index, text in enumerate(batch, start=1)]
        return (
            f'商品分析维度如下：\n{chr(10).join(dimensionLines)}\n\n'
            f'请对下列 {len(batch)} 条评论逐条打分，评论原文必须原样作为 JSON 顶层键：\n'
            + '\n'.join(commentLines)
        )

    def _parseScoreJson(self, content: str, strategy: AnalysisStrategy) -> list[CommentScore]:
        '''容错解析 LLM 打分输出。

        依次尝试：原样解析 → 剥离 Markdown 代码围栏 → 去除尾逗号；
        评论 key 未命中时按去空白归一匹配回退。

        Args:
            content: LLM 输出的原始文本。
            strategy: 当前分析策略。

        Returns:
            list[CommentScore]: 解析出的本批打分结果。

        Raises:
            ValueError: 无法解析出 JSON 对象时抛出。
        '''
        dimensionNames = {dimension.name for dimension in strategy.dimensions}
        data = self._loadsTolerant(content)
        if not isinstance(data, dict):
            msg = 'LLM 输出不是 JSON 对象'
            raise ValueError(msg)
        normalizedKeys: dict[str, str] = {
            key.strip(): key for key in data
        }
        results: list[CommentScore] = []
        for rawKey, value in data.items():
            if not isinstance(value, dict):
                continue
            comment = str(rawKey).strip()
            scores: dict[str, int | None] = {}
            for dimensionName in dimensionNames:
                scores[dimensionName] = clampScore(value.get(dimensionName))
            credibility = clampCredibility(value.get('credibility'))
            results.append(CommentScore(comment=comment, scores=scores, credibility=credibility))
        if not results:
            logger.warning('LLM 输出中未解析到任何评论结果，键示例：%s', list(normalizedKeys)[:3])
        return results

    def _loadsTolerant(self, content: str) -> Any:
        '''多策略容错的 JSON 加载。

        Args:
            content: 原始文本。

        Returns:
            Any: 解析结果，全部失败时抛出最后一个异常。

        Raises:
            ValueError: 无法解析时抛出。
        '''
        candidates = [content]
        fenceMatch = re.search(r'```(?:json)?\s*(.*?)\s*```', content, flags=re.DOTALL)
        if fenceMatch:
            candidates.insert(0, fenceMatch.group(1))
        braceMatch = re.search(r'\{.*\}', content, flags=re.DOTALL)
        if braceMatch:
            candidates.insert(0, braceMatch.group(0))
        lastError: Exception | None = None
        for candidate in candidates:
            for text in (candidate, re.sub(r',\s*([}\]])', r'\1', candidate)):
                try:
                    return json.loads(text)
                except json.JSONDecodeError as error:
                    lastError = error
        msg = f'LLM 输出无法解析为 JSON：{lastError}'
        raise ValueError(msg)
