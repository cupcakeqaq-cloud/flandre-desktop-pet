# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""番茄钟 + 倒计时。

设计要点（2026-10-08 第五批）：
- 番茄钟支持「做 N 个番茄」循环、长休息、第 i/N 个进度提示。
- 剩余时间**在同一个气泡里原地刷新**（不重新弹窗），并通过 Bubble.set_buttons 提供
  「暂停 / 继续 / 停止 / +1 分钟」按钮，鼠标不用离开角色。
- 任务完成 → 播 sound\\tada.wav + 切站立 4.png（开心）；整组做完 → sound\\TADA (2).wav。
"""

from PySide6.QtCore import QObject, Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QComboBox, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QFrame, QMessageBox,
)

import config
import dialogue
import sound
import theme
from data_manager import (
    MAX_CUSTOM_TYPES, load_settings, save_settings,
    get_custom_types, set_custom_types, get_all_types,
)


def reload_types(combo, kind, keep=""):
    """（重）填类型下拉框：把当前输入的自定义名保留下来，且不触发 changed 信号。"""
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(get_all_types(kind))
    if keep:
        if combo.findText(keep) < 0:
            combo.addItem(keep)
        combo.setCurrentText(keep)
    combo.blockSignals(False)


def open_type_manager(parent, combo, kind):
    """打开非模态类型管理窗；parent 必须持引用，否则窗口会被回收。"""
    dlg = TypeManagerDialog(parent, kind,
                            "管理任务类型" if kind == "task" else "管理事件类型")
    parent._type_dlg = dlg
    dlg.show()
    dlg.raise_()
    dlg.finished.connect(lambda _=0: reload_types(combo, kind, combo.currentText()))


def _mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _work_line(phase, index, done, total, task_type, remain):
    """番茄钟气泡正文：标题 + 进度 + 剩余时间，一眼能看全。

    每行都刻意压短（气泡正文宽 236px，像素字体 11pt 一行约 15 个汉字），
    否则会自动折行、折在「个」这种字上很难看。
    """
    index = max(1, min(int(index), int(total)))
    name = (task_type or "").strip()
    if phase == "focus":
        # 「专注中」由秒数行的节奏暗示，不再塞进第一行，免得折行
        line1 = f"第 {index}/{total} 个番茄"
        if name:
            line1 += f" · {name}"
        line2 = f"专注中  {_mmss(remain)}   已完成 {done}/{total}"
    elif phase == "long_break":
        line1 = f"长休息 · 已完成 {done}/{total}"
        line2 = f"{_mmss(remain)}   好好放松一下"
    else:
        line1 = f"短休息 · 已完成 {done}/{total}"
        line2 = f"{_mmss(remain)}   喝口水吧"
    return f"{line1}\n{line2}"


def _cd_line(task_type, remain, total, extra=""):
    name = (task_type or "").strip()
    head = f"倒计时 · {name}" if name else "倒计时"
    tail = f"   {extra}" if extra else ""
    return f"{head}\n{_mmss(remain)}{tail}"


# ==================== 自定义类型管理 ====================
class TypeManagerDialog(QDialog):
    """可保存 / 可删除的类型管理，最多 MAX_CUSTOM_TYPES 个（两处共用）。"""

    def __init__(self, parent, kind, title, placeholder="输入新的类型名称……"):
        super().__init__(parent)
        theme.setup_dialog(self, title)
        self.kind = kind
        self.placeholder = placeholder
        self._builtin, self._custom = get_custom_types(kind)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        cap = QLabel(f"自定义类型（最多 {MAX_CUSTOM_TYPES} 个）")
        cap.setObjectName("title")
        lay.addWidget(cap)

        hint = QLabel("内置类型：" + "、".join(self._builtin) + "<br>内置项不可删除，下面是你自己加的。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addWidget(theme.hline())

        self.list = QListWidget()
        self.list.setMinimumHeight(150)
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMaxLength(12)
        self.edit.returnPressed.connect(self._add)
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._add)
        row.addWidget(self.edit, 1)
        row.addWidget(add_btn)
        lay.addLayout(row)

        self.count = QLabel("")
        self.count.setObjectName("hint")
        lay.addWidget(self.count)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

        self._refresh()

    def _refresh(self):
        self.list.clear()
        for name in self._custom:
            item = QListWidgetItem(self.list)
            item.setSizeHint(self._row_size())
            self.list.setItemWidget(item, self._row_widget(name))
        self.count.setText(f"已添加 {len(self._custom)} / {MAX_CUSTOM_TYPES}")
        self.count.setStyleSheet(
            f"color: {'#8d7b68' if len(self._custom) < MAX_CUSTOM_TYPES else '#a4503c'};")

    @staticmethod
    def _row_size():
        return QSize(200, 38)

    def _row_widget(self, name):
        w = QFrame()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 2, 6, 2)
        lay.setSpacing(8)
        lab = QLabel(name)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("danger")
        del_btn.setProperty("tiny", True)
        del_btn.setToolTip(f"删除自定义类型「{name}」")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda _=False, n=name: self._remove(n))
        lay.addWidget(lab, 1)
        lay.addWidget(del_btn, 0)
        return w

    def _add(self):
        name = self.edit.text().strip()
        if not name:
            return
        if name in self._builtin or name in self._custom:
            QMessageBox.information(self, "提示", f"「{name}」已经存在啦。")
            return
        if len(self._custom) >= MAX_CUSTOM_TYPES:
            QMessageBox.information(
                self, "提示",
                f"最多只能加 {MAX_CUSTOM_TYPES} 个自定义类型，先删一个吧。")
            return
        self._custom.append(name)
        self.edit.clear()
        self._refresh()

    def _remove(self, name):
        if name in self._custom:
            self._custom.remove(name)
            self._refresh()

    def _save(self):
        set_custom_types(self.kind, self._custom)
        self.accept()


# ==================== 番茄钟 ====================
PRESETS = [("25 / 5", 25, 5), ("45 / 10", 45, 10), ("50 / 10", 50, 10)]


class PomodoroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        theme.setup_dialog(self, "番茄钟")
        self.setMinimumWidth(400)
        s = load_settings()
        last = s.get("pomodoro") or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("番茄钟")
        title.setObjectName("title")
        root.addWidget(title)
        tip = QLabel("专注一段时间，然后休息一下；做满一轮循环会有一次长休息。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        presets.addWidget(QLabel("常用"))
        for label, f, b in PRESETS:
            pb = QPushButton(label)
            pb.setObjectName("ghost")
            pb.setToolTip(f"专注 {f} 分钟 / 休息 {b} 分钟")
            pb.clicked.connect(lambda _=False, x=f, y=b: self._apply_preset(x, y))
            presets.addWidget(pb)
        presets.addStretch()
        root.addLayout(presets)

        card, form = theme.card_form()

        self.focus = theme.ChevronSpinBox()
        self.focus.setRange(1, 180)
        self.focus.setValue(int(last.get("focus", 25)))
        self.focus.setSuffix(" 分钟")
        form.addRow("专注时长", self.focus)

        self.break_ = theme.ChevronSpinBox()
        self.break_.setRange(1, 60)
        self.break_.setValue(int(last.get("break", 5)))
        self.break_.setSuffix(" 分钟")
        form.addRow("短休息", self.break_)

        self.cycles = theme.ChevronSpinBox()
        self.cycles.setRange(1, 20)
        self.cycles.setValue(int(last.get("cycles", 4)))
        self.cycles.setSuffix(" 个")
        self.cycles.setToolTip("这一轮要做几个番茄；做满就自动结束")
        form.addRow("循环次数", self.cycles)

        self.long_every = theme.ChevronSpinBox()
        self.long_every.setRange(0, 12)
        self.long_every.setValue(int(last.get("long_every", 4)))
        self.long_every.setSuffix(" 个")
        self.long_every.setToolTip("每做满这么多个番茄，休息一次长的；填 0 表示不要长休息")
        form.addRow("每几个番茄长休息", self.long_every)

        self.long_break = theme.ChevronSpinBox()
        self.long_break.setRange(1, 120)
        self.long_break.setValue(int(last.get("long_break", 15)))
        self.long_break.setSuffix(" 分钟")
        form.addRow("长休息时长", self.long_break)

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self.type = theme.ChevronComboBox()
        self.type.setEditable(True)
        self.type.setInsertPolicy(QComboBox.NoInsert)
        self.type.lineEdit().setPlaceholderText("不填也行")
        reload_types(self.type, "task", last.get("task_type", "") or "")
        manage = QPushButton("管理")
        manage.setObjectName("ghost")
        manage.setToolTip("添加 / 删除自定义任务类型（最多 3 个）")
        manage.clicked.connect(lambda: open_type_manager(self, self.type, "task"))
        type_row.addWidget(self.type, 1)
        type_row.addWidget(manage)
        form.addRow("任务类型", type_row)

        root.addWidget(card)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("开始专注")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _apply_preset(self, f, b):
        self.focus.setValue(f)
        self.break_.setValue(b)

    def values(self):
        return {
            "focus": self.focus.value(),
            "break": self.break_.value(),
            "cycles": self.cycles.value(),
            "long_every": self.long_every.value(),
            "long_break": self.long_break.value(),
            "task_type": self.type.currentText().strip(),
        }


class CountdownDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        theme.setup_dialog(self, "倒计时")
        self.setMinimumWidth(400)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("倒计时")
        title.setObjectName("title")
        root.addWidget(title)
        tip = QLabel("设一个时长，到点我叫你；中途可以 +1 分钟、暂停或直接停掉。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

        card, form = theme.card_form()

        self.minutes = theme.ChevronSpinBox()
        self.minutes.setRange(0, 600)
        self.minutes.setValue(10)
        self.minutes.setSuffix(" 分钟")
        form.addRow("分钟", self.minutes)

        self.seconds = theme.ChevronSpinBox()
        self.seconds.setRange(0, 59)
        self.seconds.setValue(0)
        self.seconds.setSuffix(" 秒")
        form.addRow("秒", self.seconds)

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self.type = theme.ChevronComboBox()
        self.type.setEditable(True)
        self.type.setInsertPolicy(QComboBox.NoInsert)
        self.type.lineEdit().setPlaceholderText("不填也行")
        reload_types(self.type, "task")
        manage = QPushButton("管理")
        manage.setObjectName("ghost")
        manage.setToolTip("添加 / 删除自定义任务类型（最多 3 个）")
        manage.clicked.connect(lambda: open_type_manager(self, self.type, "task"))
        type_row.addWidget(self.type, 1)
        type_row.addWidget(manage)
        form.addRow("任务类型", type_row)

        root.addWidget(card)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("开始计时")
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        root.addLayout(btns)

    def total_seconds(self):
        return self.minutes.value() * 60 + self.seconds.value()

    def task_type(self):
        return self.type.currentText().strip()


# ==================== 运行时 ====================
class _TimerBase(QObject):
    """番茄钟 / 倒计时的公共部分：1 秒心跳 + 气泡原地刷新 + 控制按钮。"""

    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.remaining = 0
        self.total = 1
        self.paused = False
        self._shown_secs = None

    # ---- 气泡 ----
    def _buttons(self):
        if self.paused:
            return [
                {"label": "继续", "reply": "@resume"},
                {"label": "+1 分钟", "reply": "@add"},
                {"label": "停止", "reply": "@stop"},
            ]
        return [
            {"label": "暂停", "reply": "@pause"},
            {"label": "+1 分钟", "reply": "@add"},
            {"label": "停止", "reply": "@stop"},
        ]

    def _label(self):
        return ""

    def _say_static(self, text):
        """一次性提示（开始 / 结束），只给按钮，不给 +1 分钟这类刷新用入口。"""
        self._shown_secs = None
        self.pet.say(text, mood=self._mood())

    def _mood(self):
        return "unhappy" if self.paused else ""

    def _refresh(self):
        """原地刷新气泡：只在显示的秒数变化时才重建，避免按钮闪烁。"""
        if not load_settings().get("live_bubble", True):
            return
        if self._shown_secs == self.remaining:
            return
        self._shown_secs = self.remaining
        self.pet.show_live(self._label(), self._buttons(), mood=self._mood())

    def _clear_mood(self):
        self.pet.set_timer_mood("", 0)

    # ---- 控制 ----
    def pause(self):
        if self.paused or not self.timer.isActive():
            return
        self.paused = True
        self.timer.stop()
        # 暂停 = 不高兴的站立 3.png，提示「现在停着」
        self.pet.set_timer_mood("unhappy")
        # 强制刷新一次：按钮要从「暂停」变成「继续」
        self._shown_secs = None
        self._refresh()

    def resume(self):
        if not self.paused:
            return
        self.paused = False
        self.pet.set_timer_mood("", 0)
        self.timer.start()
        # 强制刷新一次：按钮要从「继续」变回「暂停」
        self._shown_secs = None
        self._refresh()

    def add_minute(self, secs=60):
        self.remaining += secs
        self.total = max(self.total, self.remaining)
        self._shown_secs = None
        self._refresh()

    def on_control(self, action):
        """气泡按钮（@pause / @resume / @add / @stop）的统一入口。"""
        if action == "pause":
            self.pause()
        elif action == "resume":
            self.resume()
        elif action == "add":
            self.add_minute(60)
        elif action == "stop":
            self.stop()

    def stop(self, quiet=False):
        self.timer.stop()
        self.paused = False
        self.remaining = 0
        self._shown_secs = None
        self._clear_mood()
        self._on_stop(quiet)

    def _on_stop(self, quiet):
        pass


class Pomodoro(_TimerBase):
    def __init__(self, pet):
        super().__init__(pet)
        self.phase = None            # focus / break / long_break
        self.focus_min = 25
        self.break_min = 5
        self.long_min = 15
        self.long_every = 4
        self.cycles = 4              # 一共要做几个番茄
        self.done = 0                # 已经做完几个
        self.task_type = ""

    def start(self, opts):
        self.focus_min = int(opts.get("focus", 25))
        self.break_min = int(opts.get("break", 5))
        self.long_min = int(opts.get("long_break", 15))
        self.long_every = int(opts.get("long_every", 4))
        self.cycles = max(1, int(opts.get("cycles", 4)))
        self.task_type = (opts.get("task_type") or "").strip()
        self.done = 0
        self.paused = False
        self._shown_secs = None
        self._save_memory(opts)
        self._begin_focus()

    @staticmethod
    def _save_memory(opts):
        s = load_settings()
        s["pomodoro"] = dict(opts)
        save_settings(s)

    # ---- 阶段 ----
    def _begin_focus(self):
        self.phase = "focus"
        self.remaining = self.focus_min * 60
        self.total = self.remaining
        self._shown_secs = None
        self._say_static(dialogue.pick("pomodoro_start"))
        self.timer.start()
        self._refresh()

    def _begin_break(self):
        n = self.done
        if self.long_every > 0 and n > 0 and n % self.long_every == 0 and n < self.cycles:
            self.phase = "long_break"
            self.remaining = self.long_min * 60
        else:
            self.phase = "break"
            self.remaining = self.break_min * 60
        self.total = self.remaining
        self._shown_secs = None
        self._say_static(dialogue.pick("pomodoro_end"))
        self.timer.start()
        self._refresh()

    def _next_after_break(self):
        if self.done >= self.cycles:
            self._finish()
        else:
            self._begin_focus()

    def _finish(self):
        """整组做完：不播 tada（那是单段完成），改播 TADA (2)，并给开心表情。"""
        self.timer.stop()
        self.phase = None
        self.remaining = 0
        self._shown_secs = None
        self.pet.set_timer_mood("happy", seconds=config.DONE_MOOD_SECONDS)
        sound.cycle_done()
        self.pet.say(
            self._summary() + "\n" + (dialogue.pick("pomodoro_break_end")
                                      or "休息结束啦，继续加油哦。"),
            mood="happy")

    def _summary(self):
        unit = self.task_type or "番茄"
        return f"{self.cycles} 个「{unit}」都做完啦，一共 {self.cycles} 轮。"

    def _label(self):
        index = min(self.done + 1, self.cycles) if self.phase == "focus" else self.done
        return _work_line(self.phase or "focus", index, self.done, self.cycles,
                          self.task_type, self.remaining)

    # ---- 心跳 ----
    def _tick(self):
        self.remaining -= 1
        if self.remaining > 0:
            self._refresh()
            return
        self.timer.stop()
        self.remaining = 0
        self._shown_secs = None
        if self.phase == "focus":
            self.done += 1
            self.pet.set_timer_mood("happy", seconds=config.DONE_MOOD_SECONDS)
            sound.task_done()
            self._refresh()
            QTimer.singleShot(1200, self._begin_break)
        else:
            self._refresh()
            QTimer.singleShot(1200, self._next_after_break)

    # ---- 外部 ----
    def _on_stop(self, quiet):
        """停止 = 整个番茄钟清零。"""
        self.phase = None
        self.done = 0
        if not quiet:
            self.pet.say(dialogue.pick("pomodoro_stop") or "好，那就先不做了。")

    def is_running(self):
        return self.phase is not None


class Countdown(_TimerBase):
    def __init__(self, pet):
        super().__init__(pet)
        self.task_type = ""
        self.extra = 0.0     # 累计「+1 分钟」的秒数

    def start(self, seconds, task_type=""):
        self.remaining = max(1, int(seconds))
        self.total = self.remaining
        self.task_type = (task_type or "").strip()
        self.paused = False
        self.extra = 0.0
        self._shown_secs = None
        self.pet.say(dialogue.pick("countdown_start"))
        self.timer.start()
        self._refresh()

    def _label(self):
        extra = f"已延长 {_mmss(self.extra)}" if self.extra else ""
        return _cd_line(self.task_type, self.remaining, self.total, extra)

    def add_minute(self, secs=60):
        # 额外记一笔「已延长」，倒计时气泡里单独显示
        self.extra += secs
        super().add_minute(secs)

    def _tick(self):
        self.remaining -= 1
        if self.remaining > 0:
            self._refresh()
            return
        self.timer.stop()
        self.remaining = 0
        self._shown_secs = None
        sound.task_done()
        self.pet.timer_done_overlay()
        name = f"「{self.task_type}」" if self.task_type else ""
        self.pet.say(f"{name}时间到啦！\n" + (dialogue.pick("countdown_end") or "到点了哦。"),
                    mood="happy")

    def _on_stop(self, quiet):
        if not quiet:
            self.pet.say(dialogue.pick("countdown_stop") or "好，停了。")

    def is_running(self):
        return self.timer.isActive() or self.paused
