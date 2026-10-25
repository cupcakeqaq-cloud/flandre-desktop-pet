# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""统一 UI 主题（褐色系）。

设计令牌集中在文件顶部，QSS 从令牌拼出来——以后调色只改这里。
像素字体在 main.py 里加载（PIXEL_FONT_FAMILY），这里只负责字号与样式。
"""

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout,
                               QFrame, QMenu, QSpinBox, QStyle, QStyleOptionComboBox,
                               QStyleOptionSpinBox)

# ---------- 颜色令牌（全部围绕主色 #836953 展开，不引入第二个色相）----------
PRIMARY = "#836953"        # 主色（褐）
PRIMARY_HOVER = "#6b5243"  # 悬停
PRIMARY_PRESS = "#5a4636"  # 按下
PRIMARY_SOFT = "#c9b8a6"   # 主色的浅色变体（禁用态 / 次级描边）

BG = "#f7f1e8"             # 窗口底色（米）
CARD = "#fffdf9"           # 卡片底（近白）
CARD_ALT = "#efe5d8"       # 次级面（条纹 / 分组底）
LINE = "#e2d5c3"           # 分隔线
WHITE = "#ffffff"

TEXT = "#4a3b2e"           # 正文
TEXT_MUTED = "#8d7b68"     # 次要说明
TEXT_DISABLED = "#b9a793"  # 禁用

DANGER = "#a4503c"         # 危险操作（删除 / 停止）
DANGER_HOVER = "#8c4331"

# ---------- 字号令牌（pt；像素字体在 125% 缩放下按此换算物理像素）----------
FONT_SIZE = {
    "dialog": 11,   # 对话框默认正文
    "label": 11,
    "input": 11,
    "button": 11,
    "title": 13,    # 窗口/卡片标题
    "hint": 10,     # 说明文字
    "menu": 11,
    "bubble": 14,   # 气泡正文
    "chat": 10,     # 聊天记录区（比正文小一档，长对话看着不压人）
}


def app_icon():
    """整个程序的窗口图标：标题栏、任务栏、对话框都用它。"""
    import config
    return QIcon(str(config.ICON_PATH))


def setup_dialog(dlg, title=None):
    """统一的对话框初始化：标题、样式表、按字号给最小宽度。

    顺带置顶：桌宠本体是 `WindowStaysOnTopHint`，功能窗不置顶就会被它压住；
    反过来气泡又在 `pet_window.say()` 里每次 `raise_()`，所以那边还会把开着的
    功能窗重新抬起来（用户报的「人物在窗口下面、气泡却在上面」）。
    """
    if title:
        dlg.setWindowTitle(title)
    dlg.setStyleSheet(QSS)
    dlg.setMinimumWidth(340)
    dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return dlg


def hline():
    """细分割线（列表 / 分组之间用）。"""
    f = QFrame()
    f.setObjectName("hline")
    f.setFixedHeight(1)
    f.setFrameShape(QFrame.NoFrame)
    return f


def card_form():
    """卡片容器 + 卡片内表单：卡片样式统一、标签右对齐、输入框拉伸。"""
    card = QFrame()
    card.setObjectName("card")
    form = QFormLayout(card)
    form.setContentsMargins(16, 14, 16, 14)
    form.setSpacing(10)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return card, form


QSS: str = f"""
/* ================= 基础容器 ================= */
QDialog {{
    background: {BG};
}}
QLabel {{
    color: {TEXT};
    font-size: {FONT_SIZE['label']}pt;
    background: transparent;
}}
QLabel#title {{
    color: {PRIMARY_PRESS};
    font-size: {FONT_SIZE['title']}pt;
    font-weight: bold;
}}
QLabel#hint, QLabel#muted {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE['hint']}pt;
}}
QLabel#pill {{
    color: {WHITE};
    background: {PRIMARY};
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {FONT_SIZE['hint']}pt;
}}
QFrame#card {{
    background: {CARD};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
QFrame#hline {{
    background: {LINE};
    max-height: 1px;
    border: none;
}}
QToolTip {{
    background: {TEXT};
    color: {BG};
    border: 1px solid {PRIMARY_PRESS};
    padding: 4px 8px;
    border-radius: 6px;
}}

