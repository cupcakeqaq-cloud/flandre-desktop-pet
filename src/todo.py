"""待办清单。

2026-10-08 第五批：
- 卡片式布局：标题 + 进度统计 + 任务列表 + 底部输入区。
- 勾选完成 → 开心表情（站立 4.png）+ ``sound\\tada.wav``。
- **不再在关窗时偷偷删除已完成任务**，改为显式的「清除已完成」按钮（带二次确认）。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QPushButton, QLineEdit, QLabel,
                               QFrame, QMessageBox)

import dialogue
import sound
import theme
import config
from data_manager import load_todos, save_todos


class TodoDialog(QDialog):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        theme.setup_dialog(self, "待办清单")
        self.setMinimumSize(420, 420)
        self.items = []
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("待办清单")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        self.progress = QLabel("")
        self.progress.setObjectName("pill")
        head.addWidget(self.progress)
        root.addLayout(head)

        hint = QLabel("勾选就完成啦；双击可以修改内容。")
        hint.setObjectName("hint")
        root.addWidget(hint)
        root.addWidget(theme.hline())

        self.list = QListWidget()
        self.list.setMinimumHeight(200)
        self.list.setAlternatingRowColors(False)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.itemDoubleClicked.connect(self._on_double_clicked)
        root.addWidget(self.list, 1)

        empty = QLabel("还没有任务，在下面加一条吧。")
        empty.setObjectName("muted")
        empty.setAlignment(Qt.AlignCenter)
        self.empty = empty
        root.addWidget(empty)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("输入新任务，回车即可添加……")
        self.edit.returnPressed.connect(self._add)
        add_btn = QPushButton("添加")
        add_btn.setToolTip("把输入框里的内容加到清单末尾")
        add_btn.clicked.connect(self._add)
        row.addWidget(self.edit, 1)
        row.addWidget(add_btn)
        root.addLayout(row)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.del_btn = QPushButton("删除选中")
        self.del_btn.setObjectName("danger")
        self.del_btn.setToolTip("删除列表中选中的那一条")
        self.del_btn.clicked.connect(self._delete)
        self.clear_btn = QPushButton("清除已完成")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.setToolTip("一次性移除所有已勾选的任务")
        self.clear_btn.clicked.connect(self._clear_done)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(self.del_btn)
        btns.addWidget(self.clear_btn)
        btns.addStretch()
        btns.addWidget(close_btn)
        root.addLayout(btns)

        self._reload()

    # ---------- 列表 ----------
    def _reload(self):
        self.items = load_todos()
        self.items = [it for it in self.items if isinstance(it, dict) and it.get("text")]
        self._loading = True
        self.list.clear()
        for it in self.items:
            text = it.get("text", "")
            done = bool(it.get("done", False))
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if done else Qt.Unchecked)
            if done:
                f = item.font()
                f.setStrikeOut(True)
                item.setFont(f)
            item.setToolTip("双击可以修改内容")
            self.list.addItem(item)
        self._loading = False
        self._refresh_stats()

    def _refresh_stats(self):
        total = len(self.items)
        done = sum(1 for it in self.items if it.get("done"))
        self.progress.setText(f"{done} / {total}")
        self.empty.setVisible(total == 0)
        self.list.setVisible(total > 0)
        self.clear_btn.setEnabled(done > 0)
        self.del_btn.setEnabled(self.list.currentRow() >= 0)

    def _save(self):
        save_todos(self.items)
        self._refresh_stats()

    # ---------- 操作 ----------
    def _add(self):
        text = self.edit.text().strip()
        if not text:
            return
        self.items.append({"text": text, "done": False})
        self.edit.clear()
        save_todos(self.items)
        self._reload()
        self.list.setCurrentRow(len(self.items) - 1)

    def _delete(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self.items):
            return
        self.items.pop(row)
        save_todos(self.items)
        self._reload()

    def _clear_done(self):
        done = sum(1 for it in self.items if it.get("done"))
        if done <= 0:
            return
        ok = QMessageBox.question(
            self, "清除已完成", f"确定移除 {done} 条已完成的任务吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        self.items = [it for it in self.items if not it.get("done")]
        save_todos(self.items)
        self._reload()

    def _on_double_clicked(self, item):
        from PySide6.QtWidgets import QInputDialog
        row = self.list.row(item)
        if row < 0 or row >= len(self.items):
            return
        text, ok = QInputDialog.getText(self, "修改任务", "新的内容：",
                                        QLineEdit.Normal, item.text())
        if not ok:
            return
        text = text.strip()
        if not text:
            return
        self.items[row]["text"] = text
        save_todos(self.items)
        self._reload()

    def _on_item_changed(self, item):
        if self._loading:
            return
        row = self.list.row(item)
        if row < 0 or row >= len(self.items):
            return
        done = item.checkState() == Qt.Checked
        prev = bool(self.items[row].get("done", False))
        self.items[row]["done"] = done
        f = item.font()
        f.setStrikeOut(done)
        item.setFont(f)
        self._save()
        if done and not prev:
            # 任务完成：tada 音效 + 站立 4.png（开心）
            sound.task_done()
            self.pet.set_timer_mood("happy", seconds=config.DONE_MOOD_SECONDS)
            line = dialogue.pick("todo_done")
            if line:
                self.pet.say(line, mood="happy")

    def closeEvent(self, e):
        # 只保存，不自动删除已完成的任务
        save_todos(self.items)
        super().closeEvent(e)
