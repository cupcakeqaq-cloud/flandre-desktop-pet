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
import ctypes
import time
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QEvent, QPointF, Qt            # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QKeyEvent,   # noqa: E402
                           QMouseEvent, QPixmap, QRawFont, QRegion)
from PySide6.QtWidgets import (QApplication, QComboBox,            # noqa: E402
                               QLabel, QMessageBox)

import bubble                                              # noqa: E402
import config                                              # noqa: E402
import data_manager                                        # noqa: E402
import dialogue                                            # noqa: E402
import hourly                                              # noqa: E402
import theme                                               # noqa: E402
import timers                                              # noqa: E402
import todo                                                # noqa: E402
import countdown_day                                       # noqa: E402
import settings_dialog                                     # noqa: E402
import voice as voice_mod                                  # noqa: E402
from font_subset import project_chars                      # noqa: E402
from pet_window import PetWindow, S                        # noqa: E402


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
    # 13a. 首尾条目离卡片上下边，得跟离左右边一样宽（用户 2026-10-23：
    #      「菜单上下边太窄了，加宽到和左右边一样的宽度」）
    box_top = menu.actionGeometry(menu.actions()[0])
    box_bot = menu.actionGeometry(menu.actions()[-1])
    inset_l = box_top.left() - theme.MENU_MARGIN
    inset_t = box_top.top() - theme.MENU_MARGIN
    inset_b = menu.height() - theme.MENU_MARGIN - box_bot.bottom() - 1
    assert abs(inset_t - inset_l) <= 1 and abs(inset_b - inset_l) <= 1, (
        f"菜单上下留白（上 {inset_t} / 下 {inset_b}）和左右（{inset_l}）不一致，"
        f"调整 theme.MENU_PAD_Y（当前 {theme.MENU_PAD_Y}）"
    )
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

    # 14b. 点击回弹：按下换站立\5.png（闭眼）+ 压扁，松开弹回；打盹短按不醒、
    # 按住满 NAP_WAKE_HOLD_MS 才算被吵醒；奔跑中点击保持原样（2026-10-18 第十九批）
    assert "stand1" in pet._frames, "启动必须同步解好 stand1（窗口一出来就得能画）"
    assert {"stand2", "stand5"} <= set(pet._warm_keys) | set(pet._frames), \
        "stand2/stand5 要么已经解好、要么排在预热队列里"
    pet._frame("stand5")                                     # 预热队列是异步的，这里手动补
    assert pet._frames["stand5"][1] == pet._frames["stand1"][1], \
        "5.png 和 1.png 的点击遮罩应该一模一样"

    def mouse(kind):
        pos = QPointF(120, 120)
        return QMouseEvent(kind, pos, pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)

    pet._set_state(S.STAND)
    pet.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    assert pet._pressing and pet._stand_frame() == "stand5", "按下没切闭眼差分"
    assert pet.mask() == QRegion(pet._cur_region.boundingRect()), \
        "压扁期间遮罩要放宽到外接矩形，否则下移的斜边会被切出缺口（被吞像素）"
    pet._squash_anim.setCurrentTime(config.SQUASH_MS)        # 手动走完压下动画
    assert pet._squash > 0.9, pet._squash
    assert pet._cur_img is not None and pet._cur_img.devicePixelRatio() == 1.0, \
        "压扁是逐行 1:1 拷物理像素，_cur_img 必须是 1:1 原图（带 dpr 会被再缩放）"
    pet.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease))
    assert not pet._pressing and pet.talking, "松开该弹回并照旧说话"
    assert pet._stand_frame() == "stand5", "松开后闭眼帧还得留一会儿"
    # 松开时会随机说一句预设台词，里面有「唉/算了」这种词就会顺手挂上 sweat 表情，
    # 把站立帧抢过去（踩到过的偶发红）。这一段只验回弹，表情先清掉。
    pet.expression = ""
    pet.expression_until = 0.0
    pet._bounce_until = 0.0                                  # 不等真的 BLINK_HOLD_SECONDS 秒
    assert pet._stand_frame() == "stand2", pet._stand_frame()
    pet._squash_anim.setCurrentTime(config.SQUASH_REBOUND_MS)
    assert abs(pet._squash) < 1e-6, pet._squash
    assert pet.mask() == pet._cur_region, "弹回后遮罩必须收回精确轮廓（否则贴图外那圈空白也能点）"

    pet.talking = False                                      # 清掉上一段对话
    pet.talk_until = 0.0
    pet.bubble.hide()
    pet._set_state(S.REST)                                   # 打盹：短按只压扁
    pet.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    assert pet._pressing and pet._nap_hold_timer.isActive() and not pet._bounce_frame
    pet.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease))
    assert pet.state == S.REST and not pet.talking, "打盹短按把人吵醒了"
    pet.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    pet._on_nap_hold()                                       # 等价于按住满 5 秒
    assert pet.talking and pet._rest_wake_count == 1, "按住满 5 秒没被吵醒"
    pet.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease))
    assert not pet._pressing and pet._rest_wake_count == 1   # 松开不再补一次点击

    pet._set_state(S.RUN)                                    # 奔跑中：原样
    pet.mousePressEvent(mouse(QEvent.Type.MouseButtonPress))
    assert not pet._pressing, "奔跑中不该压扁"
    pet.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease))
    pet._set_state(S.STAND)

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

    # 21. 离线 / 在线双模式（第二十一批）
    #     chat_history 跟着 DATA_DIR 落到临时目录，别写脏 data\
    from PySide6.QtCore import QEventLoop, QTimer      # noqa: E402
    import chat_ui                                     # noqa: E402
    import net as net_mod                              # noqa: E402

    # 地址补全：域名 / 带尾斜杠 / 已经写了 /v1 / 整条都贴进来，都不能补重
    assert net_mod.endpoint("https://api.deepseek.com") == \
        "https://api.deepseek.com/chat/completions"
    assert net_mod.endpoint("https://api.deepseek.com/") == \
        "https://api.deepseek.com/chat/completions"
    assert net_mod.endpoint("https://api.deepseek.com/v1") == \
        "https://api.deepseek.com/v1/chat/completions"
    assert net_mod.endpoint("https://x/v1/chat/completions") == \
        "https://x/v1/chat/completions"

    # 离线：默认设置下菜单里不该有「聊天」
    pet.settings = json.loads(json.dumps(data_manager.DEFAULT_SETTINGS))
    assert not pet._llm_ready(), "默认设置不该是「在线」"
    assert "聊天" not in [t for t, _i, _c in pet._menu_items()], \
        "离线时右键菜单里不该出现「聊天」"

    # 在线：三样填齐 + 打开开关（只改内存，别动磁盘上的 settings）
    pet.settings["llm"].update({"enabled": True, "api_key": "sk-test"})
    assert pet._llm_ready(), "填齐 base_url / key / 模型后应该算在线"
    texts = [t for t, _i, _c in pet._menu_items()]
    assert texts and texts[0] == "聊天", "在线时「聊天」要排在最前面"

    # 删掉 key 就该回离线（用户验收的第 4 条）
    pet.settings["llm"]["api_key"] = ""
    assert not pet._llm_ready(), "key 删掉后还留在在线模式"
    assert "聊天" not in [t for t, _i, _c in pet._menu_items()]
    pet.settings["llm"]["api_key"] = "sk-test"

    # 模拟模式：不联网，直接回一句固定文本
    os.environ[net_mod.MOCK_ENV] = "1"
    chat = chat_ui.ChatWindow(pet)
    loop = QEventLoop()
    pet.net.done.connect(lambda *_: loop.quit())
    QTimer.singleShot(5000, loop.quit)          # 兜底，别把自检挂死
    chat.input.setText("你好")
    chat._send()
    loop.exec()
    assert not chat._waiting, "收到回复后输入框该解锁了"
    hist = data_manager.load_chat_history()
    roles = [m.get("role") for m in hist["messages"]]
    assert roles[-2:] == ["user", "assistant"], f"聊天记录不对：{roles}"
    assert hist["messages"][-1]["content"] == net_mod.MOCK_TEXT
    assert set(hist) == {"messages", "usage", "last_date"}, hist.keys()
    assert data_manager.load_chat_history() == hist, "chat_history 读写不一致"

    chat.append_assistant("嗯，在呢。", active=True)     # 主动说话也要能记
    hist = data_manager.load_chat_history()
    assert hist["messages"][-1]["active"] is True, "主动说的话没带 active 标记"
    chat.close()

    # 语音这一轮只占位：必须明确回「不支持」，不能假装成功
    errs = []
    pet.net.done.connect(lambda k, t, e: errs.append((k, e)))
    pet.net.transcribe("nope.wav")
    assert ("stt", "unsupported") in errs, f"transcribe 占位实现不对：{errs}"

    # 全屏检测：只断言「能跑、不抛、返回布尔」。开发机上开着全屏的浏览器就会命中，
    # 所以这里不断言具体值（下面关掉开关那条才是确定性的）
    assert isinstance(pet._check_fullscreen(), bool), "全屏检测返回了非布尔值"

    # 设置里那两张新卡片能构造、能保存，保存后 _llm_ready() 跟着变
    sdlg = settings_dialog.SettingsDialog(pet)
    sdlg.llm_on.setChecked(True)
    sdlg.llm_url.setText("https://api.deepseek.com")
    sdlg.llm_key.setText("sk-test")
    sdlg.llm_model.setText("deepseek-chat")
    sdlg.llm_temp.setValue(0.7)
    sdlg.watch_hide_full.setChecked(False)
    sdlg._save()
    saved = data_manager.load_settings()
    assert saved["llm"]["api_key"] == "sk-test", saved["llm"]
    assert saved["llm"]["enabled"] is True, "保存后 llm.enabled 没写回去"
    assert saved["watch"]["hide_in_fullscreen"] is False, "全屏隐藏开关没写回去"
    assert pet._llm_ready(), "保存后 refresh_settings 没把新设置带过来"
    # 关掉「全屏时隐藏」之后，检测整套就不该再生效
    assert pet._check_fullscreen() is False, "关掉开关后仍在判全屏"

    # 22. 在线模式：点一下＝模型现编（第二十一批）
    import brain                                       # noqa: E402
    import pet_window as pet_mod                       # noqa: E402
    import sound as sound_mod                          # noqa: E402

    # 提示词：人设 / 占位符 / 四条硬约束都得在 system 里
    msgs = brain.build_messages("click", brain.context(pet))
    assert msgs[0]["role"] == "system" and len(msgs) == 2, msgs
    sys_text = msgs[0]["content"]
    for must in ("芙兰朵露", "495", "{nickname}", "不写动作", "40 个字", "虽然"):
        assert must in sys_text, "system 里缺「%s」" % must
    # 2026-10-24 用户拍板：核心能力那段「看什么都像眼睛」的写法不对，删了；
    # 句尾也不再挂固定尾巴（「～的哦」是预设台词里偶尔出现的，不是人设要求）
    assert "眼睛" not in brain.PERSONA, "核心能力那段该删掉了"
    assert "～的哦" not in brain.PERSONA, "句尾口癖该删掉了"
    # 2026-10-24 第四轮：二设「爱吃布丁」要留在人设里；反定型句那条要留在 RULES 里
    assert "布丁" in brain.PERSONA, "人设里没了布丁二设"
    # 2026-10-24 补充⑪：人设按用户手改的「人设校对表.docx」写定了，这几处别再被顺手改掉
    # 2026-10-25 第二十九批：用户给了新版角色文案，问过之后删掉了「态度没个准/闹脾气」，
    # 改成天真黏人 + 渴望陪伴；「残忍但那不是坏」保留。断言跟着换锚点。
    for must in ("玩伴", "天真烂漫", "不过你有时不觉得被关着", "寂寞", "中二的幻想"):
        assert must in brain.PERSONA, "人设里缺「%s」" % must
    assert "闹脾气" not in brain.PERSONA, "「态度没个准/闹脾气」这版用户已经作废了"
    for must in ("控制不了自己的力量", "腹黑毒舌", "你觉得她人挺好"):
        assert must in brain.OTHERS, "其他角色里缺「%s」" % must
    assert "主人" not in brain.PERSONA, "人设里又用「主人」称呼用户了"
    assert "主人" not in "".join(brain.ASKS["click"] + brain.ASKS["active"]), \
        "旁白里又用「主人」称呼用户"
    for must in ("换个说法", "句子长短错开", "十句里顶多一句"):
        assert must in sys_text, "RULES 里缺「%s」" % must
    # 2026-10-24 用户要「陪伴感」：谈心那条得允许稍长、但明令不许说套话/讲大道理
    for must in ("先把他的情绪接住", "别急着出主意", "加油", "想开点",
                 "道理最多一句", "60 个字以内"):
        assert must in sys_text, "陪伴感那段缺「%s」" % must
    # 2026-10-24 用户怕出过激的事：难过/自伤这类必须硬性接住，不许装傻打岔
    for must in ("当成真事", "不许装听不懂", "等你哭完再说", "站在他这边",
                 "先别一个人扛", "允许你稍微出戏", "夹一句你自己的口气",
                 "不是客服在回访", "12356", "010-82951332",
                 "劝他先找身边", "90 个字以内"):
        assert must in sys_text, "安全/劝解那段缺「%s」" % must
    chat_sys = brain.build_messages("chat", {"history": []})[0]["content"]
    assert "接着他的话往下聊" in chat_sys and "接着他的话往下聊" not in sys_text, \
        "聊天窗那句该只在 chat 模式出现"
    # 语气以 data\dialogue.json 为准：提示词里要带几句那个文件里的样本
    samples = brain.style_lines()
    assert samples, "没从 dialogue.json 抽到语气样本"
    for line in samples:
        assert line in sys_text, "样本「%s」没进提示词" % line
    # 屏幕那行只在 watch.enabled 时才出现
    assert "记事本" not in sys_text
    pet.settings["watch"]["enabled"] = True
    assert "记事本" in brain.build_messages(
        "click", brain.context(pet, screen="记事本"))[0]["content"], \
        "开了「看你屏幕」却没说主人屏幕上是什么"
    pet.settings["watch"]["enabled"] = False
    assert "记事本" not in brain.build_messages(
        "click", brain.context(pet, screen="记事本"))[0]["content"], \
        "没开「看你屏幕」却把窗口标题塞进提示词了"
    pet.settings["watch"]["enabled"] = True

    # 洗台词：去引号 / 星号 / 舞台提示，最多两句，超长截断
    assert brain.clean("“嗯，在呢。”") == "嗯，在呢。"
    assert brain.clean("*（歪头）嗯～在呢*") == "嗯～在呢"
    assert brain.clean("一。二。三。四。五。") == "一。二。三。四。"   # 上限四句
    assert len(brain.clean("啊" * 200)) <= brain.MAX_CHARS
    assert brain.MAX_SENTENCES == 4 and brain.MAX_CHARS == 90
    long_line = "今天是不是挺累的呀。要不先歇会儿，我就在这儿。你想说啥就说，我不催你。"
    kept = brain.clean(long_line)
    assert kept.count("。") == 3 and len(kept) <= 60, "谈心那句该留三句、60 字内：%r" % kept
    # 最要紧那档：说到难受时允许写满四句、90 字，得真劝得动，不能被截半截
    alarm = ("你先别一个人扛。这事搁谁身上都难受，不是你不行。"
             "你今天已经撑很久了。明天再想也来得及，我就在这儿陪你。")
    kept2 = brain.clean(alarm)
    assert kept2.count("。") == 4 and len(kept2) <= brain.MAX_CHARS, \
        "劝解那句该留四句、90 字内：%r" % kept2

    # 语气 → 表情：高兴星星眼 / 生气 / 无语流汗，猜不出就不给表情
    assert brain.mood_of("好耶！布丁！") == "happy", brain.mood_of("好耶！布丁！")
    assert brain.mood_of("哼，不理你了。") == "angry"
    assert brain.mood_of("唉……算了。") == "sweat"
    assert brain.mood_of("唔。") == ""
    assert "sweat" in pet._frame_specs, "站立 6.png 没登记成表情帧"
    assert pet._frame_specs["sweat"][0].exists(), "站立\\6.png 不见了"

    # 第 15 段把 pet.say 换成了记录器、没还回来，这里先接回真的（要验气泡）
    real_say = pet_mod.PetWindow.say.__get__(pet)
    pet.say = real_say
    said = []

    def _spy_say(text, options=None, mood="", active=False):
        said.append((text, options, active))
        real_say(text, options, mood, active)

    pet.say = _spy_say

    # say() 会按语气自己换表情（离线预设和在线现编都走这条路）
    pet.say("哼，不理你了。")
    assert pet.expression == "angry", pet.expression
    pet.say("唉……算了。")
    assert pet.expression == "sweat", pet.expression
    pet.say("好耶！")
    assert pet.expression == "happy", pet.expression

    def _wait_ai(sec=5.0):
        end = QEventLoop()
        pet.net.done.connect(lambda *_: end.quit())
        QTimer.singleShot(int(sec * 1000), end.quit)
        end.exec()

    # 点一下：mock 回一句，气泡里就是那句现编的，没有选项按钮
    os.environ[net_mod.MOCK_ENV] = "1"
    pet.settings["llm"].update({"enabled": True, "api_key": "sk-test"})
    pet._set_state(S.STAND)
    pet.talking = False
    assert pet._llm_ready(), "自检里该是「在线」才对"
    brain.reset_throttle()
    pet._ai_busy = False
    pet._ai_click_at = 0.0
    pet._ai_err_until = 0.0
    pet._on_click()
    _wait_ai()
    assert said, "在线点一下没说话"
    assert said[-1][0] == net_mod.MOCK_TEXT, "气泡里不是模型那句：%r" % (said[-1][0],)
    assert said[-1][2] is True, "主动说的话没带 active 标记"
    assert not pet.bubble._opt_buttons, "在线模式不该冒出选项按钮"

    # 连点 3 下（间隔 50ms）只发 1 次请求：不卡、不排队
    sent = []
    real_chat = pet.net.chat
    pet.net.chat = lambda m, kind="chat": sent.append(m) or real_chat(m, kind)
    pet._ai_click_at = 0.0
    pet._ai_busy = False
    pet._on_click()
    time.sleep(0.05)
    pet._on_click()
    time.sleep(0.05)
    pet._on_click()
    assert len(sent) == 1, "连点 3 下发了 %d 次请求" % len(sent)
    pet.net.chat = real_chat
    _wait_ai()

    # 请求失败 3 次 → 只播报 1 次（60 秒冷却），台词是那句固定的
    said.clear()
    plays = []
    real_play = sound_mod.play
    sound_mod.play = lambda name: plays.append(name)
    pet._ai_err_until = 0.0
    pet._set_state(S.STAND)
    for _ in range(3):
        pet._on_ai_done("click", "", "auth")
    sound_mod.play = real_play
    assert len(said) == 1, "冷却没挡住重复播报：%d 次" % len(said)
    assert "接收失败" in said[0][0], said[0][0]
    assert plays and plays[0] == "error.wav" and plays.count("error.wav") == 1, plays
    assert pet._ai_busy is False, "失败后单飞标记没松开"
    assert not pet.bubble._opt_buttons

    # 离线模式：点她还是 dialogue.json 的台词，选项按钮也还在
    pet.settings["llm"]["api_key"] = ""
    assert not pet._llm_ready()
    pet._set_state(S.STAND)
    said.clear()
    old_random = pet_mod.random.random
    pet_mod.random.random = lambda: 0.0             # 保证走「出选项」那条分支
    try:
        pet._on_click()
    finally:
        pet_mod.random.random = old_random
    assert pet.bubble._opt_buttons, "离线模式点她应该还能出选项按钮"
    assert said and said[-1][0] != net_mod.MOCK_TEXT, "离线模式不该用模型那句"

    # 聊天窗：按钮写「发送」、能手动清空、重启自动清空
    chat2 = chat_ui.ChatWindow(pet)
    assert chat2.send_btn.text() == "发送", chat2.send_btn.text()
    assert chat2.clear_btn.text() == "清空", chat2.clear_btn.text()
    chat2.append_assistant("在呢在呢。", active=True)
    chat2.append_assistant("{nickname} 在呢。", active=True)
    assert "{nickname}" not in chat2.text(), "记录区把占位符露出来了"
    assert data_manager.load_chat_history()["messages"], "主动说的话没落盘"
    chat2.clear_history()
    assert chat2.text().strip() == "", "清空后记录区还有字"
    assert data_manager.load_chat_history()["messages"] == [], "清空后文件里还有记录"
    chat2.close()
    data_manager.save_chat_history(
        {"messages": [{"role": "user", "content": "旧记录"}],
         "usage": {}, "last_date": ""})
    pet._reset_chat_history()
    assert data_manager.load_chat_history()["messages"] == [], "启动时没把旧记录清掉"

    # 主人自己发的那句必须出现在记录区，而且回话前一直留在输入框里（好多看一眼自己发了啥）
    chat3 = chat_ui.ChatWindow(pet)
    pet.net.chat = lambda m, kind="chat": None      # 假装请求发出去了、永远不回来
    chat3.input.setText("我发的这句不能丢")
    chat3._send()
    assert "我发的这句不能丢" in chat3.text(), chat3.text()
    assert chat3.input.text() == "我发的这句不能丢", "回话前输入框就被清了"
    assert chat3._waiting and chat3._watch.isActive(), "看门狗没装上"

    # 卡住 6 秒（timeout 1 + 5）后自己松开：不能永远停在「芙兰在想…」
    pet.settings["llm"]["timeout"] = 0
    chat3._watch.stop()
    chat3._on_timeout()
    assert not chat3._waiting and chat3.input.isEnabled(), "超时没把窗口放回来"
    assert "等太久" in chat3.text(), chat3.text()[-40:]
    assert chat3.input.text() == "", "超时后输入框还留着上一句"
    pet.net.chat = real_chat

    # 聊得长了要能用滚轮往上翻
    chat3.resize(430, 470)
    chat3.show()
    app.processEvents()
    for i in range(30):
        chat3.append_assistant("第 %d 句回话，随便说点什么看看会不会顶出去" % i)
    app.processEvents()          # 气泡是控件，得让布局跑一轮才量得出滚动范围
    bar = chat3.scroll.verticalScrollBar()
    assert bar.maximum() > 0, "聊长了却滚不动"
    bar.setValue(0)
    assert bar.value() == 0, "滚不回顶部"

    # 主人那句靠右、芙兰那句靠左：一眼分得清谁说的（用户反馈「看不见我发的话」）
    # 气泡是一个 QWidget + QHBoxLayout，靠右＝左边是弹簧、靠左＝右边是弹簧。
    def bubble_row(chat, name):
        for i in range(chat._rows.count()):
            holder = chat._rows.itemAt(i).widget()
            if holder is None:
                continue
            bubbles = holder.findChildren(chat_ui._Bubble)
            if bubbles and bubbles[0].objectName() == name:
                yield holder.layout()

    mine = list(bubble_row(chat3, "me"))
    hers = list(bubble_row(chat3, "her"))
    assert mine and hers, "气泡没分左右"
    assert mine[-1].itemAt(0).spacerItem() is not None, "主人那句没靠右"
    assert mine[-1].itemAt(1).widget() is not None, "主人那句话气泡不在右边"
    assert hers[-1].itemAt(0).widget() is not None, "芙兰那句没靠左"
    assert hers[-1].itemAt(1).spacerItem() is not None, "芙兰那句话气泡不在左边"
    # 气泡宽度：最长就到 limit（跟聊天软件一样），短句自己缩
    limit = max(200, int(chat3.scroll.viewport().width() * chat_ui.BUBBLE_WIDTH))
    widths = [wid.width() for row in list(mine) + list(hers)
              for wid in [row.itemAt(1).widget() or row.itemAt(0).widget()]
              if wid is not None]
    assert widths and all(w <= limit for w in widths), widths

    def last_bubble(chat):
        holder = chat._rows.itemAt(chat._rows.count() - 2).widget()
        return holder.findChild(chat_ui._Bubble)

    chat3.append_assistant("这一句故意写得特别特别长，就是为了顶到气泡的最大宽度看看会不会溢出来")
    long_width = last_bubble(chat3).width()
    assert long_width == limit, (long_width, limit)
    chat3.append_assistant("短")
    short_width = last_bubble(chat3).width()
    assert short_width < limit, short_width
    # 短句不许被挤成两行（「飞八分钱」那种算得刚好等于字宽，Qt 会四舍五入到换行）
    chat3.append_assistant("飞八分钱")
    app.processEvents()
    tiny = last_bubble(chat3)
    assert tiny.height() <= 46, ("短句被挤成两行", tiny.width(), tiny.height())
    # 用户 2026-10-24 截图：「你呀，怎么还问这个。」断成「……问这 / 个。」。
    # 旧算法用 boundingRect 量（墨迹框比排版宽度窄 9px），还按 10pt 量、11pt 画。
    # 这两条是九字和十二字，正好卡在会掉字的长度上。
    for text in ("你呀，怎么还问这个。", "今天有点累，先躺一会儿。"):
        chat3.append_assistant(text)
        app.processEvents()
        one = last_bubble(chat3)
        assert one.width() < limit, (text, one.width(), limit)
        assert one.height() <= 46, ("短句被挤成两行", text, one.width(), one.height())
    # 多行气泡不许被裁掉（内边距走布局，多行只该长高，不该切字）
    chat3.append_assistant("不知道它说了什么\n永远不会忘记\n为了赔偿过来了\n腹黑兔子装作什么都不知道\n结果她得赔多少钱？")
    app.processEvents()
    multi = last_bubble(chat3)
    assert multi.height() > 70, multi.height()
    assert multi.label.height() >= multi.label.heightForWidth(multi.label.width()), (
        "多行气泡被裁了", multi.label.height(),
        multi.label.heightForWidth(multi.label.width()))
    # 记录区被吞掉时要能从数据重画回来（用户报过「只显示最新一句」）
    while chat3._rows.count():
        item = chat3._rows.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
    chat3._push("assistant", "重画一次")
    assert "我发的这句不能丢" in chat3.text(), "记录区没从数据重画"

    # 输入框右键菜单要中文、要跟窗口一套样式（用户截图里是英文 Undo/Cut/Paste）
    menu = chat3.input._menu()
    labels = [a.text() for a in menu.actions() if a.text()]
    assert labels == ["撤销", "重做", "剪切", "复制", "粘贴", "删除", "全选"], labels
    assert "QMenu" in menu.styleSheet() and theme.PRIMARY in menu.styleSheet(), "右键菜单没套主题"
    empty_input = chat_ui._Input()
    assert not empty_input._menu().actions()[0].isEnabled(), "没退过就不该能撤销"
    assert not empty_input._menu().actions()[-1].isEnabled(), "没有字不该能全选"
    empty_input.deleteLater()

    # 点她不能老说同一句：旁白要几个角度随机挑；正经活（做题/算数）要拦
    assert len(brain.ASKS["click"]) >= 4, "click 的旁白太单一"
    assert len(brain.ASKS["active"]) >= 3, "active 的旁白太单一"
    assert brain._pick_ask("click") in brain.ASKS["click"]
    # 2026-10-24 用户要功能性，但方式是聊天窗的「工作模式」开关：默认还是装傻，
    # 勾上才放开（提示词原文见 brain.WORK_MODE）
    # 2026-10-24 用户拍板：开关没用（等于没开），改成常驻——正经问题老实答，
    # 只在逗她玩的时候装傻；提示词因此压在 RULES 第 11 条里
    # 2026-10-25 第二十九批：用户的新口径是「不可能一问三不知，也不可能全知全能，
    # 答得上就用自己的话说，答不上就把话头带过去」，并点名别用「这是什么能吃吗」
    # 「我不知道」复读；第 11 条整条重写，断言跟着换
    for must in ("用你自己的话说出来", "别背课文", "别列点", "别硬编", "把话头带过去"):
        assert must in brain.RULES, "RULES 里缺「%s」" % must
    assert "别真去算" not in brain.RULES, "又在拦正经活了"
    # 2026-10-25 用户拍板：撒娇时尾音可以拖长，但绝不许定型成固定尾巴
    assert "拖长" in brain.RULES and "同一个尾巴" in brain.RULES, "口癖那条被改坏了"
    # 用户还说「不许做动作心理描写，翅膀外形就少主动提」——第 10 条得管到翅膀外形
    assert "翅膀（长什么样、能不能飞）" in brain.RULES, "翅膀外形的频率没压住"
    assert not hasattr(brain, "WORK_MODE"), "WORK_MODE 该删干净了"
    # 回车只能发送：「清空」一旦当上 QDialog 默认按钮，一次回车会把刚发的记录也清掉
    # （2026-10-24 用户「只显示最新一句」的真根因）
    assert not chat3.clear_btn.autoDefault(), "「清空」会抢回车"
    assert not chat3.clear_btn.isDefault(), "「清空」又成默认按钮了"
    assert chat3.clear_btn.focusPolicy() == Qt.NoFocus, "「清空」能被键盘摸到"
    assert not chat3.send_btn.autoDefault(), "「发送」也会抢回车"
    # 所有窗口的图标都得是 贴图\icon.ico（用户 2026-10-24：「所有窗口的图标都换上icon」）
    assert not QApplication.instance().windowIcon().isNull(), "程序的窗口图标是空的"
    assert not chat3.windowIcon().isNull(), "聊天窗没有图标"
    assert chat_ui.theme.FONT_SIZE["chat"] < chat_ui.theme.FONT_SIZE["label"], "聊天字号没比正文小"
    chat3.close()
    pet._reset_chat_history()

    # 温度这种浮点也要落盘，别写回字符串
    assert abs(saved["llm"]["temperature"] - 0.7) < 1e-6, saved["llm"]["temperature"]
    # 2026-10-24：温度调到 2.0 会让 deepseek-chat 整段胡言乱语（用户截图），
    # 所以设置页封顶 1.5，net 发请求前再夹一次（老 settings.json 存着 2.0 也不放过去）
    assert net_mod.MAX_TEMPERATURE == 1.5, net_mod.MAX_TEMPERATURE
    assert sdlg.llm_temp.maximum() == 1.5, sdlg.llm_temp.maximum()
    import inspect as _insp
    assert "MAX_TEMPERATURE" in _insp.getsource(net_mod.Net._request), "net 没夹温度"

    # 23. 收藏（赠礼）真的能收下：名字是「芙兰的收藏」、文件真搬进去、重名不覆盖、
    #     文件夹也能整只收、老「收藏」目录会被搬过来、打开文件夹的那条路有兜底。
    # （2026-10-24 用户：「收藏文件夹打不开，以及检查一下收藏功能是否能行」）
    assert config.COLLECT_DIR.name == "芙兰的收藏", config.COLLECT_DIR
    saved_dm = (data_manager.OLD_COLLECT_DIR, data_manager.COLLECT_DIR)
    real_collect = config.COLLECT_DIR
    gift_dir = tmp_dir / "芙兰的收藏"
    try:
        data_manager.OLD_COLLECT_DIR = tmp_dir / "收藏"
        data_manager.COLLECT_DIR = gift_dir
        # 前面几段可能已经 ensure_dirs() 建过「芙兰的收藏」，先清掉，
        # 不然迁移那一步因为新目录已存在而跳过，这条断言就随机红
        shutil.rmtree(gift_dir, ignore_errors=True)
        old_dir = tmp_dir / "收藏"
        old_dir.mkdir(parents=True, exist_ok=True)
        (old_dir / "旧礼物.txt").write_text("还在", encoding="utf-8")
        data_manager.ensure_dirs()
        assert not old_dir.exists(), "老的「收藏」目录没搬走"
        assert (gift_dir / "旧礼物.txt").read_text(encoding="utf-8") == "还在", \
            "老收藏夹里的东西丢了"

        config.COLLECT_DIR = gift_dir
        src = tmp_dir / "送她的礼物.txt"
        src.write_text("给芙兰的", encoding="utf-8")
        ok, why = pet._move_into_collect(src)
        assert ok, why
        assert not src.exists(), "赠礼只复制没删源，成了复制粘贴"
        assert (gift_dir / "送她的礼物.txt").read_text(encoding="utf-8") == "给芙兰的"

        # 重名的再送一次：另起 _1，不许把上一份盖掉
        src.write_text("第二份", encoding="utf-8")
        ok, why = pet._move_into_collect(src)
        assert ok, why
        assert (gift_dir / "送她的礼物_1.txt").exists(), "重名赠礼覆盖了上一份"

        # 文件夹也得能整只搬进去（拖文件夹是允许的）
        sub = tmp_dir / "一整个文件夹"
        (sub / "内层").mkdir(parents=True, exist_ok=True)
        (sub / "内层" / "a.txt").write_text("x", encoding="utf-8")
        ok, why = pet._move_into_collect(sub)
        assert ok, why
        assert (gift_dir / "一整个文件夹" / "内层" / "a.txt").exists(), "文件夹没搬全"
        assert not sub.exists(), "文件夹赠礼没删源"
    finally:
        config.COLLECT_DIR = real_collect
        data_manager.OLD_COLLECT_DIR, data_manager.COLLECT_DIR = saved_dm

    # 「打开收藏文件夹」不能只有 os.startfile：低权限下它会抛 WinError 5，
    # 窗口程序没控制台 → 用户看到的就是「点了没反应」。要留 explorer / 抄路径兜底。
    import inspect
    opener = inspect.getsource(PetWindow._menu_open_collect)
    assert "os.startfile" in opener and "explorer.exe" in opener, "打开收藏夹没兜底"
    assert "clipboard" in opener, "叫不开文件夹时得把路径抄给用户"

    # 24. 桌面感知（Activity）：没桌面也不崩、同一程序只开口一次、每日上限、全屏躲着时闭嘴
    #     （第二十三批：用户要「打游戏夸操作、干活监工、连着忙 50 分钟催休息」）
    import activity as activity_mod                     # noqa: E402

    # 构造 / 采样 / 开关：offscreen 下什么都不许抛
    probe_act = activity_mod.Activity()
    assert probe_act.is_running() is False, "Activity 默认就该是关着的"
    probe_act.tick()                                    # 没 start：一次都不采
    probe_act.start()
    probe_act.tick()
    assert isinstance(activity_mod.idle_seconds(), float)
    app_name, win_title = activity_mod.foreground()
    assert isinstance(app_name, str) and isinstance(win_title, str)
    assert len(win_title) <= config.ACTIVITY_TITLE_MAX, win_title
    assert probe_act.current[0] == app_name, "采到的程序名没记下来"
    probe_act.stop()
    assert probe_act.is_running() is False

    # 「手感」三样：是不是全屏、这个程序待了多久、这半分钟在不在动键鼠
    assert "窗口" in probe_act.feel(), probe_act.feel()
    assert "全屏" in probe_act.feel(True), probe_act.feel(True)
    probe_act._app_since = time.monotonic() - 185
    assert "3 分钟" in probe_act.feel(), probe_act.feel()
    probe_act._motion.clear()
    probe_act._motion.extend([True] * 10)
    assert "一直在动" in probe_act.feel(), probe_act.feel()
    probe_act._motion.clear()
    probe_act._motion.extend([False] * 10)
    assert "没怎么动" in probe_act.feel(), probe_act.feel()

    # 程序名翻人话 + 后台窗口列表（只读标题/进程名，拿不到就该是空表而不是崩）
    assert "画画" in activity_mod.pretty("sai.exe"), activity_mod.pretty("sai.exe")
    assert activity_mod.pretty("没听说过的.exe") == "没听说过的.exe"
    wins = activity_mod.windows()
    assert isinstance(wins, list) and len(wins) <= 8, wins
    assert all(len(t) == 2 and t[0] and isinstance(t[1], str) for t in wins), wins
    assert isinstance(probe_act.background(), str)

    # 总开关：关了不采样，开了才采（设置页一按 Saving 就得生效，不用重启）
    pet.show()
    app.processEvents()
    pet._fullscreen_hidden = False
    pet.settings["watch"] = {"enabled": False, "cooldown_s": 600,
                             "daily_cap": 100, "hide_in_fullscreen": False}
    pet._watch_sync()
    assert not pet.activity.is_running(), "总开关关着，Activity 还在采样"
    pet.settings["watch"]["enabled"] = True
    pet._watch_sync()
    assert pet.activity.is_running(), "总开关开着，Activity 没开始采样"

    # 全屏躲起来必须「连着两次都全屏」才躲：输入法候选 / 覆盖层抢一次前台不该让她消失
    real_fs = pet._foreground_fullscreen
    pet.settings["watch"]["hide_in_fullscreen"] = True
    pet._foreground_fullscreen = lambda: True
    pet._fs_hits = 0
    pet._fs_active = False
    pet._fullscreen_hidden = False
    pet.show()
    app.processEvents()
    pet._check_fullscreen()
    assert pet.isVisible() and not pet._fullscreen_hidden, "只判定到一次全屏就躲起来了"
    pet._check_fullscreen()
    assert pet._fullscreen_hidden and not pet.isVisible(), "连着两次全屏却没躲"
    pet._foreground_fullscreen = lambda: False
    pet._check_fullscreen()
    assert pet.isVisible() and not pet._fullscreen_hidden, "退出全屏之后没回来"
    pet._foreground_fullscreen = real_fs
    pet._fs_hits = 0
    pet.settings["watch"]["hide_in_fullscreen"] = False
    # 中文输入法的宿主窗口（TextInputHost）就长这样：铺满全屏、没标题栏，必须排掉
    assert "Windows.UI.Core.CoreWindow" in activity_mod.SHELL_CLASSES, "输入法宿主没排掉"
    assert activity_mod.overlay(0) is False

    today = time.strftime("%Y-%m-%d")

    def _fresh_usage(n=0):
        data_manager.save_chat_history(
            {"messages": [], "usage": ({today: n} if n else {}), "last_date": today})

    watch_sent = []
    pet.net.chat = lambda m, kind="chat": (watch_sent.append((kind, m)), None)
    brain.reset_throttle()
    _fresh_usage()
    pet._ai_busy = False
    pet._idle_back_pending = False
    pet._streak_at = -1e9
    for _ in range(3):
        pet._ai_busy = False
        pet._on_activity_changed("GenshinImpact.exe", "原神")
    assert len(watch_sent) == 1, "同一个程序连发 3 次，开了 %d 次口" % len(watch_sent)
    kind, sent_msgs = watch_sent[0]
    assert kind == "active", kind
    # 打游戏还是干活不在这儿判断：程序名 + 标题原样塞给模型，让它自己说
    assert "原神" in sent_msgs[0]["content"], "提示词里没有窗口标题"
    assert "GenshinImpact.exe" in sent_msgs[0]["content"], "提示词里没有程序名"
    assert "窗口" in sent_msgs[0]["content"], "提示词里没有「手感」那几句"

    # 聊天窗也要看得见：带上程序名 + 手感；关了总开关就明确「别猜屏幕内容」
    pet.activity.current
    app_now, screen_now = pet.watch_screen()
    assert app_now and "窗口" in screen_now, screen_now
    chat_msgs = brain.build_messages(
        "chat", pet.chat_ctx([{"role": "user", "content": "在吗"}]))
    assert app_now in chat_msgs[0]["content"], "聊天里没带上程序名"
    pet.settings["watch"]["enabled"] = False
    assert pet.watch_screen() == ("", "")
    assert "screen" not in pet.chat_ctx([]), "总开关关着还把屏幕塞进聊天了"
    off_msgs = brain.build_messages("chat", pet.chat_ctx([]))
    assert "别猜他屏幕上有什么" in off_msgs[0]["content"], "关了开关还在瞎猜屏幕"
    pet.settings["watch"]["enabled"] = True

    # 每日上限：今天已经说满 100 句就不再开这个口
    watch_sent.clear()
    brain.reset_throttle()
    _fresh_usage(100)
    pet._ai_busy = False
    pet._on_activity_changed("Code.exe", "main.py - Visual Studio Code")
    assert not watch_sent, "每日上限到了还在开口"

    # 全屏躲起来了：不发请求
    watch_sent.clear()
    brain.reset_throttle()
    _fresh_usage()
    pet._fullscreen_hidden = True
    pet._ai_busy = False
    pet._on_activity_changed("WINWORD.EXE", "文档1 - Word")
    pet._on_idle_started(600)
    pet._on_active_streak(50)
    assert not watch_sent, "全屏躲起来了还在发请求"
    pet._fullscreen_hidden = False

    # 连着忙满 50 分钟：催休息。这条不受每日上限限制，但同类 30 分钟冷却要挡住
    watch_sent.clear()
    _fresh_usage(999)
    pet._ai_busy = False
    pet._streak_at = -1e9
    pet._on_active_streak(50)
    assert len(watch_sent) == 1, "催休息被每日上限挡住了"
    pet._ai_busy = False
    pet._on_active_streak(50)
    assert len(watch_sent) == 1, "催休息的 30 分钟冷却没生效"

    # 走开又回来：「你回来了」说一次，一小时内不重复
    watch_sent.clear()
    brain.reset_throttle()
    _fresh_usage()
    pet._ai_busy = False
    pet._back_at = -1e9
    pet._idle_back_pending = False
    pet._on_idle_started(600)
    assert pet._idle_back_pending, "人走开之后没记下「等你回来」"
    pet._on_activity_changed("explorer.exe", "文件资源管理器")
    assert len(watch_sent) == 1, "回来了却没吭声"
    pet._ai_busy = False
    pet._on_idle_started(600)
    pet._on_activity_changed("explorer.exe", "文件资源管理器")
    assert len(watch_sent) == 1, "「你回来了」一小时内说了两次"

    pet.net.chat = real_chat
    pet._ai_busy = False
    pet._reset_chat_history()

    # 25. 语音（按住说话键说话）：没麦克风也不崩、没模型时热键是空操作、说话键能带组合键、
    #     按住→松开→转文字→用同一个气泡显示（不弹聊天窗）→她回一句（FLANDRE_VOICE_MOCK=1）
    assert voice_mod.parse_hotkey("F8") == ((), 0x77), voice_mod.parse_hotkey("F8")
    mods, vk = voice_mod.parse_hotkey("Ctrl+Shift")
    assert vk == 0 and set(mods) == {0x11, 0x10}, (mods, vk)
    mods, vk = voice_mod.parse_hotkey("Ctrl+Shift+F9")
    assert vk == 0x78 and set(mods) == {0x11, 0x10}, (mods, vk)
    assert voice_mod.parse_hotkey("F13") is None, "不认识的键名也该被拒"
    assert voice_mod.parse_hotkey("") is None

    # 说话键按钮：点一下进入录制，按什么锁什么（组合键也认）
    hk = settings_dialog._HotkeyButton("F8")
    hk._start()
    hk.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_F9,
                               Qt.ControlModifier | Qt.ShiftModifier))
    assert hk.hotkey() == "Ctrl+Shift+F9", hk.hotkey()
    hk._start()
    hk.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert hk.hotkey() == "Ctrl+Shift+F9", "Esc 没取消掉录制"
    hk.deleteLater()

    v0 = voice_mod.Voice()
    has_local = voice_mod.local_files() is not None
    v0.configure({})
    assert not v0.listening(), "什么都没配就开始听热键了"
    v0.press()
    v0.release()                         # 空操作：一个信号都不该发
    v0.set_hwnd(0)
    v0.configure({"enabled": True, "hotkey": "F8"})
    assert not v0._claimed, "没有窗口句柄也去系统里占键了"
    # 本地识别：有模型就该听，一个地址都不用填
    assert v0.listening() == has_local, "本地模型没被认出来"
    v0.configure({"enabled": True, "hotkey": "F13"})
    assert not v0.listening(), "不认识的键名也开听了"
    v0.configure({"enabled": True, "hotkey": "Ctrl+Shift+F9"})
    assert v0.listening() == has_local, "组合键没被认出来"

    # 键盘钩子给的是左右分开的码（A2 左 Ctrl / A0 左 Shift），必须换算成 11/10，
    # 不然「Ctrl+Shift」这种纯修饰键组合永远等不到按下 —— 第二十七批就是这么整批失灵的
    def _feed(vk, down):
        kb = voice_mod._KbdllHook()
        kb.vkCode = vk
        vk_event = voice_mod.WM_KEYDOWN if down else voice_mod.WM_KEYUP
        v0._hook_key(0, vk_event, ctypes.addressof(kb))

    hook_thread = v0._hook_thread        # 下面那行 configure 会把这个引用丢掉，先留住
    v0.configure({"enabled": False, "hotkey": "Ctrl+Shift"})  # 别真开轮询/装钩子，只验换算
    if hook_thread is not None:
        # 真钩子线程退出消息循环时还会把 _hooked / _key_down 清一遍（voice.py:508-509）。
        # 不等它退干净就往下喂键，偶尔会卡在「左 Ctrl + 左 Shift 没认出来」那条断言
        # 上——第二十九批整批复现过，所以这里必须等，别删。
        hook_thread.join(2.0)
    v0._hooked = True
    assert not v0._down(v0._vk()), "什么都没按就说按着"
    _feed(0xA2, True)
    assert not v0._down(v0._vk()), "只按 Ctrl 就算按住了组合键"
    _feed(0xA0, True)
    assert v0._down(v0._vk()), "左 Ctrl + 左 Shift 没认出来"
    _feed(0xA0, False)
    assert not v0._down(v0._vk()), "松开 Shift 还说按着"
    _feed(0xA3, True)
    assert not v0._down(v0._vk()), "松开 Shift 之后只剩 Ctrl，不该算按住"
    _feed(0xA2, False)
    _feed(0xA3, False)
    assert not v0._down(v0._vk()), "全松开还说按着"
    v0._hooked = False
    v0.deleteLater()
    # 本地识别：模型在就真跑一遍（1 秒静音，只要求不崩、返回的是字符串）
    wav_probe = tmp_dir / "_local_probe.wav"
    wav_probe.write_bytes(
        voice_mod._wav_bytes(b"\x00\x00" * config.VOICE_SAMPLE_RATE))
    if has_local:
        assert voice_mod.local_recognizer() is not None, "本地模型加载不出来"
        text_probe, err_probe = voice_mod._transcribe_local(wav_probe)
        assert isinstance(text_probe, str) and isinstance(err_probe, str), \
            (text_probe, err_probe)
    else:
        assert voice_mod.local_recognizer() is None, "没有模型却返回了识别器"
        assert voice_mod._transcribe_local(wav_probe) == ("", "stt"), \
            "没有模型时本地识别没老实报错"
    assert voice_mod.stt_endpoint("https://x.cn/v1/") == \
        "https://x.cn/v1/audio/transcriptions"
    assert voice_mod.stt_endpoint("https://x.cn/v1/audio/transcriptions") == \
        "https://x.cn/v1/audio/transcriptions"

    os.environ[voice_mod.MOCK_ENV] = "1"
    pet.settings["voice"] = {"enabled": True, "hotkey": "F8"}
    pet.settings["llm"].update({"enabled": True, "api_key": "sk-test"})
    pet._voice_sync()
    assert pet.voice.listening(), "配齐了还不听热键"

    said.clear()
    pet._set_state(S.STAND)
    pet._ai_busy = False
    assert len(list(config.VOICE_SPIN_DIR.glob("*.png"))) == 12, "头顶转圈贴图不是 12 张"
    pet.voice.press()
    assert pet._voice_busy, "按下热键没进「在听」状态"
    assert pet._spin_on, "按下热键头顶没开始转圈"
    assert pet._bounce_frame == "stand5", "按下热键没闭眼"
    assert pet._spin_timer.isActive(), "转圈定时器没起来"
    assert len(pet._spin_frames) == 12, len(pet._spin_frames)
    step0 = pet._spin_step
    pet._spin_tick()
    assert pet._spin_step == (step0 + 1) % 12, "转圈没走帧"
    pet.voice.release()                  # mock：录一段 16k 单声道静音，识别直接给一句假的
    assert pet._voice_busy and pet._spin_on, "松开就停了，还没等到回答"
    wav_path = data_manager.DATA_DIR / "_voice_tmp.wav"
    assert wav_path.exists(), "录音文件没落地"
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getnchannels() == 1, wf.getnchannels()
        assert wf.getframerate() == 16000, wf.getframerate()
        assert wf.getnframes() > 0, "录了个空文件"
    # 主人说的话：进气泡（标题写他的昵称），不弹聊天窗
    assert pet._dlgs.get("chat") is None, "语音输入不该自己把聊天窗开出来"
    assert pet.bubble.isVisible(), "主人说的话没显示在气泡里"
    assert pet.bubble.title.text() == (pet.settings.get("nickname") or "你"), \
        pet.bubble.title.text()
    assert voice_mod.MOCK_TEXT in pet.bubble.label.text(), pet.bubble.label.text()
    assert pet._voice_guard.isActive(), "等回答时没起兜底计时（会被挤掉就永远转圈）"
    _wait_ai()
    msgs = data_manager.load_chat_history()["messages"]
    assert [m["role"] for m in msgs[-2:]] == ["user", "assistant"], msgs
    assert msgs[-2]["content"] == voice_mod.MOCK_TEXT, msgs[-2]
    assert msgs[-1]["content"] == net_mod.MOCK_TEXT, msgs[-1]
    # 她的回答：同一个气泡换内容，标题回到她的名字
    assert pet.bubble.title.text() == bubble.WHO_DEFAULT, pet.bubble.title.text()
    assert net_mod.MOCK_TEXT in pet.bubble.label.text(), pet.bubble.label.text()
    assert said and said[-1][0] == net_mod.MOCK_TEXT, said[-1:]
    assert not pet._voice_busy, "回答回来了还没收尾"
    assert not pet._voice_guard.isActive(), "回答回来了兜底计时还在跑"
    assert not pet._spin_on and not pet._spin_timer.isActive(), "回答回来了还在转圈"
    assert pet._bounce_frame == "" and pet._bounce_until == 0.0, \
        "回答回来了还闭着眼（该当场睁眼、不再多闭半秒）"

    # 聊天窗开着时说的：记录要进窗（打开聊天框照样能翻到语音说的那句）
    chat5 = chat_ui.ChatWindow(pet)
    pet._dlgs["chat"] = chat5
    try:
        said.clear()
        pet.voice.press()
        pet.voice.release()
        assert voice_mod.MOCK_TEXT in chat5.text(), chat5.text()
        _wait_ai()
        assert net_mod.MOCK_TEXT in chat5.text(), chat5.text()
        # 看这个窗口自己那份记录（历史文件是「谁最后写算谁的」，多个窗口各自持有一份，
        # 拿文件断言会被别的窗口晚一步的写入搅乱 —— 那是本来就有的事，不是这一轮引入的）
        msgs = chat5._history["messages"]
        assert [m["role"] for m in msgs[-2:]] == ["user", "assistant"], msgs[-4:]
        assert msgs[-2]["content"] == voice_mod.MOCK_TEXT, msgs[-2]
        tail = data_manager.load_chat_history()["messages"]
        assert any(m["content"] == voice_mod.MOCK_TEXT for m in tail), "语音说的那句没落盘"
    finally:
        pet._dlgs.pop("chat", None)
        chat5.close()
        chat5.deleteLater()

    # 没听清：借请求失败那句播报，60 秒内只提示一次
    said.clear()
    plays2 = []
    real_play2 = sound_mod.play
    sound_mod.play = lambda name: plays2.append(name)
    pet._ai_err_until = 0.0
    pet._set_state(S.STAND)
    for _ in range(3):
        pet._on_voice_failed("net")
    sound_mod.play = real_play2
    assert len(said) == 1, "语音失败 60 秒冷却没生效：%d 次" % len(said)
    assert "没听清" in said[0][0], said[0][0]
    assert plays2.count("error.wav") == 1, plays2

    # 402 余额不足也得认出来（在线那条路虽然从界面撤了，错误码不能退化成「没听清」）
    assert net_mod._http_error(402) == "billing", net_mod._http_error(402)
    assert net_mod._http_error(401) == "auth"

    # 20 秒还没回来：自己睁眼、停转圈，只吭一句「没听清」
    said.clear()
    pet._ai_err_until = 0.0
    pet._set_state(S.STAND)
    pet._voice_listening(True)
    assert pet._voice_busy and pet._spin_on, "等回答时没闭眼/没转圈"
    pet._on_ai_done("voice", "", "timeout")
    assert not pet._voice_busy, "超时了还没收尾"
    assert not pet._spin_on and not pet._spin_timer.isActive(), "超时了还在转圈"
    assert len(said) == 1 and "没听清" in said[0][0], said

    # 太短（不到 0.6 秒）当误触：不吭声、也不发请求，只把闭眼和转圈收掉
    real_mock_wav = pet.voice._mock_wav
    heard2 = []
    said.clear()
    pet.voice.heard.connect(heard2.append)
    pet.voice._mock_wav = lambda: (real_mock_wav()[0], config.VOICE_MIN_SECONDS / 2)
    pet.voice.press()
    assert pet._voice_busy and pet._spin_on, "误触那次没进「在听」"
    pet.voice.release()
    pet.voice._mock_wav = real_mock_wav
    assert not heard2, "0.3 秒的误触也当成一句话往上发了"
    assert not said, "误触还吭声了"
    assert not pet._voice_busy and not pet._spin_on, "误触之后没睁眼/没停转圈"

    # 关掉开关：立刻不听（设置页一保存就生效，不用重启）
    said.clear()
    pet.settings["voice"] = dict(data_manager.DEFAULT_SETTINGS.get("voice") or {})
    pet._voice_sync()
    assert not pet.voice.listening(), "关掉开关还在听热键"
    pet.voice.press()
    pet.voice.release()
    assert not said, "关掉开关之后还冒出提示"
    os.environ.pop(voice_mod.MOCK_ENV, None)

    # 第二十四段：气泡宽度跟着窗口走（用户报「气泡也跟着收缩」）
    w = chat_ui.ChatWindow(pet)
    w.show()
    app.processEvents()
    w.resize(470, 520)
    app.processEvents()
    narrow_limit = w._bubble_limit()
    w.resize(700, 560)
    app.processEvents()
    wide_limit = w._bubble_limit()
    assert wide_limit > narrow_limit, (narrow_limit, wide_limit)
    assert w.size().width() >= 470, w.size().width()
    assert not hasattr(w, "work"), "限制解除开关撤了还留着属性"
    w.close()

    print("SELFCHECK OK - 界面自检全部通过")
    del app
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
