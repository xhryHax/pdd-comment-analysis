from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from src.interface.view.aiSummaryDialog import AiSummaryDialog
from src.interface.viewModel.aiSummaryViewModel import AiSummaryViewModel

logger = logging.getLogger(__name__)


class AiSummaryHost(QObject):
    '''AI 智能总结弹窗的生命周期协调器。

    采用“隐藏即销毁”策略：每次请求显示时新建非模态弹窗，主窗口
    切换页面（或显式请求隐藏）时关闭并释放，切换回来不会自动恢复，
    需用户再次点击入口按钮。
    '''

    def __init__(
        self,
        viewModel: AiSummaryViewModel,
        parentWidget: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None:
        '''初始化协调器。

        Args:
            viewModel: AI 总结视图模型（弹窗与调用方共享）。
            parentWidget: 弹窗的 Qt 父控件（通常为主窗口），可在窗口
                创建后通过 setHostWidget 补齐。
            parent: Qt 父对象。
        '''
        super().__init__(parent)
        self._viewModel = viewModel
        self._parentWidget = parentWidget
        self._dialog: AiSummaryDialog | None = None

    def setHostWidget(self, widget: QWidget) -> None:
        '''设置弹窗的宿主控件（通常为已创建的主窗口）。

        Args:
            widget: 宿主控件。
        '''
        self._parentWidget = widget

    @property
    def isVisible(self) -> bool:
        '''弹窗当前是否处于显示状态。'''
        dialog = self._dialog
        if dialog is None:
            return False
        try:
            return dialog.isVisible()
        except RuntimeError:
            # C++ 对象已释放
            self._dialog = None
            return False

    def show(self) -> None:
        '''显示弹窗（不存在则新建），已存在时仅刷新内容并置顶。'''
        dialog = self._dialog
        if dialog is None:
            dialog = AiSummaryDialog(self._viewModel, self._parentWidget)
            self._dialog = dialog
            logger.info('已创建 AI 智能总结弹窗')
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def hide(self) -> None:
        '''隐藏并销毁弹窗（不清除已达成的对话数据与上下文）。'''
        dialog = self._dialog
        self._dialog = None
        if dialog is None:
            return
        try:
            dialog.close()
        except RuntimeError:
            logger.debug('AI 智能总结弹窗已释放，跳过关闭')
            return
        dialog.deleteLater()
        logger.info('已销毁 AI 智能总结弹窗')
