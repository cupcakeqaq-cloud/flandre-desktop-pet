"""统一 UI 主题（褐色系）。

设计令牌集中在文件顶部，QSS 从令牌拼出来——以后调色只改这里。
像素字体在 main.py 里加载（PIXEL_FONT_FAMILY），这里只负责字号与样式。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QFrame

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
}


def setup_dialog(dlg, title=None):
    """统一的对话框初始化：标题、样式表、按字号给最小宽度。"""
    if title:
        dlg.setWindowTitle(title)
    dlg.setStyleSheet(QSS)
    dlg.setMinimumWidth(340)
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
QComboBox::down-arrow {{
    width: 8px;
    height: 8px;
    /* 用主色画一个小三角，避免依赖系统图片资源 */
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {PRIMARY};
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
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateEdit::up-arrow {{
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid {PRIMARY_PRESS};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateEdit::down-arrow {{
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid {PRIMARY_PRESS};
}}

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