/* ================= 按钮 ================= */
QPushButton {{
    background: {PRIMARY};
    color: {WHITE};
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-size: {FONT_SIZE['button']}pt;
    min-height: 18px;
}}
QPushButton:hover {{ background: {PRIMARY_HOVER}; }}
QPushButton:pressed {{ background: {PRIMARY_PRESS}; }}
QPushButton:disabled {{
    background: {PRIMARY_SOFT};
    color: {BG};
}}
/* 次要按钮：描边式，用于「取消 / 关闭 / 重命名」 */
QPushButton#ghost {{
    background: transparent;
    color: {PRIMARY};
    border: 1px solid {PRIMARY};
}}
QPushButton#ghost:hover {{
    background: {PRIMARY};
    color: {WHITE};
}}
QPushButton#ghost:pressed {{
    background: {PRIMARY_PRESS};
    border-color: {PRIMARY_PRESS};
    color: {WHITE};
}}
/* 危险按钮：删除 / 停止 */
QPushButton#danger {{
    background: {DANGER};
    color: {WHITE};
}}
QPushButton#danger:hover {{ background: {DANGER_HOVER}; }}
/* 小号按钮：列表行内的「删除」（对象名或 tiny 属性都认） */
QPushButton#tiny, QPushButton[tiny="true"] {{
    padding: 3px 10px;
    font-size: {FONT_SIZE['hint']}pt;
    border-radius: 6px;
}}

/* ================= 输入控件 ================= */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {PRIMARY};
    border-radius: 7px;
    padding: 5px 8px;
    font-size: {FONT_SIZE['input']}pt;
    min-height: 18px;
    selection-background-color: {PRIMARY};
    selection-color: {WHITE};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 2px solid {PRIMARY_PRESS};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
    background: {CARD_ALT};
    color: {TEXT_DISABLED};
    border-color: {PRIMARY_SOFT};
}}
QLineEdit::placeholder {{ color: {TEXT_DISABLED}; }}
QComboBox::drop-down {{
    border: none;
    width: 20px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}
/* 日期控件也要接管 drop-down，否则系统会自己画一个又大又黑的实心三角，
   跟旁边手绘的细箭头不是一套语言 */
QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    border: none;
    width: 20px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}}
QComboBox QAbstractItemView {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {PRIMARY};
    border-radius: 6px;
    padding: 2px;
    outline: none;
    selection-background-color: {PRIMARY};
    selection-color: {WHITE};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: none;
    border-top-right-radius: 7px;
    background: {CARD_ALT};
}}
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: none;
    border-bottom-right-radius: 7px;
    background: {CARD_ALT};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QDateEdit::up-button:hover, QDateEdit::down-button:hover {{
    background: {PRIMARY_SOFT};
}}
/* 箭头一律交给系统样式画：QSS 里写 `image: none` + border 三角的做法在 Qt 上
   只会画出小方块（上下两条横杠），看起来像坏掉的按钮。不写 ::up-arrow /
   ::down-arrow / ::down-arrow 规则时，QStyleSheetStyle 会退回基础样式画原生箭头。 */

/* ================= 复选框 ================= */
QCheckBox {{
    color: {TEXT};
    font-size: {FONT_SIZE['label']}pt;
    spacing: 7px;
    padding: 2px 0;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 2px solid {PRIMARY};
    background: {WHITE};
    border-radius: 4px;
}}
QCheckBox::indicator:hover {{
    background: {CARD_ALT};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    image: none;
}}
QCheckBox::indicator:disabled {{
    border-color: {PRIMARY_SOFT};
    background: {CARD_ALT};
}}

/* ================= 列表 / 滚动区 ================= */
QListWidget, QListView {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 4px;
    outline: none;
    font-size: {FONT_SIZE['input']}pt;
}}
QListWidget::item, QListView::item {{
    padding: 7px 8px;
    border-radius: 7px;
    border: none;
    margin: 1px 2px;
}}
QListWidget::item:hover, QListView::item:hover {{
    background: {CARD_ALT};
}}
QListWidget::item:selected, QListView::item:selected {{
    background: {PRIMARY};
    color: {WHITE};
}}
QListWidget::indicator {{
    width: 15px;
    height: 15px;
    border: 2px solid {PRIMARY};
    border-radius: 4px;
    background: {WHITE};
}}
QListWidget::indicator:hover {{ background: {CARD_ALT}; }}
QListWidget::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QAbstractScrollArea::corner {{
    background: {BG};
    border: none;
}}

