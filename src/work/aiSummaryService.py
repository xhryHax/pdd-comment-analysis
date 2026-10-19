from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from openai import OpenAI

from src.data.configAccess import ConfigAccess
from src.data.loggerSetup import maskSecret
from src.interface.model.summaryContext import SummaryContext

logger = logging.getLogger(__name__)

type HistoryTurn = dict[str, Any]


class AiSummaryService:
    '''AI 智能总结服务：注入分析数据后向 LLM 发起多轮问答。

    每次请求将四类数据注入系统提示词：分析策略（维度重构后则注入
    重构结果）、中间数据、修正因子（若有）与汇总结果；并按配置携带
    该商品最近若干轮历史对话，实现多轮追问。
    '''

    _systemPromptPlaceholder: ClassVar[str] = (
        '【占位提示词】此处为 AI 智能总结的正式系统提示词位置，尚未提供正式文案。\n'
        '占位期间的临时行为约定：\n'
        '1. 你的身份：资深电商商品评测顾问；\n'
        '2. 只依据下方“注入数据”中的信息作答，不得编造数据；\n'
        '3. 回答使用简体中文，结构清晰、结论先行，必要时给出要点列表；\n'
        '4. 涉及分数时必须引用注入数据中的具体数值；\n'
        '5. 若注入数据不足以回答，直接说明缺少哪些数据。'
    )

    def __init__(self, config: ConfigAccess) -> None:
        '''初始化 AI 总结服务（客户端惰性创建）。

        Args:
            config: 系统配置读写器，用于读取凭据与 [aiSummary] 参数。
        '''
        self._config = config
        self._client: OpenAI | None = None

    def _requireClient(self) -> OpenAI:
        '''获取（必要时创建）LLM 客户端。

        Returns:
            OpenAI: 已配置的客户端实例。

        Raises:
            ValueError: API Key 未配置时抛出。
        '''
        if self._client is not None:
            return self._client
        apiKey = self._config.getStr('llm', 'apiKey', '')
        if not apiKey:
            msg = '未配置 DeepSeek API Key，无法使用 AI 智能总结'
            raise ValueError(msg)
        baseUrl = self._config.getStr('llm', 'baseUrl', 'https://api.deepseek.com')
        timeout = self._config.getFloat('llm', 'requestTimeoutSeconds', 120.0)
        self._client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)
        logger.info('AI 总结客户端就绪（baseUrl=%s，apiKey=%s）', baseUrl, maskSecret(apiKey))
        return self._client

    # ---------- 提示词组装 ----------

    def buildMessages(
        self,
        context: SummaryContext,
        history: list[HistoryTurn],
        question: str,
    ) -> list[dict[str, str]]:
        '''组装本次请求的消息列表。

        Args:
            context: 注入数据上下文。
            history: 该商品的历史对话（按时间正序）。
            question: 用户本轮提问。

        Returns:
            list[dict[str, str]]: 可直接提交给 chat.completions 的 messages。
        '''
        historyLimit = max(0, self._config.getInt('aiSummary', 'historyLimit', 5))
        recentTurns = history[-historyLimit:] if historyLimit else []
        messages: list[dict[str, str]] = [
            {'role': 'system', 'content': self.buildSystemPrompt(context)},
        ]
        for turn in recentTurns:
            if str(turn.get('question', '')).strip():
                messages.append({'role': 'user', 'content': str(turn['question'])})
            if str(turn.get('answer', '')).strip():
                messages.append({'role': 'assistant', 'content': str(turn['answer'])})
        messages.append({'role': 'user', 'content': question})
        return messages

    def buildSystemPrompt(self, context: SummaryContext) -> str:
        '''构建系统提示词（占位提示词 + 注入数据）。

        Args:
            context: 注入数据上下文。

        Returns:
            str: 系统提示词全文。
        '''
        return f'{self._systemPromptPlaceholder}\n\n{self.buildInjection(context)}'

    def buildInjection(self, context: SummaryContext) -> str:
        '''将四类分析数据格式化为注入文本。

        Args:
            context: 注入数据上下文。

        Returns:
            str: 结构化的注入数据文本。
        '''
        sections = [
            self._buildStrategySection(context),
            self._buildIntermediateSection(context),
            self._buildCorrectionSection(context),
            self._buildSummarySection(context),
        ]
        return '===== 注入数据开始 =====\n' + '\n\n'.join(sections) + '\n===== 注入数据结束 ====='

    def _buildStrategySection(self, context: SummaryContext) -> str:
        '''构建“分析策略”小节。'''
        snapshot = context.strategySnapshot or {}
        lines = ['【一、分析策略】']
        if not snapshot:
            lines.append('（暂无分析策略数据）')
            return '\n'.join(lines)
        lines.append(f'策略名称：{snapshot.get('name', '（未命名）')}')
        lines.append(f'是否维度重构：{"是（已按强调维度重构并归一化权重）" if context.refactored else '否'}')
        dimensions = snapshot.get('dimensions') or []
        if dimensions:
            lines.append('维度列表：')
            for dimension in dimensions:
                lines.append(
                    f'  - {dimension.get('name', '')}（权重 {dimension.get('weight', 0)}，'
                    f'{"强调" if dimension.get('emphasized') else '非强调'}）：'
                    f'{dimension.get('description', '')}',
                )
        else:
            lines.append('维度列表：（空）')
        ratingPrompt = str(snapshot.get('ratingPrompt', '')).strip()
        credibilityPrompt = str(snapshot.get('credibilityPrompt', '')).strip()
        lines.append(f'评分提示词：{ratingPrompt or '（空）'}')
        lines.append(f'置信度提示词：{credibilityPrompt or '（空）'}')
        return '\n'.join(lines)

    def _buildIntermediateSection(self, context: SummaryContext) -> str:
        '''构建“中间数据”小节（按配置限制条数）。'''
        lines = ['【二、中间数据（LLM 逐条评论打分结果）】']
        rows = context.intermediateData or []
        if not rows:
            lines.append('（暂无中间数据）')
            return '\n'.join(lines)
        limit = max(0, self._config.getInt('aiSummary', 'intermediateLimit', 100))
        shownRows = rows[:limit] if limit else rows
        lines.append(f'共 {len(rows)} 条，本次注入 {len(shownRows)} 条：')
        for index, row in enumerate(shownRows, start=1):
            comment = str(row.get('comment', '')).replace('\n', ' ').strip()
            scores = row.get('scores') or {}
            scoreText = '，'.join(
                f'{name}={scores[name] if scores.get(name) is not None else 'Null'}'
                for name in scores
            )
            lines.append(
                f'  {index}. 评论：{comment} | 维度分：{scoreText or '无'}'
                f' | 置信度：{row.get('credibility', 0)}',
            )
        if len(shownRows) < len(rows):
            lines.append(f'  （其余 {len(rows) - len(shownRows)} 条已按 intermediateLimit 省略）')
        return '\n'.join(lines)

    def _buildCorrectionSection(self, context: SummaryContext) -> str:
        '''构建“修正因子”小节（未介入时显式说明）。'''
        lines = ['【三、修正因子】']
        if context.correctionFactor is None:
            lines.append('未介入（本次汇总未使用修正因子）')
        else:
            lines.append(f'修正因子：{context.correctionFactor:.2f}（0-1，表示对结果的可信程度）')
        return '\n'.join(lines)

    def _buildSummarySection(self, context: SummaryContext) -> str:
        '''构建“汇总”小节。'''
        lines = ['【四、汇总】']
        if not context.dimensionAverages and not context.finalScore:
            lines.append('（暂无汇总数据）')
            return '\n'.join(lines)
        lines.append(f'商品名：{context.goodsName or '（未知）'}')
        lines.append(f'最终得分：{context.finalScore:.2f}')
        lines.append(f'评论总数：{context.totalCommentCount} · 有效评论：{context.validCommentCount}')
        lines.append(
            f'置信度阈值：{context.credibilityThreshold:.2f}'
            f' · 截尾比例：{context.trimPercent:.0f}%',
        )
        if context.dimensionAverages:
            lines.append('各维度平均分与加权分：')
            for name, average in context.dimensionAverages.items():
                averageText = f'{average:.1f}' if average is not None else '无数据'
                weighted = context.dimensionWeightedScores.get(name)
                weightedText = f'{weighted:.2f}' if weighted is not None else '无数据'
                lines.append(f'  - {name}：均分 {averageText}，加权分 {weightedText}')
        return '\n'.join(lines)

    # ---------- 请求 ----------

    def ask(
        self,
        context: SummaryContext,
        history: list[HistoryTurn],
        question: str,
    ) -> str:
        '''发起一次 AI 总结问答。

        Args:
            context: 注入数据上下文。
            history: 该商品的历史对话。
            question: 用户提问。

        Returns:
            str: 模型回答文本。

        Raises:
            RuntimeError: 重试耗尽仍失败时抛出。
        '''
        client = self._requireClient()
        model = self._config.getStr('aiSummary', 'model', 'deepseek-chat')
        maxTokens = self._config.getInt('aiSummary', 'maxTokens', 1200)
        temperature = self._config.getFloat('aiSummary', 'temperature', 0.3)
        maxRetries = self._config.getInt('llm', 'maxRetries', 3)
        messages = self.buildMessages(context, history, question)
        logger.info(
            '发起 AI 总结请求（模型 %s，注入数据 %d 项，消息 %d 条，携带历史 %d 轮）',
            model,
            len(context.intermediateData or []),
            len(messages),
            len(history),
        )
        lastError: Exception | None = None
        for attempt in range(maxRetries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=maxTokens,
                    temperature=temperature,
                )
                content = str(response.choices[0].message.content or '').strip()
                logger.info('AI 总结回答成功：%d 字', len(content))
                return content
            except Exception as error:  # noqa: BLE001 - 统一重试
                lastError = error
                waitSeconds = min(2.0 * (2**attempt), 30.0)
                logger.warning(
                    'AI 总结请求失败（第 %d/%d 次），%.1f 秒后重试：%s',
                    attempt + 1,
                    maxRetries + 1,
                    waitSeconds,
                    error,
                )
                if attempt < maxRetries:
                    time.sleep(waitSeconds)
        msg = f'AI 总结请求失败：{lastError}'
        raise RuntimeError(msg)
