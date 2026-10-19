from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.interface.viewModel.settingsViewModel import SettingsViewModel


class SettingsView(QWidget):
    '''系统设置页：界面主题、运行参数表单、API 凭证与操作栏。'''

    themeChangeRequested = Signal(str)

    def __init__(self, viewModel: SettingsViewModel, parent: QWidget | None = None) -> None:
        '''初始化页面并绑定视图模型。

        Args:
            viewModel: 设置页视图模型。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._buildUi()
        self._connectSignals()
        self._loadFromSnapshot(viewModel.snapshot())

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

        titleLabel = QLabel('系统设置')
        titleLabel.setProperty('headingLevel', '1')
        contentLayout.addWidget(titleLabel)

        # 界面主题
        appearanceCard = QFrame()
        appearanceCard.setProperty('card', 'true')
        appearanceForm = QFormLayout(appearanceCard)
        appearanceForm.setContentsMargins(20, 20, 20, 20)
        appearanceForm.setSpacing(10)
        self._themeCombo = QComboBox()
        self._themeCombo.addItem('浅色（黑白编辑风）', 'light')
        self._themeCombo.addItem('深色（Voltagent 暗色）', 'dark')
        self._themeCombo.setToolTip('切换立即生效，需点击“保存设置”持久化')
        appearanceForm.addRow('界面主题', self._themeCombo)
        contentLayout.addWidget(appearanceCard)

        # 采集与判定参数
        analysisCard = QFrame()
        analysisCard.setProperty('card', 'true')
        analysisForm = QFormLayout(analysisCard)
        analysisForm.setContentsMargins(20, 20, 20, 20)
        analysisForm.setSpacing(10)
        self._commentThresholdSpin = QSpinBox()
        self._commentThresholdSpin.setRange(1, 500)
        self._commentThresholdSpin.setToolTip('抓取评论条数低于该值时触发维度重构')
        self._commentBatchSizeSpin = QSpinBox()
        self._commentBatchSizeSpin.setRange(10, 200)
        self._commentMaxCountSpin = QSpinBox()
        self._commentMaxCountSpin.setRange(50, 5000)
        self._commentMaxCountSpin.setSingleStep(50)
        self._credibilityThresholdSpin = QDoubleSpinBox()
        self._credibilityThresholdSpin.setRange(0.0, 1.0)
        self._credibilityThresholdSpin.setSingleStep(0.05)
        self._trimPercentSpin = QDoubleSpinBox()
        self._trimPercentSpin.setRange(0.0, 50.0)
        self._trimPercentSpin.setSingleStep(1.0)
        self._trimPercentSpin.setSuffix('%')
        self._validCommentThresholdSpin = QSpinBox()
        self._validCommentThresholdSpin.setRange(1, 200)
        analysisForm.addRow('评论数阈值（触发维度重构）', self._commentThresholdSpin)
        analysisForm.addRow('抓取批大小', self._commentBatchSizeSpin)
        analysisForm.addRow('单次抓取上限', self._commentMaxCountSpin)
        analysisForm.addRow('置信度阈值', self._credibilityThresholdSpin)
        analysisForm.addRow('截尾比例（去除两端各 x%）', self._trimPercentSpin)
        analysisForm.addRow('有效评论阈值（触发修正因子）', self._validCommentThresholdSpin)
        contentLayout.addWidget(analysisCard)

        # LLM 与浏览器参数
        techCard = QFrame()
        techCard.setProperty('card', 'true')
        techForm = QFormLayout(techCard)
        techForm.setContentsMargins(20, 20, 20, 20)
        techForm.setSpacing(10)
        self._maxConcurrencySpin = QSpinBox()
        self._maxConcurrencySpin.setRange(1, 16)
        self._batchSizeSpin = QSpinBox()
        self._batchSizeSpin.setRange(10, 100)
        self._requestTimeoutSpin = QSpinBox()
        self._requestTimeoutSpin.setRange(10, 600)
        self._requestTimeoutSpin.setSuffix(' 秒')
        self._maxRetriesSpin = QSpinBox()
        self._maxRetriesSpin.setRange(0, 10)
        self._baseUrlEdit = QLineEdit()
        self._modelEdit = QLineEdit()
        self._driverPathEdit = QLineEdit()
        self._timezoneEdit = QLineEdit()
        self._languageEdit = QLineEdit()
        self._localeEdit = QLineEdit()
        techForm.addRow('LLM 并发数', self._maxConcurrencySpin)
        techForm.addRow('LLM 批大小（条/请求）', self._batchSizeSpin)
        techForm.addRow('请求超时', self._requestTimeoutSpin)
        techForm.addRow('失败重试次数', self._maxRetriesSpin)
        techForm.addRow('DeepSeek Base URL', self._baseUrlEdit)
        techForm.addRow('模型名称', self._modelEdit)
        techForm.addRow('chromedriver 路径（UC 模式自动管理，预留）', self._driverPathEdit)
        techForm.addRow('指纹时区', self._timezoneEdit)
        techForm.addRow('指纹语言', self._languageEdit)
        techForm.addRow('指纹区域', self._localeEdit)
        contentLayout.addWidget(techCard)

        # 凭证
        credentialCard = QFrame()
        credentialCard.setProperty('card', 'soft')
        credentialLayout = QFormLayout(credentialCard)
        credentialLayout.setContentsMargins(20, 20, 20, 20)
        credentialLayout.setSpacing(10)
        self._apiKeyEdit = QLineEdit()
        self._apiKeyEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self._apiKeyEdit.setPlaceholderText('sk-...')
        self._testButton = QPushButton('测试连接')
        self._testButton.setProperty('variant', 'ghost')
        credentialLayout.addRow('DeepSeek API Key', self._apiKeyEdit)
        credentialLayout.addRow('', self._testButton)
        contentLayout.addWidget(credentialCard)

        # 操作栏
        actionRow = QHBoxLayout()
        self._saveButton = QPushButton('保存设置')
        self._saveButton.setProperty('variant', 'primary')
        self._resetButton = QPushButton('恢复默认')
        self._resetButton.setProperty('variant', 'ghost')
        self._statusLabel = QLabel('')
        self._statusLabel.setProperty('caption', True)
        actionRow.addWidget(self._saveButton)
        actionRow.addWidget(self._resetButton)
        actionRow.addStretch(1)
        actionRow.addWidget(self._statusLabel)
        contentLayout.addLayout(actionRow)
        contentLayout.addStretch(1)
        scrollArea.setWidget(contentWidget)
        rootLayout.addWidget(scrollArea)

    def _connectSignals(self) -> None:
        '''绑定信号。'''
        self._saveButton.clicked.connect(self._onSaveClicked)
        self._resetButton.clicked.connect(self._onResetClicked)
        self._testButton.clicked.connect(self._onTestClicked)
        self._themeCombo.currentIndexChanged.connect(self._onThemeChanged)
        self._viewModel.saved.connect(lambda: self._statusLabel.setText('设置已保存'))
        self._viewModel.connectionTested.connect(self._onConnectionTested)

    def _loadFromSnapshot(self, snapshot: dict[str, dict[str, Any]]) -> None:
        '''用配置快照填充表单。'''
        app = snapshot.get('app', {})
        crawl = snapshot.get('crawl', {})
        analysis = snapshot.get('analysis', {})
        llm = snapshot.get('llm', {})
        browser = snapshot.get('browser', {})
        with QSignalBlocker(self._themeCombo):
            themeIndex = self._themeCombo.findData(str(app.get('theme', 'light')))
            self._themeCombo.setCurrentIndex(max(0, themeIndex))
        self._commentThresholdSpin.setValue(int(crawl.get('commentThreshold', 20)))
        self._commentBatchSizeSpin.setValue(int(crawl.get('commentBatchSize', 50)))
        self._commentMaxCountSpin.setValue(int(crawl.get('commentMaxCount', 600)))
        self._credibilityThresholdSpin.setValue(float(analysis.get('credibilityThreshold', 0.6)))
        self._trimPercentSpin.setValue(float(analysis.get('trimPercent', 5)))
        self._validCommentThresholdSpin.setValue(int(analysis.get('validCommentThreshold', 10)))
        self._maxConcurrencySpin.setValue(int(llm.get('maxConcurrency', 4)))
        self._batchSizeSpin.setValue(int(llm.get('batchSize', 50)))
        self._requestTimeoutSpin.setValue(int(llm.get('requestTimeoutSeconds', 120)))
        self._maxRetriesSpin.setValue(int(llm.get('maxRetries', 3)))
        self._baseUrlEdit.setText(str(llm.get('baseUrl', 'https://api.deepseek.com')))
        self._modelEdit.setText(str(llm.get('model', 'deepseek-chat')))
        self._apiKeyEdit.setText(str(llm.get('apiKey', '')))
        self._driverPathEdit.setText(str(crawl.get('driverPath', '')))
        self._timezoneEdit.setText(str(browser.get('timezone', 'Asia/Shanghai')))
        self._languageEdit.setText(str(browser.get('language', 'zh-CN')))
        self._localeEdit.setText(str(browser.get('locale', 'zh_CN')))
        self._statusLabel.setText('')

    def _collectValues(self) -> dict[str, dict[str, Any]]:
        '''收集表单值为嵌套配置字典。'''
        return {
            'app': {
                'theme': str(self._themeCombo.currentData() or 'light'),
            },
            'crawl': {
                'commentThreshold': self._commentThresholdSpin.value(),
                'commentBatchSize': self._commentBatchSizeSpin.value(),
                'commentMaxCount': self._commentMaxCountSpin.value(),
                'driverPath': self._driverPathEdit.text().strip(),
            },
            'analysis': {
                'credibilityThreshold': self._credibilityThresholdSpin.value(),
                'trimPercent': self._trimPercentSpin.value(),
                'validCommentThreshold': self._validCommentThresholdSpin.value(),
            },
            'llm': {
                'apiKey': self._apiKeyEdit.text().strip(),
                'baseUrl': self._baseUrlEdit.text().strip() or 'https://api.deepseek.com',
                'model': self._modelEdit.text().strip() or 'deepseek-chat',
                'maxConcurrency': self._maxConcurrencySpin.value(),
                'batchSize': self._batchSizeSpin.value(),
                'requestTimeoutSeconds': self._requestTimeoutSpin.value(),
                'maxRetries': self._maxRetriesSpin.value(),
            },
            'browser': {
                'timezone': self._timezoneEdit.text().strip() or 'Asia/Shanghai',
                'language': self._languageEdit.text().strip() or 'zh-CN',
                'locale': self._localeEdit.text().strip() or 'zh_CN',
            },
        }

    def _onSaveClicked(self) -> None:
        '''保存设置。'''
        self._viewModel.save(self._collectValues())

    def _onResetClicked(self) -> None:
        '''恢复默认设置。'''
        self._loadFromSnapshot(self._viewModel.resetDefaults())
        self.themeChangeRequested.emit(str(self._themeCombo.currentData() or 'light'))
        self._statusLabel.setText('已恢复默认设置并保存')

    def _onThemeChanged(self) -> None:
        '''主题下拉框切换：立即应用新主题（持久化依赖保存按钮）。'''
        self.themeChangeRequested.emit(str(self._themeCombo.currentData() or 'light'))

    def _onTestClicked(self) -> None:
        '''先保存表单再测试连接（测试使用保存后的 Key）。'''
        self._viewModel.save(self._collectValues())
        self._statusLabel.setText('正在测试连接……')
        self._testButton.setEnabled(False)
        self._viewModel.testConnection()

    def _onConnectionTested(self, ok: bool, message: str) -> None:
        '''连接测试结果展示。'''
        self._testButton.setEnabled(True)
        self._statusLabel.setText('连接成功' if ok else '连接失败')
        from PySide6.QtWidgets import QMessageBox

        if ok:
            QMessageBox.information(self, '连接成功', f'DeepSeek 回复：{message}')
        else:
            QMessageBox.warning(self, '连接失败', message)
