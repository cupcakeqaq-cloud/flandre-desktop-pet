"""界面自检：把五个对话框全部构造一遍，再跑一遍计时器控制路径。

用 offscreen 平台跑，不需要真实桌面；双击同目录的 `界面自检.bat` 即可。
改了 pet_window / timers / todo / countdown_day / settings_dialog / theme /
bubble / dialogue / hourly 之后跑一次，能挡住「导入名写错、函数签名对不上、
信号连错、控件属性改名」这类改坏。
**改了台词之后也跑一次**：它会检查打包字体里有没有界面要显示的全部字
（字体是子集化的，加了新字要先双击「字体子集化.bat」）。

数据全部写到 `.tmp\\ui_check_data\\`，跑完自动删掉，不会碰 `data\\` 下的
settings.json / todos.json / countdown.json。
"""

import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import Qt                            # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPixmap, QRawFont  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox,            # noqa: E402
                               QMessageBox)

import bubble                                              # noqa: E402
import data_manager                                        # noqa: E402
import dialogue                                            # noqa: E402
import hourly                                              # noqa: E402
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

    # 8. 台词里不许出现字面的「你」——自定义称呼后那些句子会露馅
    def walk(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)

    raw = json.loads((Path(__file__).resolve().parent.parent / "data" /
                      "dialogue.json").read_text(encoding="utf-8"))
    bad = [s for s in walk(raw) if "你" in s]
    assert not bad, "台词里有写死的「你」，请改成 {nickname}：%r" % bad[:3]

    # 9. 旧设置项 nickname_replace_all 已经删掉了
    assert "nickname_replace_all" not in data_manager.DEFAULT_SETTINGS

    # 10. 选项按钮上的文字也得把 {nickname} 填掉（pick_choice 是唯一入口）
    (tmp_dir / "settings.json").write_text(
        json.dumps({"nickname": "主人"}, ensure_ascii=False), encoding="utf-8")
    seen_nick = False
    for ch in raw.get("choices", []):
        dialogue._dialogue = {"choices": [ch]}     # 单元素列表 = 必定取到这一条
        got = dialogue.pick_choice()
        assert got, "pick_choice 返回了空"
        texts = [got.get("line", "")] + [o.get("label", "") for o in got["options"]]
        for t in texts:
            assert "{" not in t and "}" not in t, "按钮/正文漏了占位符：%r" % t
            seen_nick = seen_nick or "主人" in t
    assert seen_nick, "称呼没被替换进去，pick_choice 是不是没走 _fmt？"

    # 11. 气泡尺寸是确定性的：宽度一律 BUBBLE_W，同一句话必得同一个高度，
    # 且正文一个像素都不许被裁
    b = bubble.SpeechBubble()
    for kind in ("click", "idle_talk"):
        texts = [t for t in raw.get(kind, []) if isinstance(t, str)]
        for t in texts[:25]:
            b.show_message(t)
            first = (b.width(), b.height())
            assert b.width() == bubble.BUBBLE_W, \
                f"气泡宽度不是固定的 {bubble.BUBBLE_W}：{b.width()} {t!r}"
            assert b.height() >= b.layout().sizeHint().height(), \
                f"气泡比内容矮，正文会被裁：{t!r}"
            b.show_message(t)                      # 同一句再来一遍
            assert (b.width(), b.height()) == first, \
                f"同一句话量出两种尺寸：{first} -> {(b.width(), b.height())} <- {t!r}"
            assert b.label.height() == b.label.heightForWidth(b.label.width()), \
                f"正文高度不是 heightForWidth 的结果：{t!r}"

    # 11b. 选项气泡换过内容以后尺寸还得一样。回归：重建的按钮曾是隐藏态，布局把
    # 它按空项算（0 高），气泡最后比内容矮一截，按钮被挤成没字的实心小条。
    opts = [{"label": "有点像", "reply": "x"}, {"label": "不太像", "reply": "y"}]
    b.show_message("我和姐姐像吗？", opts)
    first = (b.width(), b.height())
    b.show_message("我先说一句别的。")
    b.show_message("我和姐姐像吗？", opts)
    assert (b.width(), b.height()) == first, \
        f"换过内容后选项气泡尺寸变了：{first} -> {(b.width(), b.height())}"
    assert all(not btn.isHidden() for btn in b._opt_buttons), \
        "重建的选项按钮处于隐藏态（布局会按空项算，气泡就被挤扁了）"
    assert all(btn.height() >= 30 for btn in b._opt_buttons), \
        f"选项按钮被挤扁：{[btn.height() for btn in b._opt_buttons]}"
    assert b.height() >= b.layout().sizeHint().height(), "选项气泡比内容矮，按钮会被裁"

    # 11c. 长台词之后短台词必须缩回去。回归：`QLabel::sizeForWidth()` 会拿控件当前
    # 高度当返回值的下限，量高度前不先把正文固定高度清 0，气泡就只会越长越高。
    long_line = ("今天也一起把该做的事情做完吧，做完了就奖励自己休息一下，"
                 "不许偷偷熬夜，我可是会一直看着你的哦。")
    b.show_message("嗯嗯。")
    small = (b.width(), b.height())
    b.show_message(long_line)
    tall = b.height()
    assert tall > small[1], "长台词的正文没换行？"
    b.show_message("嗯嗯。")
    assert (b.width(), b.height()) == small, \
        f"长台词之后气泡缩不回去：{small} -> 长 {tall} -> {(b.width(), b.height())}"

    # 12. 对话避重：只有「紧接着又抽到同一条」被排除，两条必然交替
    two = ["第一条", "第二条"]
    dialogue._dialogue = {"idle_talk": two}
    dialogue._last_said.clear()
    said = [dialogue.pick("idle_talk") for _ in range(8)]
    assert set(said) == set(two), said
    assert all(said[i] != said[i + 1] for i in range(len(said) - 1)), \
        f"连着说了同一句：{said}"
    dialogue._dialogue = raw
    dialogue._last_said.clear()

    # 13. 右键菜单：圆角菜单该开的属性都开了，图标都画出来了、且不会压到圆弧上
    menu = theme.make_menu(None)
    for text, name in (("隐藏", "hide"), ("番茄钟", "tomato"), ("倒计时", "timer"),
                       ("倒数日", "day"), ("待办清单", "todo"),
                       ("打开收藏文件夹", "folder"), ("设置", "settings"),
                       ("退出", "quit")):
        theme.add_item(menu, text, name)
    assert isinstance(menu, theme.RoundedMenu), "默认应该是有图标的圆角菜单"
    assert menu.styleSheet() == theme.MENU_STYLE
    for name in theme._ICONS:
        pm = theme.icon(name, theme.PRIMARY, 18).pixmap(18, 18)
        img = pm.toImage()
        painted = sum(1 for y in range(18) for x in range(18)
                      if img.pixelColor(x, y).alpha() > 32)
        assert painted > 4, f"图标 {name} 是空的（只有 {painted} 个像素）"
    menu.showEvent(None)          # 离屏平台不真弹窗，手动走一遍圆角/阴影设置
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), \
        "没有透明背景的话，QSS 的圆角会露出方角（就是「四角发黑」）"
    assert menu.graphicsEffect() is None, \
        "菜单不该再挂阴影了：QGraphicsDropShadowEffect 的模糊半径比透明边距还大，" \
        "被裁之后就是用户说的「大黑边」"
    assert theme.MENU_MARGIN > theme.MENU_RADIUS, \
        "透明边距必须大于圆角半径，否则菜单项会压到圆弧上"
    menu.ensurePolished()
    menu.resize(menu.sizeHint())
    for act in menu.actions():
        box = menu.actionGeometry(act)
        assert box.left() >= theme.MENU_MARGIN, f"菜单项越过了透明边距：{act.text()}"
        assert not act.icon().isNull(), f"菜单项没图标：{act.text()}"
    menu.close()

    # 13c. 四角必须真的透出去：不带阴影效果以后 render 才可靠，洋红打底、圆角外
    # 还应该是洋红（以前这里四角是实心卡片色 = 直角 = 「四角发黑」的来源）
    # 真机回归（offscreen 测不出合成）：菜单窗口必须带 FramelessWindowHint，否则
    # Windows 不会给这扇窗口开 WS_EX_LAYERED，透明边距那一圈会合成成纯黑 ——
    # 就是用户报的「大黑边」。（试过 NoDropShadowWindowHint，Qt 对 Popup 不收这个
    # 标志，设了也查不到，所以不在这里断言。）
    flags = menu.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, \
        "菜单窗口缺 FramelessWindowHint，真机上透明边距会变成黑边"
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground), \
        "菜单窗口没开透明背景"
    menu.resize(menu.sizeHint())
    shot = QPixmap(menu.size())
    shot.fill(QColor(255, 0, 255))
    menu.render(shot)
    img = shot.toImage()
    for x, y in ((0, 0), (menu.width() - 1, 0), (0, menu.height() - 1),
                 (menu.width() - 1, menu.height() - 1)):
        assert img.pixelColor(x, y).name() == "#ff00ff", \
            f"菜单角 ({x},{y}) 没透出背景，圆角没生效"
    # ① 卡片必须是自己画的（QSS 背景刷满 border box 才算「莫名其妙的阴影框」的元凶）
    assert img.pixelColor(menu.width() // 2, menu.height() // 2).name() == theme.CARD.lower(), \
        "菜单中心不是卡片色：paintEvent 没画底板"
    # ② 最外那圈必须一个像素都不画。这条就是用户报的「拉开菜单后有莫名其妙的阴影框」：
    #    QSS 的 background 会刷满整个 border box，透明 border 只让位不挡刷子。
    band = theme.MENU_MARGIN - 2
    for x in range(0, menu.width()):
        for y in (0, menu.height() - 1):
            assert img.pixelColor(x, y).name() == "#ff00ff", \
                f"菜单透明边距被画了东西：({x},{y})"
    for y in range(0, menu.height()):
        for x in (0, menu.width() - 1):
            assert img.pixelColor(x, y).name() == "#ff00ff", \
                f"菜单透明边距被画了东西：({x},{y})"
    assert band > 0 and theme.MENU_BORDER >= 1, "菜单得有 1px 描边，且边距要容得下它"

    # 13b. 托盘菜单跟右键菜单共用同一套（别哪天又退回系统默认样式）
    fired = []
    tmenu = theme.make_menu(None)
    tact = theme.add_item(tmenu, "隐藏", "hide", lambda: fired.append(1))
    tact.trigger()
    assert fired == [1], "theme.add_item 没把回调接上"
    assert tmenu.styleSheet() == theme.MENU_STYLE, "托盘菜单没套主题"
    assert not theme.icon("eye", theme.PRIMARY).isNull(), \
        "托盘菜单「显示」态的图标画不出来"

    # 14. 「删除选中」跟着选中行变灰/变亮（漏了信号线的话按钮会一直是灰的）
    tdlg = todo.TodoDialog(None)
    original_load, original_save = todo.load_todos, todo.save_todos
    saved = {"items": [{"text": "写自检", "done": False},
                       {"text": "跑一遍", "done": True}]}
    todo.load_todos = lambda: [dict(it) for it in saved["items"]]
    todo.save_todos = lambda items: saved.__setitem__(
        "items", [dict(it) for it in items])
    try:
        tdlg._reload()
        tdlg.list.setCurrentRow(-1)
        assert not tdlg.del_btn.isEnabled(), "没选中任何行时「删除选中」不该能按"
        tdlg.list.setCurrentRow(0)
        assert tdlg.del_btn.isEnabled(), "选中了一行，「删除选中」却还是灰的"
        asked = []
        original_question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
        try:
            tdlg._delete()                          # 答「否」→ 什么都不能被删掉
            assert len(tdlg.items) == 2, "二次确认里选了「否」却还是删了"
            assert asked, "删除没有弹二次确认"
            QMessageBox.question = staticmethod(
                lambda *a, **k: asked.append(a[2]) or QMessageBox.Yes)
            tdlg.list.setCurrentRow(0)
            tdlg._delete()
            assert len(tdlg.items) == 1, "确认删除后没删掉"
            assert len(saved["items"]) == 1, "删除没有落盘"
        finally:
            QMessageBox.question = original_question
    finally:
        todo.load_todos, todo.save_todos = original_load, original_save
        tdlg.close()

    # 15. 整点播报：跨小时后的前几分钟内补报，不再因为卡顿漏掉一整小时
    fake = {"hour": 13, "minute": 0}
    real_localtime = hourly.time.localtime
    hourly.time.localtime = lambda *a: type("T", (), {
        "tm_hour": fake["hour"], "tm_min": fake["minute"]})()
    said = []
    pet.say = lambda *a, **k: said.append(a)
    try:
        reporter = hourly.HourlyReporter(pet)
        reporter.timer.stop()
        reporter._check()                           # 第一次只记下当前小时
        fake["hour"], fake["minute"] = 14, 0
        reporter._check()
        assert len(said) == 1, f"整点该播报一次，实际 {len(said)} 次"
        fake["hour"], fake["minute"] = 14, 8      # 只比小时的话这里会被漏掉
        reporter._check()
        fake["hour"], fake["minute"] = 15, 3      # 卡顿几分钟后仍要补报
        reporter._check()
        assert len(said) == 2, f"宽限期内该补报一次，实际 {len(said)} 次"
        fake["hour"], fake["minute"] = 16, 30     # 错过太久就不补了，等下一个整点
        reporter._check()
        assert len(said) == 2, "错过太久还补报，会突然被灌一堆整点问候"
    finally:
        hourly.time.localtime = real_localtime
        reporter.timer.stop()

    # 16. 微调框/下拉框的箭头是手绘的。Qt 的 QSS 画不出三角形（写 border 只会得到
    # 两个小方块），子控件被 QSS 接管后基础样式也不再画原生箭头——所以箭头由
    # theme.Chevron* 这几个子类自己在 paintEvent 里画，这里量右侧有没有主色像素。
    spin = theme.ChevronSpinBox()
    spin.setStyleSheet(theme.QSS)
    spin.setRange(0, 99)
    spin.resize(120, 34)
    spin.show()
    app.processEvents()
    img = spin.grab().toImage()
    hits = sum(1 for y in range(2, img.height() // 2)
               for x in range(img.width() - 17, img.width() - 3)
               if img.pixelColor(x, y).lightness() < 160)   # 按钮底色很浅，深色只可能是箭头
    assert hits > 4, f"微调框的箭头没画出来（只有 {hits} 个深色像素）"
    spin.close()
    assert isinstance(pom_dlg.focus, theme.ChevronSpinBox), \
        "番茄钟的「专注时长」没换成手绘箭头版"
    assert isinstance(timers.CountdownDialog().type, theme.ChevronComboBox), \
        "倒计时的类型下拉没换成手绘箭头版"
    assert isinstance(settings_dialog.SettingsDialog(None).bubble_dur,
                      theme.ChevronDoubleSpinBox), "设置里的气泡时长没换成手绘箭头版"
    ddlg = countdown_day.CountdownDayDialog(None)
    assert isinstance(ddlg.date_edit, theme.ChevronDateEdit), \
        "倒数日的日期框没换成手绘箭头版"
    assert isinstance(ddlg.type_combo, theme.ChevronComboBox), \
        "倒数日的类型下拉没换成手绘箭头版"

    # 17. 层级：功能窗要压得住桌宠，气泡说话时又要把功能窗重新抬起来（否则出现
    # 「人物在窗口下面、气泡飘在窗口上面」的奇观，用户 2026-10-15 报的）
    assert pom_dlg.windowFlags() & Qt.WindowType.WindowStaysOnTopHint, \
        "功能窗没置顶标志，会被置顶的桌宠压住"
    assert hasattr(pet, "_raise_dialogs") and hasattr(pet, "_dlgs"), \
        "桌宠缺少把功能窗重新抬起来的入口"
    pet._raise_dialogs()                    # 没有开着的窗口时也必须能空跑

    print("SELFCHECK OK - 界面自检全部通过")
    del app
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
