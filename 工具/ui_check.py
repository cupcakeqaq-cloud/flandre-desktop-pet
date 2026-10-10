"""界面自检：把五个对话框全部构造一遍，再跑一遍计时器控制路径。

用 offscreen 平台跑，不需要真实桌面；双击同目录的 `界面自检.bat` 即可。
改了 pet_window / timers / todo / countdown_day / settings_dialog / theme 之后跑一次，
能挡住「导入名写错、函数签名对不上、信号连错、控件属性改名」这类改坏。
**改了台词之后也跑一次**：它会检查打包字体里有没有界面要显示的全部字
（字体是子集化的，加了新字要先双击「字体子集化.bat」）。

数据全部写到 `.tmp\\ui_check_data\\`，跑完自动删掉，不会碰 `data\\` 下的
settings.json / todos.json / countdown.json。
"""

import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtGui import QFont, QFontDatabase, QRawFont          # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox      # noqa: E402

import data_manager                                        # noqa: E402
import theme                                               # noqa: E402
import timers                                              # noqa: E402
import todo                                                # noqa: E402
import countdown_day                                       # noqa: E402
import settings_dialog                                     # noqa: E402
from font_subset import project_chars                      # noqa: E402
from pet_window import PetWindow                           # noqa: E402


def main():
    app = QApplication([])

    # 数据隔离：所有读写都落到临时目录，跑完即弃（别用系统 %TEMP%，沙箱下可能不可写）
    tmp_dir = Path(__file__).resolve().parent.parent / ".tmp" / "ui_check_data"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    data_manager.DATA_DIR = tmp_dir

    # 1. 主题小工具
    assert theme.hline().objectName() == "hline"
    card, form = theme.card_form()
    assert card.objectName() == "card" and form is not None
    assert "QGroupBox" not in theme.QSS and "QScrollArea" not in theme.QSS
    assert "QRadioButton" not in theme.QSS and "QProgressBar" not in theme.QSS

    # 2. 五个对话框都能构造（构造过程会走 QSS / 卡片表单 / 类型下拉框）
    pom_dlg = timers.PomodoroDialog()
    timers.CountdownDialog()
    todo.TodoDialog(None)
    countdown_day.CountdownDayDialog(None)
    settings_dialog.SettingsDialog(None)
    pet = PetWindow()

    # 3. 类型下拉框：内置项都在，且能把手写的类型保留住
    combo = QComboBox()
    timers.reload_types(combo, "task")
    assert combo.count() >= 4, combo.count()
    timers.reload_types(combo, "task", "手写的新类型")
    assert combo.currentText() == "手写的新类型"

    # 4. 类型管理窗能开、且被父对话框持引用
    timers.open_type_manager(pom_dlg, pom_dlg.type, "task")
    assert isinstance(pom_dlg._type_dlg, timers.TypeManagerDialog)

    # 5. 计时器：按钮 / 心情 / 控制指令
    assert [b["reply"] for b in pet.pomodoro._buttons()] == ["@pause", "@add", "@stop"]

    timers.Pomodoro._save_memory = staticmethod(lambda opts: None)   # 别写盘
    pet.pomodoro.start({"focus": 25, "break": 5, "cycles": 4,
                        "long_every": 4, "long_break": 15})
    assert pet.pomodoro.is_running() and pet._timer_busy()
    assert pet._route_timer_control("@pause") and pet.pomodoro.paused
    assert [b["reply"] for b in pet.pomodoro._buttons()] == ["@resume", "@add", "@stop"]
    assert pet.pomodoro._mood() == "unhappy"
    before = pet.pomodoro.remaining
    assert pet._route_timer_control("@add")
    assert pet.pomodoro.remaining == before + 60
    assert pet._route_timer_control("@stop")
    assert not pet._timer_busy() and pet.pomodoro._mood() == ""

    pet.countdown.start(60, "考试")
    before = pet.countdown.remaining
    assert pet._route_timer_control("@add")
    assert pet.countdown.remaining == before + 60
    assert pet.countdown.extra == 60.0, pet.countdown.extra
    pet.countdown.stop(quiet=True)
    assert not pet._route_timer_control("@add")      # 没在跑就不该被接管

    # 6. 表情别名：happy / unhappy / 乱写 / 空，都只能落到已知帧
    for mood in ("happy", "unhappy", "angry", "", "乱写"):
        pet.set_timer_mood(mood, seconds=0.1)
        assert pet.timer_mood in ("", "happy", "angry"), pet.timer_mood
    pet.set_timer_mood("")

    # 7. 打包字体里真有界面要显示的字（字体被子集化过，这里是唯一会缺字的地方）
    fp = Path(__file__).resolve().parent.parent / "font" / "NotoSansSC-VF.ttf"
    fid = QFontDatabase.addApplicationFont(str(fp))
    assert fid >= 0, f"装不上字体：{fp}"
    families = QFontDatabase.applicationFontFamilies(fid)
    assert families, "字体没有家族名"
    raw = QRawFont.fromFont(QFont(families[0], 10))
    need = project_chars() | set("0123456789:/.-")
    missing = sorted(c for c in need if not raw.supportsCharacter(ord(c)))
    assert not missing, f"字体里缺这些字，重跑一次「字体子集化.bat」：{missing}"

    print("SELFCHECK OK - 界面自检全部通过")
    del app
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
