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
        if self._last_hour is None:
            self._last_hour = now.tm_hour
            return
        if now.tm_hour != self._last_hour:
            self._last_hour = now.tm_hour
            greeting = dialogue.pick("hourly_" + dialogue.period_key())
            self.pet.say(f"现在{now.tm_hour}点啦。" + greeting)
