"""设置。

2026-10-08 第五批：
- 卡片式分区：称呼与台词 / 气泡显示 / 类型管理 / 音效。
- 新增「倒计时气泡逐秒刷新」开关（关掉就不每秒重绘，适合低配机器）。
- 新增两个类型管理入口（任务类型 / 事件类型）与音效试听按钮。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QLabel, QFrame, QDoubleSpinBox,
                               QPushButton, QCheckBox)

import theme
from data_manager import load_settings, save_settings, DEFAULT_SETTINGS


def _card(title, hint=""):
    """返回 (卡片 QFrame, 卡片内的 QFormLayout)，标题与提示已放好。"""
    card = QFrame()
    card.setObjectName("card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(16, 12, 16, 14)
    outer.setSpacing(8)
    lab = QLabel(title)
    lab.setObjectName("pill")
    outer.addWidget(lab)
    if hint:
        h = QLabel(hint)
        h.setObjectName("hint")
        h.setWordWrap(True)
        outer.addWidget(h)
    outer.addWidget(theme.hline())
    form = QFormLayout()
    form.setSpacing(10)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    outer.addLayout(form)
    return card, form


class SettingsDialog(QDialog):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        theme.setup_dialog(self, "设置")
        self.setMinimumWidth(430)
        s = load_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("设置")
        title.setObjectName("title")
        root.addWidget(title)

        # ---- 称呼与台词 ----
        card1, form1 = _card("称呼与台词", "改完保存就会生效，芙兰立刻换叫法。")
        self.nickname = QLineEdit(s.get("nickname", "你"))
        self.nickname.setPlaceholderText("你")
        self.nickname.setMaxLength(12)
        form1.addRow("怎么称呼你", self.nickname)
        hint = QLabel("芙兰说话时提到的称呼都会跟着这里变。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form1.addRow("", hint)
        root.addWidget(card1)

        # ---- 气泡显示 ----
        card2, form2 = _card(
            "气泡显示",
            "气泡时长决定一句话停留多久；计时器运行时不会自动收起，暂停/停止按钮一直可用。")
        self.bubble_dur = QDoubleSpinBox()
        self.bubble_dur.setRange(2, 60)
        self.bubble_dur.setValue(float(s.get("bubble_duration", 5.0)))
        self.bubble_dur.setSuffix(" 秒")
        form2.addRow("气泡时长", self.bubble_dur)

        self.live_bubble = QCheckBox("倒计时每秒刷新气泡里的剩余时间")
        self.live_bubble.setChecked(bool(s.get("live_bubble", True)))
        self.live_bubble.setToolTip("关掉后只在开始 / 结束 / 点按钮时更新，省一点性能")
        form2.addRow("", self.live_bubble)

        self.ui_font = QCheckBox("界面文字改用系统字体（重启后生效）")
        self.ui_font.setChecked(s.get("ui_font", "source") == "system")
        self.ui_font.setToolTip("默认用随程序带来的思源黑体；勾选后换成系统自带的微软雅黑")
        form2.addRow("", self.ui_font)
        root.addWidget(card2)

        # ---- 类型管理 ----
        card3, form3 = _card("类型管理", "自定义类型最多各 3 个，可以随时添加或删除。")
        row_task = QHBoxLayout()
        row_task.setSpacing(8)
        task_btn = QPushButton("管理任务类型")
        task_btn.setToolTip("番茄钟 / 倒计时里可选的任务类型")
        task_btn.clicked.connect(lambda: self._manage("task", "管理任务类型"))
        task_hint = QLabel("番茄钟、倒计时用")
        task_hint.setObjectName("muted")
        row_task.addWidget(task_btn)
        row_task.addWidget(task_hint, 1)
        form3.addRow("任务类型", row_task)

        row_evt = QHBoxLayout()
        row_evt.setSpacing(8)
        evt_btn = QPushButton("管理事件类型")
        evt_btn.setToolTip("倒数日里可选的事件类型")
        evt_btn.clicked.connect(lambda: self._manage("countdown", "管理事件类型"))
        evt_hint = QLabel("倒数日用")
        evt_hint.setObjectName("muted")
        row_evt.addWidget(evt_btn)
        row_evt.addWidget(evt_hint, 1)
        form3.addRow("事件类型", row_evt)
        root.addWidget(card3)

        # ---- 底部 ----
        btns = QHBoxLayout()
        btns.setSpacing(8)
        reset = QPushButton("恢复默认")
        reset.setObjectName("ghost")
        reset.setToolTip("把上面这些设置项恢复成默认值（不会删掉类型和待办）")
        reset.clicked.connect(self._reset)
        btns.addWidget(reset)
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save_btn)
        root.addLayout(btns)

    def _manage(self, kind, title):
        from timers import TypeManagerDialog
        dlg = TypeManagerDialog(self, kind, title)
        self._type_dlg = dlg          # 非模态，必须持引用，否则可能被回收
        dlg.show()
        dlg.raise_()

    def _reset(self):
        d = DEFAULT_SETTINGS
        self.nickname.setText(d.get("nickname", "你"))
        self.bubble_dur.setValue(float(d.get("bubble_duration", 5.0)))
        self.live_bubble.setChecked(bool(d.get("live_bubble", True)))
        self.ui_font.setChecked(d.get("ui_font", "source") == "system")

    def _save(self):
        s = load_settings()
        s["nickname"] = self.nickname.text().strip() or "你"
        s["bubble_duration"] = float(self.bubble_dur.value())
        s["live_bubble"] = self.live_bubble.isChecked()
        s["ui_font"] = "system" if self.ui_font.isChecked() else "source"
        save_settings(s)
        self.pet.refresh_settings()
        self.pet.say("记住啦。")
        self.accept()
