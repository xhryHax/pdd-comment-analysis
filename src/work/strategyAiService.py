from __future__ import annotations

import logging
import re
import time
from typing import ClassVar

from openai import OpenAI

from src.data.configAccess import ConfigAccess
from src.data.loggerSetup import maskSecret
from src.work.analysisStrategy import AnalysisStrategy
from src.work.llmService import LlmService

logger = logging.getLogger(__name__)


class StrategyAiService:
    '''AI 分析策略生成服务：自然语言需求 → 分析策略。'''

    _systemPrompt: ClassVar[str] = (
        '你是一位电商商品质量分析专家，负责为特定品类商品设计评论分析策略。\n'
        '输出要求：仅输出一个 JSON 对象（不要输出任何其他文字），结构如下：\n'
        '{\n'
        '  "name": "策略名称（品类名）",\n'
        '  "dimensions": [\n'
        '    {"name": "维度名", "description": "维度含义描述", "weight": 0.3, "emphasized": true}\n'
        '  ],\n'
        '  "ratingPrompt": "评分提示词",\n'
        '  "credibilityPrompt": "置信度提示词"\n'
        '}\n'
        '约束：\n'
        '1. 维度数量 3-8 个，覆盖该品类最关键的质量维度；\n'
        '2. weight 为 0-1 的浮点数，所有维度权重之和为 1；\n'
        '3. emphasized 表示该维度是否为强调维度（核心必分析维度）；\n'
        '4. ratingPrompt 需要求逐条评论打 0-100 整数分，未提及输出 null，'
        '并说明 0/50/100 分的含义；\n'
        '5. credibilityPrompt 需要求对每条评论输出 0-1 的可信度小数，'
        '给出高/低可信度的判断标准。'
    )

    def __init__(self, config: ConfigAccess, llmService: LlmService | None = None) -> None:
        '''初始化策略生成服务。

        Args:
            config: 系统配置读写器。
            llmService: 可复用的 LLM 服务；缺省时按配置新建。
        '''
        self._config = config
        self._llmService = llmService if llmService is not None else LlmService(config)

    def generateStrategy(self, requirement: str, maxRetries: int = 2) -> AnalysisStrategy:
        '''根据自然语言需求生成分析策略。

        Args:
            requirement: 用户的需求描述（如“为机械键盘设计分析策略”）。
            maxRetries: 生成失败后的重试次数。

        Returns:
            AnalysisStrategy: 校验通过且权重归一化的策略（source 为
            'user'，strategyId 由策略名生成）。

        Raises:
            ValueError: 重试耗尽后仍未生成合法策略时抛出。
        '''
        apiKey = self._config.getStr('llm', 'apiKey', '')
        if not apiKey:
            msg = '未配置 DeepSeek API Key，无法使用 AI 生成策略'
            raise ValueError(msg)
        baseUrl = self._config.getStr('llm', 'baseUrl', 'https://api.deepseek.com')
        model = self._config.getStr('llm', 'model', 'deepseek-chat')
        timeout = self._config.getFloat('llm', 'requestTimeoutSeconds', 120.0)
        client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)
        logger.info('开始 AI 生成分析策略（模型 %s，apiKey=%s）', model, maskSecret(apiKey))
        lastError: Exception | None = None
        for attempt in range(maxRetries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': self._systemPrompt},
                        {'role': 'user', 'content': requirement},
                    ],
                    response_format={'type': 'json_object'},
                )
                content = str(response.choices[0].message.content or '')
                strategy = self._parseStrategy(content)
                logger.info('AI 生成策略成功：%s（%d 个维度）', strategy.name, len(strategy.dimensions))
                return strategy
            except Exception as error:  # noqa: BLE001 - 统一重试
                lastError = error
                waitSeconds = min(2.0 * (2**attempt), 30.0)
                logger.warning(
                    '策略生成失败（第 %d/%d 次），%.1f 秒后重试：%s',
                    attempt + 1,
                    maxRetries + 1,
                    waitSeconds,
                    error,
                )
                time.sleep(waitSeconds)
        msg = f'AI 生成策略失败：{lastError}'
        raise ValueError(msg)

    def _parseStrategy(self, content: str) -> AnalysisStrategy:
        '''解析并校验 LLM 生成的策略 JSON。

        Args:
            content: LLM 输出的原始文本。

        Returns:
            AnalysisStrategy: 归一化后的策略实例。

        Raises:
            ValueError: 输出无法解析或校验不通过时抛出（含错误明细）。
        '''
        import json

        text = content.strip()
        fenceMatch = re.search(r'```(?:json)?\s*(.*?)\s*```', text, flags=re.DOTALL)
        if fenceMatch:
            text = fenceMatch.group(1)
        braceMatch = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if braceMatch:
            text = braceMatch.group(0)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            msg = f'AI 输出无法解析为 JSON：{error}'
            raise ValueError(msg) from error
        if not isinstance(data, dict):
            msg = 'AI 输出不是 JSON 对象'
            raise ValueError(msg)
        strategy = AnalysisStrategy.fromDict(data)
        strategy.source = 'user'
        strategy.strategyId = self._slugify(strategy.name)
        errors = strategy.validate()
        if errors:
            msg = 'AI 生成的策略不合法：' + '；'.join(errors)
            raise ValueError(msg)
        return strategy.normalized()

    def _slugify(self, name: str) -> str:
        '''将策略名转换为合法的策略 ID。

        Args:
            name: 策略名称。

        Returns:
            str: 仅含中文、字母、数字与下划线的策略 ID，冲突可能时
            由调用方（存储层）覆盖。
        '''
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]+', '_', name).strip('_')
        return cleaned or 'aiStrategy'
