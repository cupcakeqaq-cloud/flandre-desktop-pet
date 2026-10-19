# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

import time

from PySide6.QtCore import QObject, QTimer

import dialogue


class HourlyReporter(QObject):
    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self._last_hour = None
        self.timer = QTimer(self)
        self.timer.setInterval(20000)  # 每 20 秒检查一次是否跨整点
        self.timer.timeout.connect(self._check)
        self.timer.start()

    def _check(self):
        now = time.localtime()
        # 跨小时的判定放宽到「整点后 5 分钟内」。只比 tm_hour 的话，电脑睡眠/短暂卡顿
        # 会让 20 秒的轮询整个跳过那一分钟，这一小时的播报就永远没了。
        if self._last_hour is None:
            self._last_hour = now.tm_hour
            return
        if now.tm_hour != self._last_hour and now.tm_min <= 5:
            self._last_hour = now.tm_hour
            greeting = dialogue.pick("hourly_" + dialogue.period_key())
            self.pet.say(f"现在{now.tm_hour}点啦。" + greeting)
