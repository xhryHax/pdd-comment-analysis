from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from src.data.configAccess import ConfigAccess
from src.data.database import Database
from src.data.loggerSetup import LoggerSetup
from src.data.strategyFileAccess import StrategyFileAccess
from src.interface.tools.qtLogHandler import QtLogHandler
from src.interface.tools.styleLoader import loadTheme
from src.interface.view.aiSummaryHost import AiSummaryHost
from src.interface.view.analysisView import AnalysisView
from src.interface.view.logView import LogView
from src.interface.view.mainWindow import MainWindow
from src.interface.view.recordsView import RecordsView
from src.interface.view.settingsView import SettingsView
from src.interface.view.strategyView import StrategyView
from src.interface.viewModel.aiSummaryViewModel import AiSummaryViewModel
from src.interface.viewModel.analysisViewModel import AnalysisViewModel
from src.interface.viewModel.logViewModel import LogViewModel
from src.interface.viewModel.recordsViewModel import RecordsViewModel
from src.interface.viewModel.settingsViewModel import SettingsViewModel
from src.interface.viewModel.strategyViewModel import StrategyViewModel
from src.work.browserTools import BrowserTools
from src.work.llmService import LlmService


def main() -> int:
    '''程序入口：装配配置、日志、数据层与 MVVM 界面并启动主窗口。

    Returns:
        int: 应用退出码。
    '''
    config = ConfigAccess()
    LoggerSetup.setup(config.getStr('app', 'logLevel', 'info'))
    app = QApplication(sys.argv)
    app.setApplicationName('pdd-comment-analyzer')
    loadTheme(app, config.getStr('app', 'theme', 'light'))

    database = Database()
    fileAccess = StrategyFileAccess()
    browserTools = BrowserTools(config)
    llmService = LlmService(config)

    analysisViewModel = AnalysisViewModel(config, database, browserTools, llmService)
    strategyViewModel = StrategyViewModel(config, database, fileAccess)
    recordsViewModel = RecordsViewModel(database)
    settingsViewModel = SettingsViewModel(config)
    logViewModel = LogViewModel(QtLogHandler())

    analysisView = AnalysisView(analysisViewModel)
    analysisView.setStrategyItems(strategyViewModel.items)
    strategyViewModel.strategiesChanged.connect(
        lambda: analysisView.setStrategyItems(strategyViewModel.items),
    )
    recordsView = RecordsView(recordsViewModel)
    strategyView = StrategyView(strategyViewModel)
    settingsView = SettingsView(settingsViewModel)
    settingsView.themeChangeRequested.connect(lambda themeName: loadTheme(app, themeName))
    logView = LogView(logViewModel)

    window = MainWindow([analysisView, recordsView, strategyView, settingsView, logView])
    aiSummaryViewModel = AiSummaryViewModel(config, database)
    summaryHost = AiSummaryHost(aiSummaryViewModel, window)

    # AI 智能总结：入口请求 → 先切换上下文，再显示（或刷新）弹窗
    analysisView.aiSummaryRequested.connect(aiSummaryViewModel.setContext)
    analysisView.aiSummaryRequested.connect(summaryHost.show)
    recordsView.recordOpened.connect(
        lambda record: aiSummaryViewModel.setContext(recordsViewModel.summaryContext(record)),
    )
    recordsView.recordOpened.connect(summaryHost.show)
    # 重置仅清理界面状态，不删除已入库内容
    analysisView.resetRequested.connect(summaryHost.hide)
    analysisView.resetRequested.connect(aiSummaryViewModel.clearContext)
    analysisView.resetRequested.connect(analysisViewModel.clearLatestContext)
    # 主窗口切换页面时自动隐藏并销毁弹窗，切回不会自动恢复
    window.pageSwitched.connect(summaryHost.hide)

    window.show()
    return app.exec()




if __name__ == '__main__':
    raise SystemExit(main())


