# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""设置。

2026-10-08 第五批：
- 卡片式分区：称呼与台词 / 气泡显示 / 类型管理 / 音效。
- 新增「倒计时气泡逐秒刷新」开关（关掉就不每秒重绘，适合低配机器）。
- 新增两个类型管理入口（任务类型 / 事件类型）与音效试听按钮。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QLabel, QFrame, QDoubleSpinBox,
                               QPushButton, QCheckBox, QScrollArea, QWidget,
                               QComboBox)

import theme
from data_manager import load_settings, save_settings, DEFAULT_SETTINGS

# 说话键捕获：Qt 键位 → 存进 settings 的键名（跟 voice.VK_NAMES 对齐）
_QT_TO_NAME = {}
for _n in range(1, 13):
    _QT_TO_NAME[getattr(Qt, "Key_F%d" % _n)] = "F%d" % _n
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    _QT_TO_NAME[getattr(Qt, "Key_" + _c)] = _c
_QT_TO_NAME.update({
    Qt.Key_Space: "SPACE", Qt.Key_Tab: "TAB", Qt.Key_Return: "ENTER",
    Qt.Key_Home: "HOME", Qt.Key_End: "END", Qt.Key_Insert: "INSERT",
    Qt.Key_Delete: "DELETE", Qt.Key_PageUp: "PAGEUP", Qt.Key_PageDown: "PAGEDOWN",
    Qt.Key_Up: "UP", Qt.Key_Down: "DOWN", Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT",
    Qt.Key_QuoteLeft: "`", Qt.Key_Minus: "-", Qt.Key_Equal: "=",
    Qt.Key_BracketLeft: "[", Qt.Key_BracketRight: "]", Qt.Key_Backslash: "\\",
    Qt.Key_Semicolon: ";", Qt.Key_Apostrophe: "'", Qt.Key_Comma: ",",
    Qt.Key_Period: ".", Qt.Key_Slash: "/",
})
_MOD_KEYS = {
    Qt.Key_Control: "Ctrl", Qt.Key_Shift: "Shift", Qt.Key_Alt: "Alt", Qt.Key_Meta: "Win",
}


