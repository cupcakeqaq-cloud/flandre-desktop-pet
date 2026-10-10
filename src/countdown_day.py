"""倒数日。

2026-10-08 第五批：
- 卡片式布局，列表按「还有几天」排序，行首带事件类型徽章。
- 事件类型可自定义保存/删除（最多 3 个，与番茄钟共用同一套机制）。
- 双击可以改名称/类型/日期；添加后会立刻让芙兰报出还剩几天。
"""

import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QLineEdit, QComboBox, QDateEdit, QMessageBox)

import dialogue
import theme
from data_manager import load_countdown, save_countdown
from timers import open_type_manager, reload_types

# 内置事件类型 → dialogue.json 里的 countdown_day_* 文案分类
TYPE_KEYS = {
    "考试": "exam", "约会": "date", "见面": "meet", "面试": "interview",
    "纪念日": "anniversary", "生日": "birthday",
}


def days_until(date_str):
    try:
        y, m, d = map(int, str(date_str).split("-"))
        target = datetime.date(y, m, d)
        return (target - datetime.date.today()).days
    except Exception:
        return None


def countdown_line(typ, name, days):
    # 自定义类型没有专属文案，统一回落到 countdown_day_custom
    key = TYPE_KEYS.get(typ, "custom")
    line = dialogue.pick("countdown_day_" + key, name=name, days=days)
    if not line:
        line = dialogue.pick("countdown_day", name=name, days=days)
    return line


def open_countdown_day(pet):
    items = load_countdown()
    if items:
        best = None
        best_d = None
        for it in items:
            d = days_until(it.get("date", ""))
            if d is not None and d >= 0 and (best_d is None or d < best_d):
                best = it
                best_d = d
        if best is None:
            best = items[0]
            best_d = days_until(best.get("date", ""))
        if best_d is not None:
            pet.say(countdown_line(best.get("type", "自定义"), best.get("name", ""), best_d))
    pet.show_dialog("countdown_day", lambda: CountdownDayDialog(pet))


class CountdownDayDialog(QDialog):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        theme.setup_dialog(self, "倒数日")
        self.setMinimumSize(430, 470)
        self.items = []
        self._edit_row = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("倒数日")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        self.count_pill = QLabel("")
        self.count_pill.setObjectName("pill")
        head.addWidget(self.count_pill)
        root.addLayout(head)

        hint = QLabel("按「还有几天」排好序了；双击可以修改，选中后点删除即可移除。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addWidget(theme.hline())

        self.list = QListWidget()
        self.list.setMinimumHeight(180)
        self.list.itemDoubleClicked.connect(self._on_double_clicked)
        self.list.currentRowChanged.connect(lambda _=0: self._refresh_buttons())
        root.addWidget(self.list, 1)

        self.empty = QLabel("还没有倒数日，先在下面加一个吧。")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty)

        card, form = theme.card_form()

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setInsertPolicy(QComboBox.NoInsert)
        reload_types(self.type_combo, "countdown")
        manage = QPushButton("管理")
        manage.setObjectName("ghost")
        manage.setToolTip("添加 / 删除自定义事件类型（最多 3 个）")
        manage.clicked.connect(lambda: open_type_manager(self, self.type_combo, "countdown"))
        type_row.addWidget(self.type_combo, 1)
        type_row.addWidget(manage)
        form.addRow("事件类型", type_row)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：期末考试 / 和朋友的约定")
        form.addRow("事件名称", self.name_edit)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        # 日历周末字体与工作日一致（棕色）
        cal = self.date_edit.calendarWidget()
        if cal is not None:
            pal = cal.palette()
            pal.setColor(QPalette.Text, QColor("#4a3b2e"))
            cal.setPalette(pal)
        form.addRow("日期", self.date_edit)

        root.addWidget(card)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self._add)
        self.del_btn = QPushButton("删除选中")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self._delete)
        self.cancel_edit_btn = QPushButton("取消修改")
        self.cancel_edit_btn.setObjectName("ghost")
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(self.add_btn)
        btns.addWidget(self.del_btn)
        btns.addWidget(self.cancel_edit_btn)
        btns.addStretch()
        btns.addWidget(close_btn)
        root.addLayout(btns)

        self._reload()

    # ---------- 列表 ----------
    def _reload(self):
        self.items = load_countdown()
        self.items = [it for it in self.items if isinstance(it, dict) and it.get("name")]

        def sort_key(it):
            d = days_until(it.get("date", ""))
            return (d is None, d if d is not None else 0)

        self.items.sort(key=sort_key)
        self.list.blockSignals(True)
        self.list.clear()
        for it in self.items:
            d = days_until(it.get("date", ""))
            typ = it.get("type", "") or "未分类"
            if d is None:
                tail = "日期无效"
            elif d < 0:
                tail = f"已过 {abs(d)} 天"
            elif d == 0:
                tail = "就是今天！"
            else:
                tail = f"还剩 {d} 天"
            item = QListWidgetItem(f"[{typ}]  {it.get('name', '')}\n{it.get('date', '')}  ·  {tail}")
            item.setToolTip("双击修改这一条")
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._refresh_buttons()

    def _refresh_buttons(self):
        total = len(self.items)
        self.count_pill.setText(f"{total} 个事件")
        self.empty.setVisible(total == 0)
        self.list.setVisible(total > 0)
        has_sel = self.list.currentRow() >= 0
        self.del_btn.setEnabled(has_sel)
        self.cancel_edit_btn.setVisible(self._edit_row >= 0)
        self.add_btn.setText("保存修改" if self._edit_row >= 0 else "添加")

    # ---------- 增删改 ----------
    def _add(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.information(self, "提示", "先填个事件名称吧。")
            return
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        typ = self.type_combo.currentText().strip() or "未分类"
        record = {"name": name, "type": typ, "date": date_str}
        if self._edit_row >= 0 and self._edit_row < len(self.items):
            self.items[self._edit_row] = record
        else:
            self.items.append(record)
        save_countdown(self.items)
        self._edit_row = -1
        self.name_edit.clear()
        self._reload()
        d = days_until(date_str)
        if d is not None:
            self.pet.say(countdown_line(typ, name, d))

    def _delete(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self.items):
            return
        name = self.items[row].get("name", "")
        ok = QMessageBox.question(
            self, "删除倒数日", f"确定删掉「{name}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        self.items.pop(row)
        save_countdown(self.items)
        self._edit_row = -1
        self._reload()

    def _on_double_clicked(self, item):
        row = self.list.row(item)
        if row < 0 or row >= len(self.items):
            return
        it = self.items[row]
        self._edit_row = row
        reload_types(self.type_combo, "countdown", it.get("type", ""))
        self.name_edit.setText(it.get("name", ""))
        qd = QDate.fromString(it.get("date", ""), "yyyy-MM-dd")
        if qd.isValid():
            self.date_edit.setDate(qd)
        self._refresh_buttons()
        self.name_edit.setFocus()

    def _cancel_edit(self):
        self._edit_row = -1
        self.name_edit.clear()
        self._refresh_buttons()

    def closeEvent(self, e):
        save_countdown(self.items)
        super().closeEvent(e)
