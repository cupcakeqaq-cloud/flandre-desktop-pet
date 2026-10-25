# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""和芙兰打字聊天的小窗（只有在线模式才会出现）。

记录区是一列气泡（自己那句靠右、芙兰靠左），回车发送，Esc 关窗。
关窗不会掐断已经发出去的请求——回复来了就当没看见，别让用户关个窗口还提心吊胆。
"""

import math
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLayout,
                               QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

import brain
import theme
from data_manager import load_chat_history, save_chat_history

KEEP_MESSAGES = 200       # 记录最多留这么多条，文件不会越长越大
SEND_CONTEXT = 20         # 带给模型的上文条数

BUBBLE_WIDTH = 0.68       # 气泡最宽占记录区宽度的比例（跟手机聊天软件差不多）
BUBBLE_QSS = """
QLabel#me, QWidget#me {
    background: %s; color: %s; border-radius: 18px;
}
QLabel#her, QWidget#her {
    background: %s; color: %s; border: 1px solid %s; border-radius: 18px;
}
QLabel#note {
    color: %s; padding: 2px 6px; font-size: %dpt;
}
""" % (theme.PRIMARY, theme.WHITE,
       theme.WHITE, theme.TEXT, theme.LINE,
       theme.TEXT_MUTED, theme.FONT_SIZE["hint"])
BUBBLE_PAD_X = 28         # 气泡左右内边距（14 * 2，见 _Bubble 的 setContentsMargins）


class _Bubble(QFrame):
    """一个气泡：QFrame 当底色、QLabel 装字。

    **内边距走布局的 setContentsMargins，不写进 QSS 的 padding**——上一版就是把
    padding 写进 QSS 才裁字的（QLabel 自带的 heightForWidth 不认 QSS padding，
    多行文字算矮一截就被切）。现在高度由里面的 QHBoxLayout 算，不可能再裁。
    圆角 18、留白 14×10 是照着手机聊天软件的样子定的（用户给的参考图）。
    """

    def __init__(self, text, mine=False, parent=None):
        super().__init__(parent)
        self.setObjectName("me" if mine else "her")
        self.label = QLabel(str(text or ""), self)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        font = self.label.font()
        font.setPointSizeF(theme.FONT_SIZE["chat"])
        self.label.setFont(font)
        # 文字颜色得写在 QLabel 自己身上：QSS 的 color 不从 QFrame 往下传。
        # 字号也必须写（主题里 QLabel 是 11pt，会盖掉上面 setFont 的 10pt——
        # 于是量宽度按 10pt 算、画出来是 11pt，整整差 8px，短句就被挤成两行）。
        self.label.setStyleSheet("background: transparent; color: %s; font-size: %dpt;"
                                 % (theme.WHITE if mine else theme.TEXT,
                                    theme.FONT_SIZE["chat"]))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)
        lay.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setStyleSheet(BUBBLE_QSS)

    def fit(self, limit):
        """按字数定宽：短句就窄，最长顶到 limit。

        宽度必须用 horizontalAdvance（排版宽度）算，不能用 boundingRect——
        后者是墨迹框，汉字两侧有空隙，9 个字能量出 121px 而实际排版要 130px。
        差的那 9px 让 QLabel 以为放不下，最后一个字就被挤到第二行（用户 2026-10-24
        截图的「你呀，怎么还问这个。」断成「……问这 / 个。」就是这么来的）。
        还要留出 28px 内边距、芙兰那侧 1px 描边（QSS 边框会扣掉布局可用宽度）、
        再给 Qt 的取整留 2px，否则刚好等宽时仍可能折行。
        """
        metrics = QFontMetricsF(self.label.font())
        text_width = max((metrics.horizontalAdvance(line)
                          for line in self.label.text().split("\n")), default=0.0)
        self.setFixedWidth(min(limit, math.ceil(text_width) + BUBBLE_PAD_X + 4))
        return self.width()


class _Input(QLineEdit):
    """输入框：右键菜单自己画。

    Qt 默认那个是英文的、边距也跟窗口不是一套（用户 2026-10-24 提的「边框太窄、
    没汉化」），所以整张菜单自己拼，配色走 theme.
    """

    def _menu(self):
        """把菜单拼出来（挪出来好让自检能核对条目，不必真的弹出来）。"""
        menu = theme.make_text_menu(self)
        items = (
            ("撤销", self.undo, self.isUndoAvailable()),
            ("重做", self.redo, self.isRedoAvailable()),
            (None, None, None),
            ("剪切", self.cut, self.hasSelectedText()),
            ("复制", self.copy, self.hasSelectedText()),
            ("粘贴", self.paste, True),
            ("删除", lambda: self.insert(""), self.hasSelectedText()),
            (None, None, None),
            ("全选", self.selectAll, bool(self.text())),
        )
        for text, callback, enabled in items:
            if text is None:
                menu.addSeparator()
                continue
            action = menu.addAction(text)
            action.triggered.connect(lambda *_, cb=callback: cb())
            action.setEnabled(bool(enabled))
        return menu

    def contextMenuEvent(self, event):          # noqa: N802 (Qt 命名)
        self._menu().exec(event.globalPos())


class ChatWindow(QDialog):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        self._waiting = False
        theme.setup_dialog(self, "和芙兰说话")
        self.setMinimumSize(430, 410)
        # 开窗别贴着最小尺寸（用户 2026-10-24：一打开是收缩的，气泡也跟着缩成一窄条）
        self.resize(470, 520)      # 别让它按布局的 sizeHint 长宽（加了内边距会多报 25px）

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)   # 四边一样宽，别让底下看着空一块
        root.setSpacing(10)

        title = QLabel("和芙兰说话")
        title.setObjectName("title")
        root.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(10, 10, 10, 10)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: %s; border-radius: 12px; }"
            % theme.CARD_ALT)
        self.body = QWidget()
        self._rows = QVBoxLayout(self.body)
        self._rows.setContentsMargins(12, 12, 12, 12)  # 气泡别贴着记录区边框
        self._rows.setSpacing(10)
        # 记录区要能长高才会出现滚动条：没有这条，QScrollArea 把 body 一直压成视口大小
        self._rows.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self._rows.addStretch(1)
        self.scroll.setWidget(self.body)
        card_lay.addWidget(self.scroll)
        root.addWidget(card, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = _Input()
        self.input.setPlaceholderText("想说点什么……")
        self.input.returnPressed.connect(self._send)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("ghost")      # 次要按钮，别跟「发送」抢眼
        # 坑（2026-10-24 用户报「只显示最新一句」的根因）：QDialog 里 QPushButton
        # 默认 autoDefault，而「清空」是最先加进对话框的按钮 → 它成了默认按钮。
        # 于是在输入框按回车时，returnPressed 发完消息，事件还会继续走到默认按钮上，
        # 同一次回车把记录也清掉了，回复回来时就只剩孤零零一条 assistant。
        self.clear_btn.setAutoDefault(False)
        self.clear_btn.setDefault(False)
        self.clear_btn.setFocusPolicy(Qt.NoFocus)  # 也不让 Tab/空格 误触
        self.clear_btn.clicked.connect(self.clear_history)
        self.send_btn = QPushButton("发送")
        self.send_btn.setAutoDefault(False)
        self.send_btn.setDefault(False)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.clear_btn)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        root.addLayout(row)

        self._bubbles = []
        self._history = load_chat_history()
        self._render()
        # 看门狗：net 拿不到锁会悄悄把请求丢了（不发 done），不设这个窗口就永远卡在「芙兰在想…」
        self._watch = QTimer(self)
        self._watch.setSingleShot(True)
        self._watch.timeout.connect(self._on_timeout)
        if self.pet is not None and getattr(self.pet, "net", None) is not None:
            self.pet.net.done.connect(self._on_done)

    # ---------- 对外 ----------
    def append_assistant(self, text, active=False):
        """芙兰自己开口说的（不是这次问答的）也可以记一笔。"""
        if not text:
            return
        self._push("assistant", text, active)

    def text(self):
        """记录区里所有气泡的文字（自检用来核对内容）。"""
        out = []
        for i in range(self._rows.count()):
            item = self._rows.itemAt(i)
            if item is None:
                continue
            holder = item.widget()
            if holder is None:
                continue
            if isinstance(holder, QLabel):      # 灰字备注是直接挂上去的
                out.append(holder.text())
                continue
            for label in holder.findChildren(QLabel):
                out.append(label.text())
        return "\n".join(out)

    # ---------- 发 / 收 ----------
    def _send(self):
        text = self.input.text().strip()
        if not text or self._waiting:
            return
        self._push("user", text)
        if self.pet is None or getattr(self.pet, "net", None) is None:
            self.input.clear()
            self._note("电波不通")
            return
        # 故意先不清空输入框：等回话再清，这样「我刚发了什么」一直看得见
        self._set_waiting(True)
        context = [{"role": m.get("role") or "user",
                    "content": str(m.get("content") or "")}
                   for m in self._history["messages"][-SEND_CONTEXT:]]
        # 聊天也要带上人设和输出约束，不然模型不知道自己在演芙兰；
        # 开了「看见你在干什么」就顺手把当前程序 / 标题 / 手感带上，别让她瞎猜屏幕内容
        if hasattr(self.pet, "chat_ctx"):
            ctx = self.pet.chat_ctx(context)
        else:
            ctx = {"history": context}
        self.pet.net.chat(brain.build_messages("chat", ctx))

    def _on_done(self, kind, text, err):
        if kind != "chat" or not self._waiting:
            return
        self._watch.stop()
        self._set_waiting(False)
        if err or not text:
            self._note("电波不通")
            return
        self._push("assistant", text)
        if self.pet is not None:
            self.pet.say(text)

    def _on_timeout(self):
        if not self._waiting:
            return
        self._set_waiting(False)
        self._note("等太久了，好像没连上")

    def _set_waiting(self, waiting):
        self._waiting = waiting
        self.input.setEnabled(not waiting)
        self.send_btn.setEnabled(not waiting)
        self.send_btn.setText("芙兰在想…" if waiting else "发送")
        if waiting:
            try:
                timeout = float((getattr(self.pet, "settings", {}) or {})
                                .get("llm", {}).get("timeout") or 20)
            except Exception:
                timeout = 20.0
            self._watch.start(int((timeout + 5) * 1000))
        else:
            self._watch.stop()
            self.input.clear()
            self.input.setFocus()

    # ---------- 记录区 ----------
    def clear_history(self):
        """手动删掉聊天记录（每次启动也会自动清一遍）。"""
        self._history["messages"] = []
        self._set_waiting(False)     # 清空就别等那句话了，免得晚到的回复在空记录里留一条
        self._save()
        self._render()

    def _bubble_limit(self):
        """气泡最宽能到多少：跟着记录区视口走，窗口拉大拉小都要重新算。"""
        view = self.scroll.viewport().width() or self.width() or 430
        return max(200, int(view * BUBBLE_WIDTH))

    def _refit_bubbles(self):
        """窗口尺寸变了就按新宽度重排一遍气泡宽度。

        以前气泡宽度只在画出来那一刻算一次，窗口开着的时候拉大，气泡就卡在
        窄的那一档（用户 2026-10-24 报的「气泡也跟着收缩」就是这个）。
        """
        limit = self._bubble_limit()
        for bubble in getattr(self, "_bubbles", ()):
            bubble.fit(limit)

    def resizeEvent(self, event):        # noqa: N802 (Qt 命名)
        super().resizeEvent(event)
        self._refit_bubbles()

    def _render(self):
        """整块重画：记录区永远等于 self._history。

        以前是一条条 append 上去，出过「只显示最新一句」的怪事（用户 2026-10-24 截图），
        离屏复现不出来。改成从数据重画之后，就算某次插入被吞了，下一条消息也会把它带回来。
        """
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)      # 立刻断开，别等 deleteLater 还占着高度
                widget.deleteLater()
        self._bubbles = []
        for msg in self._history["messages"]:
            text = str(msg.get("content") or "")
            if self.pet is not None and hasattr(self.pet, "_apply_nickname"):
                text = self.pet._apply_nickname(text)   # 台词里是 {nickname}，别把占位符露出来
            self._bubble(text, msg.get("role") == "assistant", bool(msg.get("active")))
        self._rows.addStretch(1)
        QTimer.singleShot(0, self._to_bottom)

    def _bubble(self, text, is_assistant, active=False):
        """一个气泡：主人那句靠右、主色底；芙兰那句靠左、白底描边。

        尺寸和摆位照开源实现 LC044/pyqt_component_library 的 bubble_message.py
        （https://github.com/LC044/pyqt_component_library）：气泡自己定宽，
        摆位交给外层 QHBoxLayout 的「弹簧 + 气泡」。
        """
        bubble = _Bubble(text, mine=not is_assistant)
        self._bubbles.append(bubble)
        bubble.fit(self._bubble_limit())

        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)   # 左右间隔统一交给 _rows 的 12px 内边距
        lay.setSpacing(0)
        if is_assistant:
            lay.addWidget(bubble, 0, Qt.AlignLeft)
            lay.addStretch(1)
        else:
            lay.addStretch(1)
            lay.addWidget(bubble, 0, Qt.AlignRight)
        self._rows.addWidget(holder)

    def note(self, text):
        """往记录区丢一行灰字（桌宠那边请求失败时也用这个）。"""
        self._note(text)

    def _note(self, text):
        label = QLabel("（%s）" % str(text or ""))
        label.setObjectName("note")
        label.setWordWrap(True)
        label.setStyleSheet(BUBBLE_QSS)
        label.setAlignment(Qt.AlignHCenter)
        self._rows.addWidget(label)
        QTimer.singleShot(0, self._to_bottom)

    def _to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _push(self, role, content, active=False):
        msgs = self._history["messages"]
        msgs.append({"role": role, "content": str(content),
                     "ts": time.time(), "active": bool(active)})
        del msgs[:-KEEP_MESSAGES]
        self._render()
        self._save()

    def _save(self):
        save_chat_history(self._history)
