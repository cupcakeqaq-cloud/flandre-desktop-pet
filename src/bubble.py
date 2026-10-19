# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""对话气泡。

2026-10-08 第五批：
- 支持 ``set_live()`` 在**不重新弹出**的情况下原地刷新正文与按钮（番茄钟 / 倒计时用）。
- 按钮排版：2 个及以下横排、3 个以上竖排；控制类按钮（@pause/@stop/@add）用次级描边样式，
  对话选项用主色实心样式，一眼能分清「在操作计时器」还是「在选一句话」。
"""

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QFrame)

from config import UI_COLOR

BG = "#f7f1e8"
BORDER = UI_COLOR
TEXT = "#4a3b2e"

# 以 @ 开头的 reply 是计时器控制指令，不是对话选项
CONTROL_PREFIX = "@"

# ---------- 气泡尺寸 ----------
# 2026-10-08 第十批：以前这里用 self.adjustSize()，而开了 wordWrap 的 QLabel
# sizeHint() 是**不可靠**的（实测同一句话能算出 43/65/87 三种高度、宽度还会
# 被上一次内容污染），于是「字数差不多的句子宽度不一样」。
# 2026-10-15 第十八批：用户又提「长文本把气泡撑太长，能不能把框固定住」——
# 于是宽度干脆全固定成 BUBBLE_W，长句自己在里面换行。
#   宽度 = BUBBLE_W（常量，所有气泡一样宽）
#   高度 = label.heightForWidth(定宽)  ← wordWrap 下这个方法才是可靠的
BUBBLE_W = 260         # 气泡固定宽度（改这个数就能整体调宽窄），上限也是它
OUTER_W = 24           # outer 左右内容边距 14 + 10


class SpeechBubble(QWidget):
    closed = Signal()
    option_chosen = Signal(str, str)   # (reply, mood)：mood 为空串表示该选项不带表情
    moved = Signal(int, int)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 10, 12)
        outer.setSpacing(6)

        # 顶行：角色名靠左下角，关闭键钉在气泡右上角
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title = QLabel("芙兰朵露·斯卡蕾特")
        self.title.setStyleSheet(
            f"color: {BORDER}; font-size: 10pt; font-weight: bold; letter-spacing: 1px;")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top.addWidget(self.title, 1, Qt.AlignBottom)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("收起这句话")
        self.close_btn.setStyleSheet(
            f"QPushButton{{background:transparent; color:{BORDER}; border:none;"
            f" font-size:15pt; font-weight:bold;}}"
            f"QPushButton:hover{{color:#6b5243;}}"
        )
        self.close_btn.clicked.connect(self._on_close)
        top.addWidget(self.close_btn, 0, Qt.AlignTop)

        outer.addLayout(top)

        # 正文独占一行：以前关闭键挤在正文右侧，短句时会被顶到文字边上
        self.label = QLabel("")
        self.label.setWordWrap(True)
        self.label.setStyleSheet(f"color: {TEXT}; font-size: 11pt;")
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        outer.addWidget(self.label)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: rgba(131,105,83,0.16); border: none;")
        sep.setVisible(False)
        self.sep = sep
        outer.addWidget(sep)

        self.opts_layout = QVBoxLayout()
        self.opts_layout.setSpacing(6)
        self.opts_layout.setContentsMargins(0, 2, 0, 0)
        outer.addLayout(self.opts_layout)
        self._opt_buttons = []
        self._buttons_key = ()
        self._press_global = None
        self._moved = False
        self._dragging = False

    @property
    def is_dragging(self):
        return self._dragging

    # ---------- 按钮 ----------
    @staticmethod
    def _is_control(reply):
        return str(reply or "").startswith(CONTROL_PREFIX)

    def _make_button(self, opt):
        reply = str(opt.get("reply", "") or "")
        b = QPushButton(str(opt.get("label", "")) or "　")
        b.setCursor(Qt.PointingHandCursor)
        control = self._is_control(reply)
        b.setProperty("control", control)
        if control:
            b.setStyleSheet(
                "QPushButton{background:#fffdf9; color:#836953; border:1px solid #c9b8a6;"
                " border-radius:8px; padding:6px 12px; font-size:11pt;}"
                "QPushButton:hover{background:#f3ece1; border-color:#836953; color:#6b5243;}"
                "QPushButton:pressed{background:#efe5d8;}"
            )
        else:
            b.setStyleSheet(
                "QPushButton{background:#836953; color:white; border:none; border-radius:8px;"
                " padding:8px 14px; text-align:left; font-size:11pt;}"
                "QPushButton:hover{background:#6b5243;}"
                "QPushButton:pressed{background:#5a4636;}"
            )
        b.clicked.connect(
            lambda _=False, r=reply, m=opt.get("mood", ""): self._on_option(r, m))
        if opt.get("tip"):
            b.setToolTip(str(opt["tip"]))
        return b

    def _clear_options(self):
        for b in self._opt_buttons:
            b.setParent(None)
            b.deleteLater()
        self._opt_buttons = []
        while self.opts_layout.count():
            item = self.opts_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._buttons_key = ()
        self.sep.setVisible(False)

    @staticmethod
    def _options_key(options):
        # 连 reply 一起比：暂停↔继续 标签变了、reply 也变了，必须重建
        return tuple((str(o.get("label", "")), str(o.get("reply", ""))) for o in options)

    def _build_options(self, options):
        self._clear_options()
        options = [o for o in (options or []) if o and o.get("label")]
        if not options:
            return
        self._buttons_key = self._options_key(options)
        self.sep.setVisible(True)
        # 短标签（暂停 / 停止 / +1 分钟 这类）才横排：长台词横排会被挤成折行
        short = all(len(str(o.get("label", ""))) <= 6 for o in options)
        if len(options) <= 2 and short:
            # 横排：暂停 / 停止 这类短指令最顺手
            row = QHBoxLayout()
            row.setSpacing(8)
            for opt in options:
                b = self._make_button(opt)
                row.addWidget(b)
                self._opt_buttons.append(b)
            self.opts_layout.addLayout(row)
        else:
            # 竖排：选项文字较长时保持左对齐，宽度自适应
            for opt in options:
                b = self._make_button(opt)
                b.setMinimumHeight(32)
                self.opts_layout.addWidget(b)
                self._opt_buttons.append(b)
        # 进布局后必须显式置为「显示」：QPushButton 新建时是隐藏态，气泡已经可见时
        # 插进布局不会被自动显示，而布局对隐藏项按空项算（0 高）→ 整个气泡高度少算
        # 一截，按钮最后被挤成没字的实心小条。父窗口不可见时这里只是记下状态，
        # 等气泡 show() 时一起出现，不会提前冒到桌面上。
        for b in self._opt_buttons:
            b.setVisible(True)

    # ---------- 展示 ----------
    # 注意：这两个方法**不要**发 `moved` 信号。气泡变宽变高会让屏幕边缘的夹取
    # （pet_window._position_bubble）把左上角推走；一旦把「夹取后的位置」当成
    # 用户拖拽存进 bubble_offset，下次内容再变就又夹一次——表现为「对话框每变
    # 一次就往左跑一点」。`moved` 只归鼠标拖拽用。
    def _fit_size(self):
        """算定尺寸：宽度一律 BUBBLE_W，高度按这个定宽排版实测。

        高度 = heightForWidth(定宽) + 布局里「除正文以外」的部分，后者用把正文
        高度临时设成 0 再问一次 layout().sizeHint() 拿到——这样按钮/分割线怎么
        变都自动算进去，不用手抄一串魔法数字。

        坑（2026-10-15 第十八批第二轮）：**量之前必须先把正文的固定高度清成 0**。
        `QLabelPrivate::sizeForWidth()` 开头就是 `int h = q->height()`，结尾还有
        `if (h > br.height()) br.setHeight(h)`——**当前高度会当成返回值下限**。所以
        上一条长台词把高度顶到 87 之后，短台词也永远量到 87，气泡只会越长越高，
        再也缩不回去（用户报的「触发长对话后气泡就变大了」）。
        """
        label_w = BUBBLE_W - OUTER_W
        self.label.setFixedWidth(label_w)          # 先定宽，heightForWidth 才有意义
        self.label.setFixedHeight(0)               # 再清掉上次的高度下限
        h = self.label.heightForWidth(label_w)
        if h <= 0:                                  # 兜底：极少数字体量不出高度
            h = self.label.fontMetrics().height()
        lay = self.layout()
        extra = lay.sizeHint().height() if lay is not None else 0
        self.label.setFixedHeight(int(h))
        self.setFixedWidth(BUBBLE_W)
        self.setFixedHeight(int(h) + int(extra))

    def show_message(self, text, options=None):
        """弹出一段话（清空后重建按钮）。"""
        self.label.setText(text or "")
        self._build_options(options)
        self._fit_size()

    def set_live(self, text, options=None):
        """原地刷新：正文变了就改字，按钮结构没变就不重建（避免闪烁）。"""
        if self.label.text() != (text or ""):
            self.label.setText(text or "")
        new_options = [o for o in (options or []) if o and o.get("label")]
        if self._options_key(new_options) != self._buttons_key:
            self._build_options(new_options)
        self._fit_size()

    # ---------- 事件 ----------
    def _on_close(self):
        self.hide()
        self.closed.emit()

    def _on_option(self, reply, mood=""):
        self.option_chosen.emit(reply, mood or "")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._moved = False
            self._dragging = True
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_global is not None:
            gp = e.globalPosition().toPoint()
            self.move(self.x() + (gp.x() - self._press_global.x()),
                      self.y() + (gp.y() - self._press_global.y()))
            self._press_global = gp
            self._moved = True
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_global = None
            self._dragging = False
            if self._moved:
                self.moved.emit(self.x(), self.y())
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        p.fillPath(path, QColor(BG))
        p.setPen(QPen(QColor(BORDER), 2))
        p.drawPath(path)
