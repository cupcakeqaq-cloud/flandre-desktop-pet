# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu

from config import ICON_PATH, APP_NAME


class Tray(QObject):
    def __init__(self, app, pet):
        super().__init__()
        self.app = app
        self.pet = pet
        self.icon = QSystemTrayIcon(QIcon(str(ICON_PATH)))
        self.icon.setToolTip(APP_NAME)

        self.menu = QMenu()
        self.toggle_action = self.menu.addAction("隐藏")
        self.toggle_action.triggered.connect(self.toggle)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("退出")
        quit_action.triggered.connect(self.quit)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.on_activated)
        self.icon.show()

    def toggle(self):
        if self.pet.isVisible():
            self.pet.hide()
        else:
            self.pet.show()
        self.update_visibility()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle()

    def update_visibility(self):
        self.toggle_action.setText("隐藏" if self.pet.isVisible() else "显示")

    def quit(self):
        self.icon.hide()
        self.app.quit()