/* ================= 滚动条 ================= */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 2px 2px 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {PRIMARY_SOFT};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {PRIMARY}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0 2px 2px 2px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {PRIMARY_SOFT};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {PRIMARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= 菜单 ================= */
QMenu {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {PRIMARY};
    border-radius: 10px;
    padding: 6px;
    font-size: {FONT_SIZE['menu']}pt;
}}
QMenu::item {{
    padding: 7px 26px 7px 14px;
    border-radius: 7px;
    margin: 1px 2px;
}}
QMenu::item:selected {{
    background: {PRIMARY};
    color: {WHITE};
}}
QMenu::item:disabled {{
    color: {TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: {LINE};
    margin: 5px 8px;
}}
/* ================= 消息框 ================= */
QMessageBox {{
    background: {BG};
}}
QMessageBox QLabel {{
    color: {TEXT};
    font-size: {FONT_SIZE['label']}pt;
    min-width: 220px;
}}

/* ================= 日历（保持棕色系）================= */
QCalendarWidget {{
    background-color: {BG};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {PRIMARY};
}}
QCalendarWidget QToolButton {{
    color: {WHITE};
    background-color: {PRIMARY};
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    margin: 2px;
    font-weight: bold;
}}
QCalendarWidget QToolButton:hover {{ background-color: {PRIMARY_HOVER}; }}
QCalendarWidget QToolButton:pressed {{ background-color: {PRIMARY_PRESS}; }}
QCalendarWidget QSpinBox {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {PRIMARY};
    border-radius: 4px;
}}
QCalendarWidget QAbstractItemView {{
    background-color: {WHITE};
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: {WHITE};
    outline: none;
    border: none;
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {TEXT_DISABLED};
}}
QCalendarWidget QMenu {{
    background-color: {WHITE};
    color: {TEXT};
}}
QCalendarWidget QWidget {{
    alternate-background-color: {BG};
}}
"""

# ================= 弹出菜单（圆角 + 矢量图标）=================
# QMenu 的 QSS 圆角只在窗口背景透明时才生效：不透明的话四角会露出窗口方角
# 底色，也就是「四角发黑」。
# 底板的圆角原来是靠 QSS 的 `border: 16px solid transparent` 撑的，但这有个坑：
# Qt 画 QSS 背景时是把背景刷在**整个 border box** 上的，透明 border 只负责让位，
# 边距那一圈照样被刷成卡片色——真机（125%、windowsvista、真截屏逐像素差分）
# 实测外圈被刷了 13695 个像素，就是用户说的「莫名其妙的阴影框」。
# 所以现在：QSS 只留透明背景 + padding（内缩），**卡片和 1px 细边框一律在
# RoundedMenu.paintEvent 里自己画**，边距那圈真正一个像素都不碰。
MENU_RADIUS = 14
MENU_MARGIN = 16
# 内容整体右移靠 QMenu 自己的左 padding：QMenu::icon 的 padding-left 只会在图标列里
# 挪几个像素、QMenu::item 的 padding-left 只挪文字，都不动图标（实测）。要图标和文字
# 一起右移只能加这个。
MENU_PAD_LEFT = MENU_MARGIN + 6
# 上下内边距：让首尾条目离卡片上下边的距离跟离左右边一样是 6px
# （用户 2026-10-23 提的「菜单上下边太窄了，加宽到和左右边一样的宽度」）。
MENU_PAD_Y = MENU_MARGIN + 6
MENU_BORDER = 1                     # 卡片描边粗细（用户要求「很细小」）
MENU_BORDER_COLOR = PRIMARY_SOFT

MENU_STYLE = f"""
QMenu {{
    background: transparent;
    color: {TEXT};
    border: none;
    padding: {MENU_PAD_Y}px {MENU_MARGIN}px {MENU_PAD_Y}px {MENU_PAD_LEFT}px;
    font-size: {FONT_SIZE['menu']}pt;
}}
QMenu::item {{
    padding: 10px 28px 10px 26px;
    border-radius: 8px;
    margin: 1px 0px;
}}
QMenu::item:selected {{
    background: {PRIMARY};
    color: {WHITE};
}}
QMenu::item:disabled {{
    color: {TEXT_DISABLED};
}}
QMenu::separator {{
    height: 1px;
    background: {LINE};
    margin: 5px 8px;
}}
QMenu::icon {{
    padding-left: 18px;
}}
"""

# 没有圆角窗口那条腿（config.ICON_IN_MENU=false 时的普通 QMenu）用：这种菜单没有
# 自绘底板，背景必须是实心的，否则整张菜单是透明的。
PLAIN_MENU_STYLE = (
    MENU_STYLE.replace("background: transparent;", f"background: {CARD};")
    .replace("border: none;", f"border: 1px solid {PRIMARY}; border-radius: {MENU_RADIUS}px;")
    .replace(f"padding: {MENU_PAD_Y}px {MENU_MARGIN}px {MENU_PAD_Y}px {MENU_PAD_LEFT}px;",
             "padding: 6px;")
)


# 输入框/文本框的右键菜单：没有图标列，条目内边距收窄，条目文字由调用方给（中文）。
TEXT_MENU_STYLE = PLAIN_MENU_STYLE.replace("padding: 10px 28px 10px 26px;",
                                           "padding: 10px 30px;")


def make_text_menu(parent=None):
    """给输入框之类的小控件用的右键菜单（窄一点、跟窗口同一套配色）。"""
    menu = QMenu(parent)
    menu.setStyleSheet(TEXT_MENU_STYLE)
    menu.setMinimumWidth(150)
    return menu


class RoundedMenu(QMenu):
    """右键菜单/托盘菜单共用：真圆角、四周透明边距、不要系统阴影。

    没图标时（config.ICON_IN_MENU=false）走的是普通 QMenu 分支，这里只管圆角。

    一共三个坑，都实测过：

    ① 透明背景 + 无边框是「四角发黑 / 大黑边」的命门：只有 `Qt::Popup` 时原生窗口
       的 exstyle 是 `0x88`（**没有 WS_EX_LAYERED**），合成不到桌面上，边距那一圈
       直接变纯黑；补上 `FramelessWindowHint` 后 exstyle 变 `0x80088`，黑边归零。
       这些属性必须在**原生窗口创建之前**设好，放 showEvent 里在 Windows 上太晚。
    ② QSS 的 `background` 会刷满整个 **border box**，透明 border 只让位不挡刷子——
       所以边距那圈会被刷成卡片色（用户说的「莫名其妙的阴影框」）。现在 `MENU_STYLE`
       只有 transparent + padding，卡片和描边由 `paintEvent` 自绘。
    ③ **窗口外面还有一圈 DWM 阴影**：系统阴影是照着**窗口矩形**画的，而窗口矩形比
       圆角卡片大 `MENU_MARGIN` 一圈，于是看起来像「边框外多了一圈阴影」。
       真机差分（窗口外 30px 范围里数变暗的像素）：不加标志 2611 个 → 加
       `NoDropShadowWindowHint` 后 **0 个**。注意这个标志 Qt **不会**反馈到
       `windowFlags()` 里（查不到不代表没生效）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self._make_translucent()

    def _make_translucent(self):
        win = self.window()
        if win.property("_rounded") == MENU_RADIUS:
            return
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        win.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        win.setProperty("_rounded", MENU_RADIUS)

    def showEvent(self, event):                     # noqa: N802 (Qt 命名)
        super().showEvent(event)
        self._make_translucent()

    def paintEvent(self, event):                    # noqa: N802 (Qt 命名)
        """自己画底板：圆角卡片 + 1px 细边框。四周 MENU_MARGIN 那圈一个像素不碰，
        留给桌面（QSS 背景会被刷满整个 border box，靠它做不到）。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        edge = QRectF(self.rect()).adjusted(
            MENU_MARGIN - 0.5, MENU_MARGIN - 0.5, -MENU_MARGIN + 0.5, -MENU_MARGIN + 0.5)
        card = QPainterPath()
        card.addRoundedRect(edge, MENU_RADIUS, MENU_RADIUS)
        painter.fillPath(card, QColor(CARD))
        pen = QPen(QColor(MENU_BORDER_COLOR))
        pen.setWidthF(float(MENU_BORDER))
        painter.setPen(pen)
        painter.drawPath(card)
        painter.end()
        super().paintEvent(event)                  # 项和分隔线画在底板之上

    def show_padded(self, global_pos):
        """先 popup 让 Qt 算好尺寸，再把窗口挪回去抵消四周的透明边距。"""
        self.popup(global_pos)
        geo = self.geometry()
        self.move(geo.x() - MENU_MARGIN, geo.y() - MENU_MARGIN)


# 图标一律用 QPainter 画（打包版被剪掉了 Qt6Svg，用不了 SVG；字体子集里也没有对勾
# 这类字形）。坐标写在 0~100 的方格上，'c'=圆 'l'=折线 'r'=矩形，粗细统一 8。
_ICONS = {
    "hide":     [("l", [(22, 46), (78, 46)]),
                 ("l", [(30, 58), (70, 58)])],
    "eye":      [("l", [(12, 50), (30, 33), (70, 33), (88, 50), (70, 67),
                        (30, 67), (12, 50)]),
                 ("c", (50, 50), 9)],
    # 番茄：圆果身 + 短柄 + 两片斜叶。2026-10-18 试过「照系统 emoji 描 30 点轮廓」，
    # 用户看过说更丑，要求改回这一版（他说像「计时器」，那就保持这个观感）。
    "tomato":   [("c", (50, 60), 30),
                 ("l", [(50, 30), (50, 14)]),
                 ("l", [(50, 32), (38, 24)]),
                 ("l", [(50, 32), (62, 24)])],
    "timer":    [("c", (50, 47), 20), ("c", (50, 47), 34),
                 ("l", [(50, 47), (50, 29)]),
                 ("l", [(50, 47), (63, 53)]),
                 ("l", [(38, 14), (62, 14)])],
    "day":      [("r", (24, 20), (76, 80)),
                 ("l", [(36, 10), (36, 26)]),
                 ("l", [(64, 10), (64, 26)]),
                 ("l", [(24, 38), (76, 38)]),
                 ("c", (50, 60), 5)],
    "todo":     [("r", (24, 24), (76, 86)),
                 ("r", (36, 14), (64, 30)),
                 ("l", [(34, 52), (66, 52)]),
                 ("l", [(34, 68), (66, 68)])],
    "folder":   [("l", [(16, 72), (16, 28), (38, 28), (46, 38),
                        (84, 38), (84, 72), (16, 72)])],
    "settings": [("c", (50, 50), 15),
                 ("l", [(50, 10), (50, 24)]),
                 ("l", [(50, 76), (50, 90)]),
                 ("l", [(10, 50), (24, 50)]),
                 ("l", [(76, 50), (90, 50)]),
                 ("l", [(22, 22), (32, 32)]),
                 ("l", [(68, 68), (78, 78)]),
                 ("l", [(78, 22), (68, 32)]),
                 ("l", [(32, 68), (22, 78)])],
    "quit":     [("l", [(46, 14), (22, 14), (22, 86), (78, 86), (78, 14), (54, 14)]),
                 ("l", [(50, 44), (50, 72)])],
    # 对话气泡：圆角方框 + 左下小尖角 + 三个点（一笔画完，20px 下也别糊）
    "chat":     [("l", [(22, 20), (78, 20), (88, 30), (88, 58), (78, 68),
                        (50, 68), (30, 86), (36, 68), (22, 68), (14, 58),
                        (14, 30), (22, 20)]),
                 ("c", (38, 44), 5), ("c", (52, 44), 5), ("c", (66, 44), 5)],
}

_ICON_CACHE = {}


def icon(name, color=PRIMARY, size=None):
    """按名字生成一枚线性图标（同一个名字+颜色+尺寸只画一次）。"""
    import config
    if size is None:
        size = config.MENU_ICON_SIZE
    key = (name, color, size)
    hit = _ICON_CACHE.get(key)
    if hit is not None:
        return hit
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 100.0, size / 100.0)
    pen = QPen(QColor(color))
    pen.setWidth(8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for shape in _ICONS.get(name, ()):
        if shape[0] == "c":
            _, center, radius = shape
            painter.drawEllipse(QPointF(*center), radius, radius)
        elif shape[0] == "r":
            _, top_left, bottom_right = shape
            painter.drawRect(QRectF(QPointF(*top_left), QPointF(*bottom_right)))
        elif shape[0] == "l":
            path = QPainterPath(QPointF(*shape[1][0]))
            for point in shape[1][1:]:
                path.lineTo(QPointF(*point))
            painter.drawPath(path)
    painter.end()
    result = QIcon(pix)
    _ICON_CACHE[key] = result
    return result


def make_menu(parent=None, with_icon=None):
    """造一个套好主题的菜单（圆角；带不带图标按 config.ICON_IN_MENU）。"""
    import config                          # 延迟导入，避免和 config 循环引用
    if with_icon is None:
        with_icon = config.ICON_IN_MENU
    if with_icon:
        menu = RoundedMenu(parent)
    else:
        menu = QMenu(parent)
    menu.setStyleSheet(MENU_STYLE if with_icon else PLAIN_MENU_STYLE)
    return menu


def add_item(menu, text, icon_name, callback=None, with_icon=None):
    """往菜单里加一项（自动带矢量图标），返回这个 QAction。"""
    import config
    if with_icon is None:
        with_icon = config.ICON_IN_MENU
    action = menu.addAction(text)
    if with_icon:
        action.setIcon(icon(icon_name, config.MENU_ICON_COLOR))
    if callback is not None:
        action.triggered.connect(lambda *_: callback())
    return action


# ---------- 微调框 / 下拉框的箭头 ----------
# Qt 的 QSS 里**没有**三角形这回事：给 ::up-arrow 写 `image: none` + 三边 border，
# 只会得到两个小方块（看着像坏掉的按钮）。而子控件一旦被 QSS 接管，基础样式就
# 不肯再画原生箭头了（这两个坑都实测过）。所以按钮底色继续交给 QSS，箭头在
# paintEvent 里手绘一条折线，线宽/圆头跟菜单图标同一套语言。
_CHEVRON_HALF_W = 3.2
_CHEVRON_HALF_H = 1.7


def _chevron(widget, center, up):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(PRIMARY if widget.isEnabled() else TEXT_DISABLED), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    cx = center.x() + 0.5
    cy = center.y() + 0.5
    sign = _CHEVRON_HALF_H if up else -_CHEVRON_HALF_H
    painter.drawPolyline([QPointF(cx - _CHEVRON_HALF_W, cy + sign),
                          QPointF(cx, cy - sign),
                          QPointF(cx + _CHEVRON_HALF_W, cy + sign)])
    painter.end()


class ChevronSpinBox(QSpinBox):
    def paintEvent(self, event):                    # noqa: N802 (Qt 命名)
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        style = self.style()
        for sub, up in ((QStyle.SubControl.SC_SpinBoxUp, True),
                        (QStyle.SubControl.SC_SpinBoxDown, False)):
            rect = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option, sub, self)
            _chevron(self, rect.center(), up)


class ChevronDoubleSpinBox(QDoubleSpinBox):
    def paintEvent(self, event):                    # noqa: N802 (Qt 命名)
        super().paintEvent(event)
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        style = self.style()
        for sub, up in ((QStyle.SubControl.SC_SpinBoxUp, True),
                        (QStyle.SubControl.SC_SpinBoxDown, False)):
            rect = style.subControlRect(QStyle.ComplexControl.CC_SpinBox, option, sub, self)
            _chevron(self, rect.center(), up)


class ChevronComboBox(QComboBox):
    def paintEvent(self, event):                    # noqa: N802 (Qt 命名)
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                          QStyle.SubControl.SC_ComboBoxArrow, self)
        _chevron(self, rect.center(), False)


class ChevronDateEdit(QDateEdit):
    def paintEvent(self, event):                    # noqa: N802 (Qt 命名)
        super().paintEvent(event)
        # 开了日历弹窗的 QDateEdit 没有上下按钮，只有右侧一个下拉箭头
        _chevron(self, QPoint(self.width() - 10, self.height() // 2), False)

