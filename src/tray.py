# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

import theme
from config import ICON_PATH, APP_NAME, MENU_ICON_COLOR


class Tray(QObject):
    def __init__(self, app, pet):
        super().__init__()
        self.app = app
        self.pet = pet
        self.icon = QSystemTrayIcon(QIcon(str(ICON_PATH)))
        self.icon.setToolTip(APP_NAME)

        self.menu = theme.make_menu()                # 与右键菜单同一套圆角+图标
        self.toggle_action = theme.add_item(self.menu, "隐藏", "hide", self.toggle)
        self.menu.addSeparator()
        theme.add_item(self.menu, "退出", "quit", self.quit)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.on_activated)
        self.icon.show()

    def toggle(self):
        if self.pet.isVisible():
            self.pet.hide()
        else:
            self.pet.show()
            # 手动叫出来就是要看：这次全屏期间别再自动躲回去
            self.pet.leave_fullscreen_hidden()
        self.update_visibility()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle()

    def update_visibility(self):
        visible = self.pet.isVisible()
        self.toggle_action.setText("隐藏" if visible else "显示")
        self.toggle_action.setIcon(
            theme.icon("hide" if visible else "eye", MENU_ICON_COLOR))

    def quit(self):
        self.icon.hide()
        self.app.quit()