class _HotkeyButton(QPushButton):
    """点一下就能重新录说话键：按什么锁什么，存成 "Ctrl+Shift+F8" 这种写法。"""

    def __init__(self, hotkey):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点一下，然后按下你想用的键（可以带 Ctrl / Shift / Alt / Win）")
        self._capturing = False
        self._hotkey = str(hotkey or "F8").strip() or "F8"
        self.clicked.connect(self._start)
        self._refresh()

    def hotkey(self):
        return self._hotkey

    def _refresh(self):
        self.setText(self._hotkey)

    def _start(self):
        self._capturing = True
        self.setText("按下你要用的键……（Esc 取消）")
        self.setFocus(Qt.OtherFocusReason)

    def focusOutEvent(self, event):           # noqa: N802 (Qt 命名)
        if self._capturing:
            self._capturing = False
            self._refresh()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):           # noqa: N802 (Qt 命名)
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Escape:
            self._capturing = False
            self._refresh()
            return
        mods = []
        m = event.modifiers()
        if m & Qt.ControlModifier:
            mods.append("Ctrl")
        if m & Qt.ShiftModifier:
            mods.append("Shift")
        if m & Qt.AltModifier:
            mods.append("Alt")
        if m & Qt.MetaModifier:
            mods.append("Win")
        mod_name = _MOD_KEYS.get(key)
        if mod_name is not None:
            # 只按了修饰键（比如就想用 Ctrl+Shift 推着说话）：先记着，还能再补一个主键
            if mod_name not in mods:
                mods.append(mod_name)
            self._hotkey = "+".join(mods)
            self._capturing = True
            self.setText("+".join(mods) + "（可以再补一个键，或直接保存）")
            return
        name = _QT_TO_NAME.get(key)
        if not name:
            return                            # 不认识的键：让她再按一次，别把好键吞了
        self._hotkey = "+".join(mods + [name])
        self._capturing = False
        self._refresh()



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

        # 卡片越来越多，小屏幕上会顶出屏幕外，所以卡片都塞进滚动区，
        # 标题和底部按钮固定在原处（滚的时候不会跟着跑）。
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setAutoFillBackground(False)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(12)
        scroll.setWidget(body)
        # 滚动区整条链都透明：暗色系统主题下视口会拿系统黑底刷一遍，卡片周围就是一圈黑边
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget"
            " { background: transparent; border: none; }")
        root.addWidget(scroll, 1)

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
        body_lay.addWidget(card1)

        # ---- 气泡显示 ----
        card2, form2 = _card(
            "气泡显示",
            "气泡时长决定一句话停留多久；计时器运行时不会自动收起，暂停/停止按钮一直可用。")
        self.bubble_dur = theme.ChevronDoubleSpinBox()
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
        body_lay.addWidget(card2)

        # ---- 对话模型（在线模式）----
        card4, form4 = _card(
            "对话模型",
            "开了这个，右键菜单里才会多一项「聊天」。地址填到域名就行，后面自动补。")
        llm = s.get("llm") or {}
        self.llm_on = QCheckBox("启用在线模式")
        self.llm_on.setChecked(bool(llm.get("enabled", False)))
        self.llm_on.setToolTip("关掉就回到离线：台词全用本地写好的那些")
        form4.addRow("", self.llm_on)

        self.llm_url = QLineEdit(str(llm.get("base_url") or ""))
        self.llm_url.setPlaceholderText("https://api.deepseek.com")
        form4.addRow("接口地址", self.llm_url)

        self.llm_key = QLineEdit(str(llm.get("api_key") or ""))
        self.llm_key.setEchoMode(QLineEdit.Password)
        self.llm_key.setPlaceholderText("sk-……")
        form4.addRow("API key", self.llm_key)

        self.llm_model = QLineEdit(str(llm.get("model") or ""))
        self.llm_model.setPlaceholderText("deepseek-chat")
        form4.addRow("模型名", self.llm_model)

        self.llm_temp = theme.ChevronDoubleSpinBox()
        # 上限压到 1.5：2.0 那档 deepseek-chat 会整段胡言乱语（用户 2026-10-24 截图为证）
        self.llm_temp.setRange(0.0, 1.5)
        self.llm_temp.setSingleStep(0.1)
        self.llm_temp.setDecimals(1)
        self.llm_temp.setValue(min(1.5, float(llm.get("temperature", 0.9))))
        self.llm_temp.setToolTip("越高越放飞，越低越正经；1.5 以上容易胡言乱语，别调太高")
        form4.addRow("温度", self.llm_temp)

        row_probe = QHBoxLayout()
        row_probe.setSpacing(8)
        probe_btn = QPushButton("测试连接")
        probe_btn.clicked.connect(self._probe)
        self.probe_hint = QLabel("还没试过")
        self.probe_hint.setObjectName("muted")
        self.probe_hint.setWordWrap(True)
        row_probe.addWidget(probe_btn)
        row_probe.addWidget(self.probe_hint, 1)
        form4.addRow("", row_probe)
        body_lay.addWidget(card4)

        # 地址 / key / 模型都填齐了就把开关自动打开：用户以为「填好就能用」，
        # 让他再跑去上面找一个开关勾上太坑。真想离线，手动取消勾选就行。
        for field in (self.llm_url, self.llm_key, self.llm_model):
            field.textChanged.connect(self._llm_autotick)

        # ---- 什么时候让芙兰看着你 ----
        card5, form5 = _card(
            "芙兰看见你在干什么",
            "全屏玩游戏、看片的时候让她躲一下，退出全屏自己就回来了。")
        watch = s.get("watch") or {}
        self.watch_on = QCheckBox("可以主动来搭话")
        self.watch_on.setChecked(bool(watch.get("enabled", False)))
        self.watch_on.setToolTip("开了之后她会看着你在干什么，偶尔凑一句；关了全程不开口")
        self.watch_on.toggled.connect(self._watch_toggle)
        form5.addRow("", self.watch_on)

        self.watch_cool = theme.ChevronSpinBox()
        self.watch_cool.setRange(30, 86400)
        self.watch_cool.setSingleStep(30)
        self.watch_cool.setSuffix(" 秒")
        self.watch_cool.setValue(int(watch.get("cooldown_s", 600)))
        form5.addRow("同类冷却", self.watch_cool)

        self.watch_cap = theme.ChevronSpinBox()
        self.watch_cap.setRange(1, 10000)
        self.watch_cap.setValue(int(watch.get("daily_cap", 100)))
        form5.addRow("每日上限", self.watch_cap)

        self.watch_hide_full = QCheckBox("全屏时自动躲起来")
        self.watch_hide_full.setChecked(bool(watch.get("hide_in_fullscreen", True)))
        self.watch_hide_full.setToolTip("玩游戏、看视频时她不会杵在屏幕上挡着")
        form5.addRow("", self.watch_hide_full)

        privacy = QLabel("只读窗口标题和程序名，不截图、不上传画面。")
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        form5.addRow("", privacy)
        body_lay.addWidget(card5)

        # ---- 语音（按住热键说话）----
        card6, form6 = _card(
            "语音",
            "按住说话键说一句，松开就转成字显示在气泡里，她再回你一句。"
            "认字全在本机做，不联网、不花钱。")
        voice = s.get("voice") or {}
        self.voice_on = QCheckBox("按住说话键说话")
        self.voice_on.setChecked(bool(voice.get("enabled", False)))
        self.voice_on.setToolTip("关掉就完全不碰麦克风")
        form6.addRow("", self.voice_on)

        # 说话键：点一下「自定义」让用户自己按，按什么锁什么（支持 Ctrl / Shift / Alt / Win 组合）
        self.voice_hotkey = _HotkeyButton(str(voice.get("hotkey") or "F8").strip())
        self.voice_hotkey.setToolTip(
            "带上一个主键（比如 Ctrl+Shift+F8、F8）的，程序会向系统把这个键占住，"
            "别的软件和游戏抢不走；只有修饰键的组合（Ctrl+Shift）占不住，"
            "容易被输入法或游戏的快捷键先吃掉")
        form6.addRow("说话键", self.voice_hotkey)
        body_lay.addWidget(card6)

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
        body_lay.addWidget(card3)

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

        # 卡片再多也只长到屏幕边上，剩下的交给滚动
        ah = self.screen().availableGeometry().height() if self.screen() else 0
        limit = max(360, ah - 80) if ah else 720
        self.setMaximumHeight(limit)
        chrome = self.height() - scroll.height()      # 标题 + 按钮 + 边距占掉的高度
        need = body.sizeHint().height() + chrome
        self.resize(470, min(max(need, 360), limit))

        net = getattr(pet, "net", None) if pet is not None else None
        if net is not None:
            net.done.connect(self._on_probe_done)

    def _probe(self):
        """拿对话框里**现在填的**参数探一次，不用先保存。"""
        net = getattr(self.pet, "net", None) if self.pet is not None else None
        if net is None:
            self.probe_hint.setText("这里试不了，先保存再来")
            return
        if net.busy:
            self.probe_hint.setText("先等上一条说完")
            return
        self.probe_hint.setText("正在连……")
        net.probe({"base_url": self.llm_url.text().strip(),
                   "api_key": self.llm_key.text().strip(),
                   "model": self.llm_model.text().strip() or "deepseek-chat",
                   "temperature": float(self.llm_temp.value()),
                   "timeout": 20})

    def _on_probe_done(self, kind, text, err):
        if kind != "probe":
            return
        if not err:
            self.llm_on.setChecked(True)     # 连得上就顺手打开，省得再去找开关
        self.probe_hint.setText({
            "": "连上了，可以聊",
            "auth": "key 不对，或者没权限",
            "rate": "被限流了，等会儿再试",
            "timeout": "等太久了，没连上",
            "net": "网好像不通",
            "bad": "地址或模型名不对劲",
        }.get(err, "哪里不太对"))

    def _llm_autotick(self, *_):
        fields = (self.llm_url, self.llm_key, self.llm_model)
        if all(f.text().strip() for f in fields):
            self.llm_on.setChecked(True)

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
        d_llm = d.get("llm") or {}
        self.llm_on.setChecked(bool(d_llm.get("enabled", False)))
        self.llm_url.setText(str(d_llm.get("base_url") or ""))
        self.llm_key.setText(str(d_llm.get("api_key") or ""))
        self.llm_model.setText(str(d_llm.get("model") or ""))
        self.llm_temp.setValue(float(d_llm.get("temperature", 0.9)))
        d_watch = d.get("watch") or {}
        self.watch_on.setChecked(bool(d_watch.get("enabled", False)))
        self.watch_cool.setValue(int(d_watch.get("cooldown_s", 600)))
        self.watch_cap.setValue(int(d_watch.get("daily_cap", 100)))
        self.watch_hide_full.setChecked(
            bool(d_watch.get("hide_in_fullscreen", True)))
        d_voice = d.get("voice") or {}
        self.voice_on.setChecked(bool(d_voice.get("enabled", False)))
        self.voice_hotkey._hotkey = str(d_voice.get("hotkey") or "F8").strip() or "F8"
        self.voice_hotkey._refresh()

    def _watch_toggle(self, on):
        """「看见你在干什么」总开关一动就生效，不用按保存、更不用重启。"""
        act = getattr(self.pet, "activity", None) if self.pet is not None else None
        if act is None:
            return
        if on:
            act.start()
        else:
            act.stop()

    def reject(self):
        super().reject()
        # 勾了又取消：别把「已经在看了」留在内存里
        if self.pet is not None:
            self.pet.refresh_settings()

    def _save(self):
        s = load_settings()
        s["nickname"] = self.nickname.text().strip() or "你"
        s["bubble_duration"] = float(self.bubble_dur.value())
        s["live_bubble"] = self.live_bubble.isChecked()
        s["ui_font"] = "system" if self.ui_font.isChecked() else "source"
        llm = dict(s.get("llm") or {})
        llm.update({
            "enabled": self.llm_on.isChecked(),
            "base_url": self.llm_url.text().strip(),
            "api_key": self.llm_key.text().strip(),
            "model": self.llm_model.text().strip(),
            "temperature": round(float(self.llm_temp.value()), 2),
        })
        s["llm"] = llm
        watch = dict(s.get("watch") or {})
        watch.update({
            "enabled": self.watch_on.isChecked(),
            "cooldown_s": int(self.watch_cool.value()),
            "daily_cap": int(self.watch_cap.value()),
            "hide_in_fullscreen": self.watch_hide_full.isChecked(),
        })
        s["watch"] = watch
        v = dict(s.get("voice") or {})
        v.update({
            "enabled": self.voice_on.isChecked(),
            "hotkey": self.voice_hotkey.hotkey(),
        })
        s["voice"] = v
        save_settings(s)
        if self.pet is not None:
            self.pet.refresh_settings()
            self.pet.say("记住啦。")
        self.accept()
