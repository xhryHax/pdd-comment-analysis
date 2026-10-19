from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Generator
from enum import Enum
from typing import Any, ClassVar

from browserforge.fingerprints import FingerprintGenerator, Screen
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from seleniumbase.core import browser_launcher

from src.data.configAccess import ConfigAccess

logger = logging.getLogger(__name__)


class LoginStatus(Enum):
    '''页面登录状态枚举。'''

    needLogin = 1
    notNeedLogin = 2


class BrowserTools:
    '''基于 SeleniumBase UC Mode 的拼多多移动端页面采集工具。

    通过 UC Mode（undetected）启动 Chrome，CDP 注入 BrowserForge
    生成的指纹并抹除 navigator.webdriver；提供打开商品页、登录
    轮询、商品名提取、进入评论页与分批滚动抓取评论的能力。
    '''
    _loginUrlKey: ClassVar[str] = 'mobile.yangkeduo.com/login.html'
    # 商品名候选 XPath：按可信度从高到低排列。
    # 页面区块索引（div[3] / div[5]、span[1] / span[2]）会随版本漂移，
    # 因此候选表达式不绑定这些索引，改为遍历命中节点取首个非空文本；
    # 末尾保留两条历史精确路径，用于兼容旧版页面结构。
    _goodsNameXpaths: ClassVar[list[str]] = [
        '//*[@id="main"]//h1',
        '//h1',
        '//*[@id="main"]/div/div[2]/div/div/span/span/span',
        '//*[@id="main"]//div/div/span/span/span',
        '/html/body/div[1]/div/div[2]/div[3]/div/span/span[2]/span',
        '/html/body/div[1]/div/div[2]/div[5]/div/span/span[1]/span',
    ]
    # 单条候选 XPath 最多扫描的节点数（避免宽泛表达式拖慢提取）
    _goodsNameScanLimit: ClassVar[int] = 20
    # 无商品名信息时的浏览器标题兜底值（站点通用标题，不可作为商品名）
    _genericSiteTitle: ClassVar[str] = '拼多多'
    _commentButtonXpaths: ClassVar[list[str]] = [
        '/html/body/div[4]/div/div[2]/div[10]/div[1]/div/span',
        '/html/body/div[1]/div/div[2]/div[13]/div[1]/div/span',
        '//*[@id="main"]/div/div[2]//span[contains(text(), "查看全部")]',
        '//*[contains(text(), "查看全部")]',
    ]
    _commentTotalXpaths: ClassVar[list[str]] = [
        '//*[@id="main"]/div[1]/div[1]/ul/li[1]',
        '/html/body/div[1]/div[1]/div[2]/div/div/ul/li[1]',
    ]
    _commentItemXpathTemplates: ClassVar[list[str]] = [
        '/html/body/div[1]/div[1]/div[2]/div/div/div[{index}]/div[3]/span',
        '//*[@id="goods-comments-list"]/div/div/div[{index}]/div[3]/span',
    ]
    _commentListXpaths: ClassVar[list[str]] = [
        '//*[@id="goods-comments-list"]',
        '/html/body/div[1]/div[1]/div[2]/div/div',
    ]

    def __init__(self, config: ConfigAccess) -> None:
        '''初始化采集工具（惰性启动浏览器）。

        Args:
            config: 系统配置读写器，用于读取抓取与指纹参数。
        '''
        self._config = config
        self._driver: WebDriver | None = None

    # ---------- 启动与指纹 ----------

    def start(self) -> None:
        '''启动 UC Mode 浏览器；已启动时直接返回，可安全重复调用。'''
        if self._driver is not None:
            return
        language = self._config.getStr('browser', 'language', 'zh-CN')
        locale = self._config.getStr('browser', 'locale', 'zh_CN')
        driver = browser_launcher.get_driver(
            browser_name='chrome',
            undetectable=True,
            locale_code=locale,
        )
        driver.execute_cdp_cmd(
            'Page.addScriptToEvaluateOnNewDocument',
            {'source': self._buildFingerprintJs()},
        )
        timezone = self._config.getStr('browser', 'timezone', 'Asia/Shanghai')
        try:
            driver.execute_cdp_cmd('Emulation.setTimezoneOverride', {'timezoneId': timezone})
        except Exception as error:  # noqa: BLE001 - CDP 能力探测，失败不影响主流程
            logger.warning('设置时区失败（忽略）：%s', error)
        try:
            driver.execute_cdp_cmd(
                'Emulation.setLocaleOverride',
                {'locale': locale.replace('_', '-')},
            )
        except Exception as error:  # noqa: BLE001
            logger.warning('设置区域失败（忽略）：%s', error)
        self._driver = driver
        logger.info(
            'UC Mode 浏览器已启动（语言 %s / 区域 %s / 时区 %s）',
            language,
            locale,
            timezone,
        )

    def _buildFingerprintJs(self) -> str:
        '''构建注入到新文档的指纹伪装 JS。

        使用 BrowserForge 生成导航器指纹，抹除 navigator.webdriver
        并以配置的语言覆盖 language 相关属性。

        Returns:
            str: 待注入的自执行 JS 片段。
        '''
        fingerprint = FingerprintGenerator().generate(
            screen=Screen(min_width=1280, min_height=800),
        )
        navigator = fingerprint.navigator
        language = self._config.getStr('browser', 'language', 'zh-CN')
        languages = [language, language.split('-')[0]]
        properties: dict[str, Any] = {
            'languages': languages,
            'platform': navigator.platform,
            'hardwareConcurrency': navigator.hardwareConcurrency,
            'vendor': navigator.vendor,
            'maxTouchPoints': navigator.maxTouchPoints,
        }
        if navigator.deviceMemory is not None:
            properties['deviceMemory'] = navigator.deviceMemory
        if navigator.doNotTrack is not None:
            properties['doNotTrack'] = navigator.doNotTrack
        if navigator.userAgentData is not None:
            properties['userAgentData'] = dict(navigator.userAgentData)
        lines = ['Object.defineProperty(navigator, "webdriver", {get: () => undefined});']
        for key, value in properties.items():
            lines.append(
                f'Object.defineProperty(navigator, {json.dumps(key)}, '
                f'{{get: () => {json.dumps(value, ensure_ascii=False)}}});'
            )
        return '(() => {\n' + '\n'.join(lines) + '\n})();'

    def _requireDriver(self) -> WebDriver:
        '''获取已就绪的浏览器驱动，尚未启动时自动启动。'''
        if self._driver is None:
            self.start()
        driver = self._driver
        assert driver is not None
        return driver

    # ---------- 登录 ----------

    def _checkLoginStatus(self) -> LoginStatus:
        '''依据当前页面 URL 判定登录状态。'''
        currentUrl = self._requireDriver().current_url
        if self._loginUrlKey in currentUrl:
            return LoginStatus.needLogin
        return LoginStatus.notNeedLogin

    def openGoodsPage(self, goodsUrl: str) -> LoginStatus:
        '''打开商品页面并判断是否需要登录。

        Args:
            goodsUrl: 商品页 URL 地址。

        Returns:
            LoginStatus: 是否需要登录的状态。
        '''
        self._requireDriver().get(goodsUrl)
        time.sleep(self._config.getFloat('crawl', 'redirectWaitSeconds', 3.0))
        return self._checkLoginStatus()

    def waitForLogin(self) -> bool:
        '''轮询等待用户在浏览器中手动完成登录。

        Returns:
            bool: 登录成功返回 True，等待超时返回 False。
        '''
        interval = self._config.getFloat('crawl', 'loginCheckInterval', 0.5)
        timeout = self._config.getFloat('crawl', 'loginTimeoutSeconds', 180.0)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._checkLoginStatus() is LoginStatus.notNeedLogin:
                logger.info('检测到登录完成')
                return True
            time.sleep(interval)
        logger.warning('等待登录超时（%.0f 秒）', timeout)
        return False

    # ---------- 页面数据 ----------

    def _findFirstElement(self, xpaths: list[str]):
        '''按顺序尝试多个 XPath，返回第一个命中的元素。

        Args:
            xpaths: XPath 候选列表。

        Returns:
            WebElement | None: 命中的元素，全部未命中返回 None。
        '''
        driver = self._requireDriver()
        for xpath in xpaths:
            try:
                return driver.find_element(By.XPATH, xpath)
            except NoSuchElementException:
                continue
        return None

    def _findFirstText(self, xpaths: list[str]) -> str | None:
        '''按顺序尝试多个 XPath，返回首个命中的非空文本。

        与 _findFirstElement 的区别：每条表达式都会遍历命中的全部节点
        （上限 _goodsNameScanLimit），并在非空候选文本中取字符数最多的
        一条。定位表达式本身不带会漂移的区块索引，命中集合随页面版本
        变化时仍能选到商品名（商品名通常比价格、标签等邻近区块更长）。

        Args:
            xpaths: XPath 候选列表。

        Returns:
            str | None: 首个命中的文本，全部未命中返回 None。
        '''
        driver = self._requireDriver()
        for xpath in xpaths:
            try:
                elements = driver.find_elements(By.XPATH, xpath)
            except Exception as error:  # noqa: BLE001 - 表达式异常不应中断后续候选
                logger.debug('XPath 查询失败，跳过：%s（%s）', xpath, error)
                continue
            texts: list[str] = []
            for element in elements[: self._goodsNameScanLimit]:
                try:
                    text = (element.text or '').strip()
                except StaleElementReferenceException:
                    continue
                if text:
                    texts.append(text)
            # 诊断日志：真实页面核对时可从日志确认各候选的命中情况
            logger.debug(
                '商品名候选 %s：命中 %d 个节点，非空文本 %d 条：%s',
                xpath,
                len(elements),
                len(texts),
                texts,
            )
            if texts:
                best = max(texts, key=len)
                logger.debug('商品名选定：%r（来自 %s）', best, xpath)
                return best
        return None

    def getGoodsName(self) -> str | None:
        '''从当前商品页提取商品名。

        优先按泛化候选 XPath 取页面元素文本，全部未命中时回落浏览器
        标题；文本仅做首尾空白裁剪，不做其它清洗。

        Returns:
            str | None: 商品名文本，无法提取时返回 None。
        '''
        text = self._findFirstText(self._goodsNameXpaths)
        if text:
            return text
        title = (self._requireDriver().title or '').strip()
        if title and title != self._genericSiteTitle:
            logger.info('XPath 未命中商品名，回落使用浏览器标题：%s', title)
            return title
        logger.warning('无法提取商品名')
        return None

    def openCommentPage(self) -> bool:
        '''触发“查看全部”进入评论页。

        常规点击被悬浮层遮挡时改用 JS 强制触发。

        Returns:
            bool: 评论列表容器出现返回 True，超时未出现返回 False。
        '''
        driver = self._requireDriver()
        commentButton = self._findFirstElement(self._commentButtonXpaths)
        if commentButton is None:
            logger.error('未找到进入评论区的按钮')
            return False
        driver.execute_script('arguments[0].scrollIntoView({block: "center"})', commentButton)
        try:
            commentButton.click()
        except ElementClickInterceptedException:
            logger.info('常规点击被遮挡，改用 JS 触发点击')
            driver.execute_script('arguments[0].click()', commentButton)
        for listXpath in self._commentListXpaths:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, listXpath)),
                )
                logger.info('已进入评论页')
                return True
            except TimeoutException:
                continue
        logger.warning('进入评论页后未检测到评论列表容器，当前 URL：%s', driver.current_url)
        return False

    def _parseCommentTotal(self) -> int | None:
        '''解析评论总数。

        支持“全部(7871)”与“全部(1.7万)”两种格式。

        Returns:
            int | None: 评论总条数，缺失或无法解析时返回 None。
        '''
        totalElement = self._findFirstElement(self._commentTotalXpaths)
        if totalElement is None:
            logger.warning('未找到评论总数元素')
            return None
        match = re.search(r'全部\(([\d.]+)(万)?\)', totalElement.text)
        if not match:
            logger.warning('无法解析评论总数，元素文本：%s', repr(totalElement.text))
            return None
        total = float(match.group(1))
        if match.group(2) == '万':
            total *= 10000
        return int(total)

    def getCommentSet(self) -> Generator[list[str]]:
        '''逐条提取评论文本并分批产出。

        评论未加载时向下滑动触发懒加载，连续多次滚动仍无新评论
        则提前结束；评论总数未知时以滚动重试上限为终止条件。

        Yields:
            list[str]: 每批评论文本（批大小由配置决定），末批可能不足。
        '''
        driver = self._requireDriver()
        total = self._parseCommentTotal()
        maxCount = self._config.getInt('crawl', 'commentMaxCount', 600)
        effectiveTotal = total if total is not None else maxCount
        effectiveTotal = min(effectiveTotal, maxCount)
        batchSize = self._config.getInt('crawl', 'commentBatchSize', 50)
        maxScrollRetry = self._config.getInt('crawl', 'maxScrollRetry', 5)
        scrollWait = self._config.getFloat('crawl', 'scrollWaitSeconds', 2.0)
        logger.info('评论总数：%s（本次抓取上限 %d 条）', total, effectiveTotal)
        index = 1
        fetched = 0
        batch: list[str] = []
        scrollRetry = 0
        while fetched < effectiveTotal:
            xpath = None
            element = None
            for template in self._commentItemXpathTemplates:
                xpath = template.format(index=index)
                try:
                    element = driver.find_element(By.XPATH, xpath)
                    break
                except NoSuchElementException:
                    continue
            if element is None or not element.text.strip():
                if scrollRetry >= maxScrollRetry:
                    logger.info(
                        '连续滚动 %d 次无新评论，提前结束（已获取 %d 条）',
                        maxScrollRetry,
                        fetched,
                    )
                    break
                driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(scrollWait)
                scrollRetry += 1
                continue
            batch.append(element.text.strip())
            index += 1
            fetched += 1
            scrollRetry = 0
            if len(batch) >= batchSize:
                yield batch
                batch = []
        if batch:
            yield batch
        logger.info('评论抓取完成，共获取 %d 条', fetched)

    def close(self) -> None:
        '''关闭浏览器驱动并释放系统资源（幂等，可重复调用）。'''
        driver = self._driver
        self._driver = None
        if driver is None:
            return
        try:
            driver.quit()
        except Exception as error:  # noqa: BLE001 - 关闭阶段尽力而为
            logger.warning('关闭浏览器驱动失败：%s', error)
        else:
            logger.info('浏览器驱动已关闭')
