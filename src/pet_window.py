# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

import math
import random
import re
import time
from enum import IntEnum

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QImage, QPixmap, QRegion, QPainter
from PySide6.QtWidgets import QWidget, QMenu, QApplication, QDialog
from PIL import Image

import brain
import config
import dialogue
import sound
import theme
from activity import Activity, SHELL_CLASSES, overlay, pretty
from bubble import SpeechBubble
from data_manager import (load_chat_history, load_settings, save_chat_history,
                          save_settings)
from timers import Pomodoro, Countdown
from hourly import HourlyReporter
from net import Net
from voice import Voice


class S(IntEnum):
    STAND = 0
    RUN = 1
    PICKED = 2
    FALL = 3
    REST = 4
    WALK = 5


def _pil_to_qpixmap(img):
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


_ALPHA_RUN = re.compile(rb"[^\x00]+")        # alpha 连续的可见段


def _pil_alpha_to_region(img, pad=0):
    # 由 alpha 通道构建点击遮罩（alpha>0 的像素算可点击）
    # pad：每行向左右各放宽几个像素，给压扁回弹（横向 1.05）和颤抖留余量，
    # 否则那几像素会被窗口遮罩切掉，看起来像贴图边缘破了个口子。
    # 用正则找连续的 alpha>0 段（C 速度），比逐像素 Python 循环快 ~5 倍，启动少等约 0.2 秒
    alpha = img.getchannel("A").tobytes()
    w = img.width
    region = QRegion()
    for m in _ALPHA_RUN.finditer(alpha):
        start, end = m.start(), m.end()
        while start < end:                       # 一段可能跨行，拆成每行一条
            y, x = divmod(start, w)
            n = min(end - start, w - x)
            x0 = max(0, x - pad)
            region += QRegion(x0, y, min(w, x + n + pad) - x0, 1)
            start += n
    return region


def _offset_frame(img, dx, dy):
    # 平移贴图内容（超出画布的部分被裁掉，空出来的部分保持透明）
    if not dx and not dy:
        return img
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


def _load_frame(path, size, dpr, mirrored=False, dx=0, dy=0, pad=None):
    # pad 默认按配置的压扁余量放宽遮罩；传 0 可以要精确遮罩
    if pad is None:
        pad = config.SQUASH_MASK_PAD
    src = Image.open(str(path)).convert("RGBA")
    if mirrored:
        src = src.transpose(Image.FLIP_LEFT_RIGHT)
        dx = -dx                   # 镜像后「右移」在画布上要反过来才视觉一致
    # 高清渲染：PIL LANCZOS 高质量缩放，按 DPR 到物理分辨率，边缘更平滑
    # 在「预乘 alpha」空间里缩放：贴图的透明像素 RGB 是白的，直通缩放会把白色
    # 渗进轮廓边缘，叠在桌面上就是一圈白毛边，转 RGBa 再转回来就没有了
    phys = max(1, int(round(size * dpr)))
    hi = src.convert("RGBa").resize((phys, phys), Image.LANCZOS).convert("RGBA")
    hi = _offset_frame(hi, int(round(dx * dpr)), int(round(dy * dpr)))
    pix = _pil_to_qpixmap(hi)
    pix.setDevicePixelRatio(dpr)
    # 点击遮罩：逻辑分辨率。直接从已算好的物理图降采样（省一次 1000→240 的 LANCZOS，
    # 每个窗口启动少等十几毫秒），轮廓差异在 ±1 像素、遮罩本来就放宽了 pad，看不出来
    lo = hi.resize((size, size), Image.LANCZOS)
    region = _pil_alpha_to_region(lo, pad)
    return pix, region


class PetWindow(QWidget):
    @staticmethod
    def _blink_frame_path():
        # 点击回弹的闭眼差分；老贴图包里没有 5.png 就退化用 1.png，不让程序起不来
        blink = config.STAND_DIR / "5.png"
        return blink if blink.exists() else config.STAND_DIR / "1.png"

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(config.DISPLAY_SIZE, config.DISPLAY_SIZE)

        self._dpr = max(1.0, float(QApplication.primaryScreen().devicePixelRatio()))

        # 帧按需加载：启动只同步解 stand1/stand2/stand5（其余等窗口出来后后台一帧一帧补，
        # 20 帧全解要 0.5 秒，全塞在启动里会明显拖慢 .exe 打开）
        self._frame_specs = {
            "stand1": (config.STAND_DIR / "1.png", {}),
            "stand2": (config.STAND_DIR / "2.png", {}),
            "stand5": (self._blink_frame_path(), {}),
            "run1_L": (config.RUN_DIR / "1.png", {}),
            "run2_L": (config.RUN_DIR / "2.png", {}),
            "run1_R": (config.RUN_DIR / "1.png", {"mirrored": True}),
            "run2_R": (config.RUN_DIR / "2.png", {"mirrored": True}),
            # 被拎起的两帧：整体右移 PICK_FRAME_DX，补偿翅膀锚点的视觉偏移
            "pick1": (config.PICK_DIR / "1.png", {"dx": config.PICK_FRAME_DX}),
            "pick2": (config.PICK_DIR / "2.png", {"dx": config.PICK_FRAME_DX}),
            # 表情帧（站立 3=生气 / 4=星星眼开心 / 6=冷脸流汗），只在对话语气或事件触发时使用
            "angry": (config.STAND_DIR / "3.png", {}),
            "happy": (config.STAND_DIR / "4.png", {}),
            "sweat": (config.STAND_DIR / "6.png", {}),
            # 坠落三帧：放下后下坠(3) → 快接触任务栏(4) → 摔到地上(5)
            # 三帧默认朝左，向右甩出时整段镜像
            "fall1_L": (config.PICK_DIR / "3.png", {}),
            "fall2_L": (config.PICK_DIR / "4.png", {}),
            "land_L": (config.PICK_DIR / "5.png", {}),
            "fall1_R": (config.PICK_DIR / "3.png", {"mirrored": True}),
            "fall2_R": (config.PICK_DIR / "4.png", {"mirrored": True}),
            "land_R": (config.PICK_DIR / "5.png", {"mirrored": True}),
            # 休息（无操作打盹）：2.png = 闭眼打盹，1.png = 被吵醒的嫌弃脸
            "rest1": (config.REST_DIR / "1.png", {}),
            "rest2": (config.REST_DIR / "2.png", {}),
        }
        self._frames = {}                 # 已解好的帧（键 → (像素图, 点击遮罩)）
        # 只同步解这一帧：窗口一出来就能画。stand2（说话）/stand5（闭眼）排在预热队列最前，
        # 120ms + 60ms 内就补好，比启动时一次解三帧快约 85ms（每帧约 42ms）
        self._frame("stand1")
        self._warm_keys = [k for k in self._frame_specs if k not in self._frames]
        self._cur_frame = None
        self._cur_pix = None
        self._cur_region = None
        self._cur_img = None              # 当前帧的物理像素图（压扁时逐行拷，避免重采样）

        # 状态
        self.state = S.STAND
        self.direction = -1  # -1 左 / +1 右
        self.state_started = time.monotonic()
        self.run_duration = 0.0
        self.walk_duration = 0.0
        self._rest_pending_at = 0.0   # 空闲到点但还在跑/走：等满宽限期再坐下打盹
        self._rest_woken = False      # 打盹中被点醒（说话期间用 休息\1.png）
        self._rest_wake_count = 0     # 这一觉被点醒了几次（够 REST_WAKE_LIMIT 次就直接起身）
        self._rest_wake_bubble = False  # 当前气泡是「被点醒的不满」，不受计时器守卫影响，必须自动收

        # 地面（主显示器工作区，即任务栏顶端，加下移补偿消除悬空感）
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.ground_y = geo.bottom() + config.GROUND_OFFSET
        self.left_bound = geo.left()
        self.right_bound = geo.right() - config.DISPLAY_SIZE

        self._x = (geo.left() + geo.right() - config.DISPLAY_SIZE) // 2
        self._y = self.ground_y - config.DISPLAY_SIZE
        self.move(self._x, self._y)

        # 交互状态
        self.talking = False
        self.talk_until = 0.0
        self.expression = ""          # 当前表情帧（angry / happy），空串表示无
        self.expression_until = 0.0
        # 计时器专用心情（"happy" 完成 = 站立 4.png / "unhappy" 暂停 = 站立 3.png）
        self.timer_mood = ""
        self.timer_mood_until = 0.0
        self.last_interaction = time.monotonic()
        self._click_times = []        # 频繁点击的时间戳列表（见 CLICK_ANNOY_*）

        # 点击回弹：按下压扁（换站立\5.png 闭眼差分）+ 按住颤抖 + 松开弹回
        self._squash = 0.0            # 0=原样，1=压到最扁（>1 是按下时的过冲）
        self._pressing = False        # 左键按住中（决定要不要颤抖）
        self._press_time = 0.0
        self._wobble_dx = 0.0         # 颤抖的水平位移（像素）
        self._bounce_frame = ""       # 回弹期间强制显示的表情帧（"stand5"）
        self._bounce_until = 0.0      # 松开后 5.png 还能留到什么时候
        self._click_consumed = False  # 这次按住已被「长按叫醒」吃掉，松开别再对话
        self._squash_anim = QVariantAnimation(self)
        self._squash_anim.setEasingCurve(QEasingCurve.OutBack)   # 鲸鱼插件同款过冲
        self._squash_anim.valueChanged.connect(self._on_squash_value)
        self._squash_anim.finished.connect(self._on_squash_done)
        self._wobble_timer = QTimer(self)
        self._wobble_timer.setInterval(16)
        self._wobble_timer.timeout.connect(self._on_wobble)
        self._nap_hold_timer = QTimer(self)
        self._nap_hold_timer.setSingleShot(True)
        self._nap_hold_timer.timeout.connect(self._on_nap_hold)

        # 拖拽 / 坠落
        self._press_global = None
        self._dragging = False
        self._snapped = False
        self._fall_speed = 0.0
        self._fall_vx = 0.0
        self._fall_mirror = False     # 坠落三帧是否镜像朝右（松手瞬间定死）
        self._drag_trail = []
        self._landed = False
        self._land_time = 0.0

        # 挣扎（被拎起）速度：相位累加器，支持变间隔不跳帧
        self._struggle_phase = 0.0
        self._struggle_interval = config.STRUGGLE_FAST
        self._struggle_next_roll = 0.0

        # 气泡
        self.bubble = SpeechBubble()
        self.bubble.closed.connect(self._on_bubble_closed)
        self.bubble.option_chosen.connect(self._on_option_chosen)
        self.bubble.moved.connect(self._on_bubble_moved)

        self.tray = None
        self.settings = load_settings()
        self._reset_chat_history()   # 用户要求：重启不留上次的聊天记录
        self._last_tick = time.monotonic()
        self._dlgs = {}              # 非模态窗口（同类只留一个）

        # 接收拖放（赠礼）
        self.setAcceptDrops(True)

        # 功能模块
        self.pomodoro = Pomodoro(self)
        self.countdown = Countdown(self)
        self.hourly = HourlyReporter(self)

        # 标题栏 / 任务栏统一用 贴图\icon.ico（用户 2026-10-24：所有窗口都换上图）
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(theme.app_icon())

        # 在线模式（聊天 / 测连接）。离线时它什么都不做，只是挂着等
        self.net = Net(self)
        self.net.done.connect(self._on_ai_done)

        # 在线模式的「嘴」：单飞（同一时刻只留一句在飞）、连点防抖、失败播报冷却
        self._ai_busy = False
        self._ai_click_at = 0.0
        self._ai_err_until = 0.0

        # 桌面感知（看见你在干什么）：只读窗口标题 / 程序名，不截图。见 activity.py
        self.activity = Activity(self)
        self.activity.activity_changed.connect(self._on_activity_changed)
        self.activity.idle_started.connect(self._on_idle_started)
        self.activity.active_streak.connect(self._on_active_streak)
        self._idle_back_pending = False  # 人走开又回来了：等下一次换程序时补一句
        # 冷却起点用 -1e9：time.monotonic() 在 Windows 上是开机以来的秒数，
        # 刚开机那半小时里拿 0.0 当起点会被当成「刚才才说过」，白白压掉第一次提醒
        self._streak_at = -1e9           # 上次催休息的时刻（同类冷却 30 分钟）
        self._back_at = -1e9             # 上次说「你回来了」的时刻（每小时最多一次）
        self._watch_sync()               # 总开关没开就一次都不采样

        # 语音（按住热键说话 → 转文字 → 当用户输入发给她）。芙兰不出声，只回气泡
        self.voice = Voice(self)
        self.voice.heard.connect(self._on_voice_heard)
        self.voice.failed.connect(self._on_voice_failed)
        self.voice.recording.connect(self._voice_listening)
        self._voice_busy = False         # 这一轮说话还没结束（录音 / 等识别 / 等回答）
        self._spin_on = False            # 头顶转圈是不是在转
        self._spin_step = 0
        self._spin_frames = []           # 第一次用到才读贴图
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(config.VOICE_SPIN_MS)
        self._spin_timer.timeout.connect(self._spin_tick)
        # 等回答的兜底：请求要是被挤掉了（上一个还没回来），没人会来收尾，
        # 转圈就会一直转下去——所以松开之后最多等 VOICE_WAIT_SECONDS。
        self._voice_guard = QTimer(self)
        self._voice_guard.setSingleShot(True)
        self._voice_guard.setInterval(int(config.VOICE_WAIT_SECONDS * 1000))
        self._voice_guard.timeout.connect(lambda: self._on_voice_failed("timeout"))
        self.voice.set_hwnd(int(self.winId()))   # 系统级占键要句柄：别的程序抢不走
        self._voice_sync()               # 没有本地模型就一个字节都不采

        # 全屏检测：借 think 那 1 秒的钟，每 ACTIVITY_TICK_MS 才问一次 Windows，
        # 不额外开定时器（多一个 QTimer 就多一处要收拾的并发）
        self._fs_every = max(1, config.ACTIVITY_TICK_MS // 1000)
        self._fs_ticks = 0
        self._fs_active = False          # 现在是不是「全屏把你藏起来了」的状态
        self._fs_hits = 0                # 连续几次采样都判成全屏（两次才躲）
        self._fullscreen_hidden = False  # 这次全屏是自动躲的（托盘手动显示会清掉）

        # 定时器
        self.tick = QTimer(self)
        self.tick.setInterval(config.TICK_MS)  # 常规约 30fps，坠落时临时提到 60fps
        self.tick.timeout.connect(self._on_tick)
        self.tick.start()

        self.think = QTimer(self)
        self.think.setInterval(1000)
        self.think.timeout.connect(self._on_think)
        self.think.start()

        self.active_talk_timer = QTimer(self)
        self.active_talk_timer.setSingleShot(True)
        self.active_talk_timer.timeout.connect(self._on_active_talk)
        self._schedule_active_talk()

        self._apply_frame("stand1")
        if self._warm_keys:
            QTimer.singleShot(120, self._warm_next)

    # ---------- 工具 ----------
    def _frame(self, key):
        """取帧（像素图, 点击遮罩），没解过就现解一次。"""
        data = self._frames.get(key)
        if data is None:
            path, kw = self._frame_specs[key]
            data = _load_frame(path, config.DISPLAY_SIZE, self._dpr, **kw)
            self._frames[key] = data
        return data

    def _warm_next(self):
        """窗口出来后后台补解剩下的帧：每次事件循环只解一帧，不卡界面。"""
        while self._warm_keys:
            key = self._warm_keys.pop(0)
            if key not in self._frames:
                self._frame(key)
                break
        if self._warm_keys:
            QTimer.singleShot(60, self._warm_next)

    def _deformed(self):
        """当前是否处在压扁/颤抖状态（决定遮罩要不要放宽）。"""
        return abs(self._squash) > 1e-3 or abs(self._wobble_dx) > 1e-3

    def _apply_mask(self, wide=False):
        """贴遮罩：静止时用精确 alpha 轮廓，压扁/颤抖时临时放宽到外接矩形。
        遮罩是按未压扁的形状生成的，压扁后内容整体下移，斜边会落进更窄的行里被切掉
        （实测压到底切掉 306 个轮廓像素 = 用户说的「边缘被吞」）。反正每帧都会擦背景，
        放宽遮罩不会留残影，最多这 0.5 秒里贴图外那圈空白也能点。"""
        if wide or self._deformed() or self._spin_on:
            self.setMask(QRegion(self._cur_region.boundingRect()))
        else:
            self.setMask(self._cur_region)

    def _apply_frame(self, key):
        if key == self._cur_frame:
            return
        self._cur_frame = key
        self._cur_pix, self._cur_region = self._frame(key)
        img = self._cur_pix.toImage()
        img.setDevicePixelRatio(1.0)      # 压扁时按物理像素逐行 1:1 贴，不能再被 dpr 缩放
        self._cur_img = img
        self._apply_mask()
        self.update()

    def _stand_frame(self):
        # 站姿占位：点击回弹的闭眼帧 > 计时器心情 > 对话表情 > 张嘴帧
        if self._blink_active():
            return self._bounce_frame
        now = time.monotonic()
        if self.timer_mood and now < self.timer_mood_until:
            return self.timer_mood
        if self.expression and now < self.expression_until:
            return self.expression
        if self.talking and now < self.talk_until:
            return "stand2"
        return "stand1"

    def set_timer_mood(self, mood, seconds=None):
        """计时器专用表情。

        mood: '' | 'happy'（站立 4.png）| 'unhappy'/'angry'（站立 3.png）。
        seconds 为空时跟随气泡时长（BUBBLE_AUTO_HIDE）；传 0 等价于立刻清除。
        """
        key = {"unhappy": "angry"}.get(mood, mood)
        if key not in self._frame_specs:
            key = ""
        self.timer_mood = key
        if not key:
            self.timer_mood_until = 0.0
            return
        if seconds is None:
            seconds = float(self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))
        seconds = max(0.0, float(seconds))
        self.timer_mood_until = time.monotonic() + seconds

    def show_live(self, text, options=None, mood=""):
        """原地刷新气泡（不重新弹出），供番茄钟 / 倒计时每秒更新使用。"""
        self.talking = True
        dur = float(self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))
        self.talk_until = time.monotonic() + dur
        if mood:
            self.set_timer_mood(mood, seconds=max(dur, config.DONE_MOOD_SECONDS)
                                if mood == "happy" else dur)
        self.bubble.set_live(self._apply_nickname(text), options)
        self.bubble.show()
        self._position_bubble()

    def timer_done_overlay(self):
        """任务完成统一表现：开心表情（站立 4.png）+ tada 音效。"""
        sound.task_done()
        self.set_timer_mood("happy", seconds=config.DONE_MOOD_SECONDS)

    def _route_timer_control(self, reply):
        """气泡按钮以 @ 开头即为计时器指令，返回是否已处理。"""
        if not str(reply or "").startswith("@"):
            return False
        action = str(reply or "").lstrip("@").strip().lower()
        if not action:
            return False
        for obj in (self.pomodoro, self.countdown):
            if obj.is_running():
                obj.on_control(action)
                return True
        return False

    def _timer_busy(self):
        """番茄钟 / 倒计时是否正在运行（运行期间不自动收气泡、也不坐下打盹）。"""
        return self.pomodoro.is_running() or self.countdown.is_running()

    def _set_state(self, state):
        prev = self.state
        self.state = state
        self.state_started = time.monotonic()
        if state == S.RUN:
            self.run_duration = random.uniform(config.RUN_MIN_SECONDS, config.RUN_MAX_SECONDS)
        if state == S.WALK:
            self.walk_duration = random.uniform(config.WALK_MIN_SECONDS, config.WALK_MAX_SECONDS)
        if state == S.PICKED:
            self._struggle_phase = 0.0
            self._struggle_interval = config.STRUGGLE_FAST
            self._struggle_next_roll = 0.0
        if state == S.STAND:
            self._rest_woken = False
        if state == S.REST:
            self._rest_pending_at = 0.0
            self._rest_woken = False
            self._rest_wake_count = 0
        if state == S.FALL:
            self._fall_speed = 0.0
            self._fall_vx = 0.0
            self._fall_mirror = False
            self._landed = False
        # 只有下坠过程提到 60fps，离开坠落立刻恢复常规帧率
        if state == S.FALL:
            self.tick.setInterval(config.FALL_TICK_MS)
        elif prev == S.FALL:
            self.tick.setInterval(config.TICK_MS)
            # 落地时窗口曾整体下移 LAND_OFFSET_PX，离开坠落必须显式复位
            self._landed = False
            self._y = self.ground_y - config.DISPLAY_SIZE
            self.move(int(self._x), int(self._y))

    # ---------- 对话 ----------
    def _set_expression(self, mood):
        """对话/事件触发表情帧：angry(站立3) / happy(站立4) / sweat(站立6)，持续同气泡时长。"""
        key = mood if mood in ("angry", "happy", "sweat") else ""
        if not key or key not in self._frame_specs:
            return
        self.expression = key
        self.expression_until = time.monotonic() + float(
            self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))

    def say(self, text, options=None, mood="", active=False):
        if not text and not options:
            return
        self._rest_wake_bubble = False
        text = self._apply_nickname(text)
        self.talking = True
        dur = float(self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))
        self.talk_until = time.monotonic() + dur
        # 没指定表情就按台词语气猜一个（在线现编和离线预设都走这条路）
        mood = mood or brain.mood_of(text)
        if mood:
            self._set_expression(mood)
        else:
            # 新对话不带表情时收掉上一个表情
            self.expression = ""
            self.expression_until = 0.0
        self.bubble.set_who("")          # 她自己说的话，标题回到她的名字
        self.bubble.show_message(text, options)
        self.bubble.show()
        self.bubble.raise_()
        self._raise_dialogs()
        self._position_bubble()
        # 在线模式下芙兰自己说的话，聊天窗开着就顺手记一笔（功能提示不记）
        if active and self._llm_ready():
            chat = self._dlgs.get("chat")
            if chat is not None and chat.isVisible():
                chat.append_assistant(text, active=True)

    def _say_user(self, text):
        """主人说的话也走同一个气泡（标题写他的昵称），不弹聊天窗。"""
        text = self._apply_nickname(text)
        if not text:
            return
        self._rest_wake_bubble = False
        dur = float(self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))
        self.talk_until = time.monotonic() + dur
        self.expression = ""                 # 主人说的话不该给她挑表情
        self.expression_until = 0.0
        self.bubble.set_who(str(self.settings.get("nickname") or "你"))
        self.bubble.show_message(text)
        self.bubble.show()
        self.bubble.raise_()
        self._raise_dialogs()
        self._position_bubble()

    def _raise_dialogs(self):
        """把开着的功能窗重新抬到最上面。

        气泡每次说话都会 `raise_()`，不压回去就会出现「人物被窗口盖住、气泡却飘在
        窗口上面」的奇观（用户 2026-10-15 报的）。功能窗自己在 setup_dialog 里也
        带了置顶标志，两边配合才是确定的上/下关系：功能窗 > 气泡 > 桌宠。
        """
        for dlg in getattr(self, "_dlgs", {}).values():
            if dlg.isVisible():
                dlg.raise_()

    def _position_bubble(self):
        bsize = self.bubble.size()
        saved = self.settings.get("bubble_offset")
        screen = QApplication.primaryScreen().availableGeometry()
        if saved and isinstance(saved, (list, tuple)) and len(saved) == 2:
            # 用户手动拖拽过气泡：以角色左上角为基准的相对偏移，跟随角色移动
            dx = int(saved[0])
            dy = int(saved[1])
        else:
            # 默认：角色上方、左对齐
            dx = 0
            dy = -(bsize.height() + 8)
        x = self._x + dx
        y = self._y + dy
        x = max(screen.left(), min(x, screen.right() - bsize.width()))
        y = max(screen.top(), min(y, screen.bottom() - bsize.height()))
        self.bubble.move(x, y)

    def _on_bubble_closed(self):
        self.talking = False
        self.talk_until = 0.0
        self.expression = ""
        self.expression_until = 0.0
        self._rest_wake_bubble = False
        if self.state == S.REST and self._rest_woken:
            self._leave_rest()

    def _on_option_chosen(self, reply, mood=""):
        if self._route_timer_control(reply):
            return
        if reply:
            self.say(reply, mood=mood)
        else:
            self._on_bubble_closed()
            if mood:
                self._set_expression(mood)

    def _on_bubble_moved(self, x, y):
        # 保存为相对角色的偏移量，角色移动时气泡会跟随
        self.settings["bubble_offset"] = [x - self._x, y - self._y]
        save_settings(self.settings)

    # ---------- 交互 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._dragging = False
            self._press_fx()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_global is not None and not self._dragging:
            gp = e.globalPosition().toPoint()
            if (gp - self._press_global).manhattanLength() >= config.DRAG_THRESHOLD:
                self._start_pick()
                self._dragging = True
        if self._dragging:
            self._drag_to(e.globalPosition().toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            was_dragging = self._dragging
            snapped = self._snapped
            consumed = self._click_consumed
            self._dragging = False
            self._press_global = None
            self._snapped = False
            self._click_consumed = False
            self._end_bounce()
            if not snapped:
                if was_dragging:
                    self._release_pick()
                elif not consumed and self.state != S.REST:
                    # 打盹中短按只捏一下，不叫醒（按住满 NAP_WAKE_HOLD_MS 才算吵醒）
                    self._on_click()
        super().mouseReleaseEvent(e)

    def _start_pick(self):
        self.last_interaction = time.monotonic()
        self._cancel_bounce()          # 拎起来就不压扁了，交给拎起动画
        self._snapped = False
        self._drag_trail = []
        self._set_state(S.PICKED)
        self.say(dialogue.pick("struggle"))

    def _drag_to(self, global_pos):
        if global_pos.y() > self.ground_y:
            # 鼠标进入任务栏区域：回弹站立 + 生气质问
            if not self._snapped:
                self._snapped = True
                self._dragging = False
                self._press_global = None
                self._cancel_bounce()
                self._y = self.ground_y - config.DISPLAY_SIZE
                self.move(int(self._x), int(self._y))
                self._set_state(S.STAND)
                self.say(dialogue.pick("drag_down"), mood="angry")
            return
        ax = config.WING_ANCHOR[0] * config.SCALE
        ay = config.WING_ANCHOR[1] * config.SCALE
        self._x = global_pos.x() - ax
        self._y = global_pos.y() - ay
        self.move(int(self._x), int(self._y))
        # 记录拖动轨迹，用于松开时计算抛出速度
        now = time.monotonic()
        self._drag_trail.append((now, global_pos.x()))
        cutoff = now - 0.15
        self._drag_trail = [p for p in self._drag_trail if p[0] >= cutoff]

    def _release_pick(self):
        if (self._y + config.DISPLAY_SIZE) < self.ground_y - 10:
            # 松手瞬间的水平抛出速度定死整段坠落的方向（向右甩才镜像朝右）
            vx = self._compute_throw_vx()
            self._set_state(S.FALL)
            self._fall_vx = vx
            self._fall_mirror = vx > config.THROW_MIRROR_MIN_VX
            self.say(dialogue.pick("falling"))
        else:
            # 贴地吸附：回到站立位，避免卡进任务栏
            self._y = self.ground_y - config.DISPLAY_SIZE
            self.move(int(self._x), int(self._y))
            self._set_state(S.STAND)

    def _compute_throw_vx(self):
        # 松开前的水平移动速度，作为抛出惯性
        if len(self._drag_trail) >= 2:
            dt = self._drag_trail[-1][0] - self._drag_trail[0][0]
            if dt > 0.001:
                vx = (self._drag_trail[-1][1] - self._drag_trail[0][1]) / dt
                return max(-1000.0, min(1000.0, vx))
        return 0.0

    def _clicks_annoyed(self):
        """窗口内被反复点击就生气；返回 True 表示这次点击该发火。"""
        now = time.monotonic()
        self._click_times = [t for t in self._click_times
                             if now - t < config.CLICK_ANNOY_WINDOW]
        self._click_times.append(now)
        if len(self._click_times) >= config.CLICK_ANNOY_COUNT:
            self._click_times.clear()
            return True
        return False

    def _on_click(self):
        self.last_interaction = time.monotonic()
        if self.state == S.REST:
            # 被点醒：一句「不满被打扰」，贴图切 休息\1.png；对话结束自动回站立
            self._rest_woken = True
            self._rest_wake_count += 1
            self.say(dialogue.pick("rest_wake") or "唔……干嘛呀。")
            self._rest_wake_bubble = True
            if self._rest_wake_count >= config.REST_WAKE_LIMIT:
                # 一直点一直坐着不像话：点到上限就直接起身（台词还挂在气泡上，人会站起来说）
                self._leave_rest()
        elif self._llm_ready() and self.state in (S.STAND, S.WALK, S.RUN):
            # 在线：没有预设闲聊、没有选项按钮，台词交给模型现编
            self._ai_click()
        elif self.state in (S.STAND, S.RUN) and self._clicks_annoyed():
            # 频繁点击：贴图切「站立\3.png」（angry 帧）+ 一句不耐烦
            self.say(dialogue.pick("click_annoy") or "别戳啦！", mood="angry")
        elif self.state == S.STAND:
            # 左键：小概率出选项，其次闲聊/季节问候，其余是短应答
            if random.random() < 0.15:
                ch = dialogue.pick_choice()
                if ch:
                    self.say(ch.get("line", ""), ch.get("options"))
                    return
            line = self._pick_chat_line(config.CLICK_IDLE_CHANCE,
                                        config.CLICK_SEASON_CHANCE)
            self.say(line or dialogue.pick("click"))
        elif self.state == S.RUN:
            self.say(dialogue.pick("running_click"))
        # 其余状态点击暂不响应

    # ---------- 点击回弹（压扁 + 颤抖 + 闭眼差分） ----------
    def _blink_active(self):
        return bool(self._bounce_frame) and (
            self._pressing or time.monotonic() < self._bounce_until)

    def _on_squash_value(self, v):
        self._squash = float(v)
        self.update()

    def _on_squash_done(self):
        if abs(self._squash) >= 1e-3:
            return                      # 按下那段（终点 1.0）不用收尾
        self._squash = 0.0
        self._wobble_dx = 0.0
        self._apply_mask()              # 弹回原位，遮罩收回精确轮廓
        self.update()

    def _press_fx(self):
        if self.state not in (S.STAND, S.REST):
            return                      # 奔跑/走路/拎起/坠落：保持原样，不压扁
        self.last_interaction = time.monotonic()
        self._pressing = True
        self._press_time = self.last_interaction
        self._click_consumed = False
        if self.state == S.STAND:
            self._bounce_frame = "stand5"        # 一按就眯起眼
            self._apply_frame("stand5")
        else:
            self._bounce_frame = ""              # 打盹保持坐姿，只捏一下
            self._nap_hold_timer.start(config.NAP_WAKE_HOLD_MS)
        sound.squish_press()
        self._apply_mask(wide=True)     # 一开始压就把遮罩放宽，别等第一帧把斜边切掉
        self._squash_anim.stop()
        self._squash_anim.setDuration(config.SQUASH_MS)
        self._squash_anim.setStartValue(float(self._squash))
        self._squash_anim.setEndValue(1.0)
        self._squash_anim.start()
        self._wobble_timer.start()

    def _end_bounce(self):
        if not self._pressing:
            return
        self._pressing = False
        self._nap_hold_timer.stop()
        self._wobble_timer.stop()
        self._wobble_dx = 0.0
        now = time.monotonic()
        if self._bounce_frame:
            self._bounce_until = now + config.BLINK_HOLD_SECONDS
        if now - self._press_time < config.SQUASH_TAP_MS:
            # 点得太快：压扁还没走完，直接压到底再弹（鲸鱼插件 pressUp 的 tap 处理）
            self._squash = 1.0
            self.update()
        self._squash_anim.stop()
        self._squash_anim.setDuration(config.SQUASH_REBOUND_MS)
        self._squash_anim.setStartValue(float(self._squash))
        self._squash_anim.setEndValue(0.0)
        self._squash_anim.start()
        sound.squish_release()          # 松手接上音效后半段（长按时前半段已经播完了）

    def _cancel_bounce(self):
        """中断回弹（拎起 / 长按叫醒）：立刻回原样，动画和遮罩一起复位。"""
        self._pressing = False
        self._nap_hold_timer.stop()
        self._wobble_timer.stop()
        self._wobble_dx = 0.0
        self._bounce_frame = ""
        self._bounce_until = 0.0
        self._squash_anim.stop()
        self._squash = 0.0
        self._apply_mask()              # 遮罩收回精确轮廓，透出去的空白重新让出去
        self.update()

    def _on_wobble(self):
        if not self._pressing:
            self._wobble_timer.stop()
            self._wobble_dx = 0.0
            self.update()
            return
        el = time.monotonic() - self._press_time - config.SQUASH_MS / 1000.0
        if el < 0:                      # 压扁还没落定，先不抖
            return
        self._wobble_dx = config.TREMBLE_PX * math.sin(
            2 * math.pi * config.TREMBLE_HZ * el)
        self.update()

    def _on_nap_hold(self):
        """打盹中被按住够久：算被吵醒，沿用原来的唤醒逻辑（台词 + 嫌弃脸 + 计数）。"""
        if not self._pressing or self.state != S.REST:
            return
        self._click_consumed = True
        self._cancel_bounce()
        self._on_click()

    # ---------- 状态推进 ----------
    def _on_tick(self):
        now = time.monotonic()
        dt = max(0.001, min(now - self._last_tick, 0.1))
        self._last_tick = now

        # 气泡自动消失（计时器运行中不自动收，否则暂停/停止按钮会跟着消失）
        if self.talking and now >= self.talk_until:
            # 例外：打盹被点醒的那句「不满」没有按钮，不管计时器在不在跑都得收掉并回站立。
            # 否则计时器一跑，芙兰就永远卡在休息态（2026-10-08 第九批修）
            if self._rest_wake_bubble or not self._timer_busy():
                self.talking = False
                self._rest_wake_bubble = False
                self.bubble.hide()
                if self.state == S.REST and self._rest_woken:
                    self._leave_rest()

        if self.state == S.RUN:
            self._tick_run(now, dt)
        elif self.state == S.WALK:
            self._tick_walk(now, dt)
        elif self.state == S.PICKED:
            self._tick_picked(now, dt)
        elif self.state == S.FALL:
            self._tick_fall(now, dt)
        elif self.state == S.REST:
            self._apply_frame(self._rest_frame())
        else:  # STAND
            self._apply_frame(self._stand_frame())

        # 气泡跟随角色移动（奔跑 / 走路 / 拎起拖拽 / 坠落时）
        if self.bubble.isVisible() and not self.bubble.is_dragging \
                and self.state in (S.RUN, S.WALK, S.PICKED, S.FALL):
            self._position_bubble()

    def _tick_run(self, now, dt):
        idx = int((now - self.state_started) / config.RUN_FRAME_INTERVAL) % 2
        key = ("run1" if idx == 0 else "run2") + ("_L" if self.direction < 0 else "_R")
        self._apply_frame(key)

        self._x += self.direction * config.RUN_SPEED_PX * dt
        if self._x <= self.left_bound:
            self._x = self.left_bound
            self.direction = 1
        elif self._x >= self.right_bound:
            self._x = self.right_bound
            self.direction = -1
        self.move(int(self._x), self._y)

        if random.random() < 0.004:  # 随机掉头
            self.direction *= -1

        if now - self.state_started >= self.run_duration:
            # 跑完直接回站立；要不要坐下打盹由 _check_rest 统一判定
            self._set_state(S.STAND)

    def _tick_walk(self, now, dt):
        # 走路：复用奔跑两帧，但切帧更慢、速度 1 身位/秒
        idx = int((now - self.state_started) / config.WALK_FRAME_INTERVAL) % 2
        key = ("run1" if idx == 0 else "run2") + ("_L" if self.direction < 0 else "_R")
        self._apply_frame(key)

        self._x += self.direction * config.WALK_SPEED_PX * dt
        if self._x <= self.left_bound:
            self._x = self.left_bound
            self.direction = 1          # 撞到屏幕边缘就掉头，走完剩下的路
        elif self._x >= self.right_bound:
            self._x = self.right_bound
            self.direction = -1
        self.move(int(self._x), int(self._y))

        if now - self.state_started >= self.walk_duration:
            self._set_state(S.STAND)

    def _start_walk(self):
        self.direction = random.choice([-1, 1])
        self._set_state(S.WALK)

    def _tick_picked(self, now, dt):
        # 0~1s 保持 1.png → 1~5s 由慢到快 → 5~7s 稍微变慢 → 之后随机变快
        el = now - self.state_started
        if el < config.STRUGGLE_SWITCH:
            self._apply_frame("pick1")
            return
        e2 = el - config.STRUGGLE_SWITCH
        accel = max(config.STRUGGLE_ACCEL_END - config.STRUGGLE_SWITCH, 0.001)
        slow = max(config.STRUGGLE_SLOW_END - config.STRUGGLE_ACCEL_END, 0.001)
        if e2 < accel:
            k = e2 / accel
            interval = 0.5 + k * (config.STRUGGLE_FAST - 0.5)
        elif e2 < accel + slow:
            k = (e2 - accel) / slow
            interval = config.STRUGGLE_FAST + k * (config.STRUGGLE_SLOW - config.STRUGGLE_FAST)
        else:
            if now >= self._struggle_next_roll:
                self._struggle_interval = random.uniform(config.STRUGGLE_RANDOM_MIN,
                                                         config.STRUGGLE_RANDOM_MAX)
                self._struggle_next_roll = now + random.uniform(*config.STRUGGLE_RANDOM_HOLD)
            interval = self._struggle_interval
        # 相位累加：间隔变化时不会跳帧或倒退
        self._struggle_phase += dt / max(interval, 0.001)
        self._apply_frame("pick1" if int(self._struggle_phase) % 2 == 0 else "pick2")

    def _tick_fall(self, now, dt):
        side = "_R" if self._fall_mirror else "_L"
        ground_top = self.ground_y - config.DISPLAY_SIZE
        if self._landed:
            # 摔到地上：保持 5.png 几秒（期间不说话），再起身站立生气
            self._apply_frame("land" + side)
            if now >= self._land_time:
                self._set_state(S.STAND)
                self.say(dialogue.pick("fallen"), mood="angry")
            return
        # 放下后下坠(3.png) → 快接触到任务栏时切 4.png
        if (ground_top - self._y) <= config.FALL_NEAR_GROUND:
            self._apply_frame("fall2" + side)
        else:
            self._apply_frame("fall1" + side)
        # 水平惯性：向松开前移动方向飞一小段，逐渐衰减
        self._fall_vx *= max(0.0, 1.0 - 2.5 * dt)
        self._x += self._fall_vx * dt
        if self._x < self.left_bound:
            self._x = self.left_bound
            self._fall_vx = abs(self._fall_vx) * 0.4
        elif self._x > self.right_bound:
            self._x = self.right_bound
            self._fall_vx = -abs(self._fall_vx) * 0.4
        # 垂直下落：重力 + 终速
        self._fall_speed = min(self._fall_speed + 700.0 * dt, 800.0)
        self._y += self._fall_speed * dt
        if self._y >= ground_top:
            # 倒地帧内容顶到画布最底边，再整体下移 LAND_OFFSET_PX 消除悬空感
            self._y = ground_top + config.LAND_OFFSET_PX
            self._fall_vx = 0.0
            self._landed = True
            self._land_time = now + config.FALL_RECOVER
            self._apply_frame("land" + side)   # 触地当帧就换上 5.png，不拖到下一帧
        self.move(int(self._x), int(self._y))

    def _on_think(self):
        now = time.monotonic()
        # 全屏检测 / 桌面感知放在最前面：躲起来的时候也必须照常跑，
        # 否则退不出全屏、人也回不来，Activity 那边还会把「一直是你」当成没变化
        self._fs_ticks += 1
        if self._fs_ticks % self._fs_every == 0:
            self._check_fullscreen()
            self.activity.tick()
        if not self.isVisible():
            # 躲进托盘期间不算空闲（躲起来也是主人的操作），露面前的时间不计入 15 分钟
            self.last_interaction = now
            return
        self._check_rest(now)
        if self.state != S.STAND or self._rest_pending_at:
            return                 # 休息宽限期内不再触发奔跑/走路
        stood = now - self.state_started
        if stood < 30:
            return
        # 先判定「随机走两步」（概率刻意压低），再判定奔跑
        if random.random() < config.WALK_CHANCE:
            self._start_walk()
            return
        p = 0.01 + 0.07 * min((stood - 30) / 120.0, 1.0)
        if random.random() < p:
            self._start_run()

    # ---------- 休息（无操作打盹） ----------
    def _check_rest(self, now):
        """无操作满 REST_IDLE_SECONDS 就坐下打盹；正在跑/走则等满宽限期再切。

        只在站立态判定；拎起/坠落本身需要用户交互，触发时 last_interaction
        已被刷新，因此天然不算「无操作」。
        """
        if self._timer_busy():
            # 计时器运行期间算「有事在做」：不累积空闲，结束后重新计 15 分钟
            self.last_interaction = now
            self._rest_pending_at = 0.0
            return
        if now - self.last_interaction < config.REST_IDLE_SECONDS:
            self._rest_pending_at = 0.0
            return
        if self._rest_pending_at:
            if now >= self._rest_pending_at:
                self._begin_rest()
            return
        if self.state == S.STAND:
            self._begin_rest()
        elif self.state in (S.RUN, S.WALK):
            # 到点时还在动：固定再等满 REST_GRACE_SECONDS，期间不再触发跑/走
            self._rest_pending_at = now + config.REST_GRACE_SECONDS

    def _begin_rest(self):
        self.talking = False
        self.talk_until = 0.0
        self.expression = ""
        self.expression_until = 0.0
        self.bubble.hide()
        self._set_state(S.REST)

    def _rest_frame(self):
        # 打盹用 2.png；被点醒、说话期间切 1.png（嫌弃脸）
        if self.talking and time.monotonic() < self.talk_until:
            return "rest1"
        return "rest2"

    def _leave_rest(self):
        """打盹中被点醒、对话结束：回站立，并重新开始 15 分钟计时。"""
        self.last_interaction = time.monotonic()
        self._set_state(S.STAND)

    def _start_run(self):
        self.direction = random.choice([-1, 1])
        self._set_state(S.RUN)
        self.say(dialogue.pick("running"))

    def _pick_chat_line(self, idle_chance, season_chance):
        """闲聊抽词：季节问候 / 闲聊 / None（交给调用方用短应答兜底）。"""
        r = random.random()
        if r < season_chance:
            line = dialogue.pick_season()
            if line:
                return line
        elif r < season_chance + idle_chance:
            line = dialogue.pick("idle_talk")
            if line:
                return line
        return None

    def _on_active_talk(self):
        self._schedule_active_talk()
        # 隐藏后不再冒随机台词（只保留番茄钟/整点等主动提醒）
        if not self.isVisible():
            return
        if self.state != S.STAND:
            return
        if self._llm_ready():
            # 在线：现编一句。本批还没有桌面事件，先靠 brain 的冷却当「十分钟最多一次」
            self._ai_active()
            return
        line = self._pick_chat_line(config.ACTIVE_IDLE_CHANCE,
                                    config.ACTIVE_SEASON_CHANCE)
        if line:
            self.say(line)

    def _schedule_active_talk(self):
        lo, hi = self.settings.get("active_talk_interval",
                                   [config.ACTIVE_TALK_MIN, config.ACTIVE_TALK_MAX])
        lo = max(5, int(lo))
        hi = max(lo, int(hi))
        self.active_talk_timer.start(random.randint(lo, hi) * 1000)

    # ---------- 菜单 / 托盘 ----------
    def _menu_items(self):
        """右键菜单的条目：(文案, 图标名, 回调)。文案是 "" 就当分隔线。

        单拎出来是为了自检能看一眼「离线时到底有没有聊天入口」，不用真的弹菜单。
        """
        items = []
        if self._llm_ready():
            items.append(("聊天", "chat", self._menu_chat))
            items.append(("", "", None))
        items += [
            ("隐藏", "hide", self.hide_pet),
            ("", "", None),
            ("番茄钟", "tomato", self._menu_pomodoro),
            ("倒计时", "timer", self._menu_countdown),
            ("倒数日", "day", self._menu_countdown_day),
            ("待办清单", "todo", self._menu_todo),
            ("", "", None),
            ("打开收藏文件夹", "folder", self._menu_open_collect),
            ("设置", "settings", self._menu_settings),
            ("", "", None),
            ("退出", "quit", self.quit_pet),
        ]
        return items

    def contextMenuEvent(self, e):
        menu = theme.make_menu(self)
        for text, icon_name, callback in self._menu_items():
            if not text:
                menu.addSeparator()
            else:
                theme.add_item(menu, text, icon_name, callback)
        if isinstance(menu, theme.RoundedMenu):
            menu.show_padded(e.globalPos())          # 圆角菜单要先算尺寸再摆位
            menu.exec()
        else:
            menu.exec(e.globalPos())

    # ---------- 功能入口 ----------
    def show_dialog(self, key, factory):
        """非模态弹窗：同类只留一个，不挡桌宠，可以边看着芙兰边操作。"""
        dlg = self._dlgs.get(key)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            return dlg
        dlg = factory()
        self._dlgs[key] = dlg
        dlg.finished.connect(lambda _=0, k=key: self._dlgs.pop(k, None))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def _menu_pomodoro(self):
        was_running = self.pomodoro.is_running()
        from timers import PomodoroDialog

        def make():
            dlg = PomodoroDialog(self)

            def on_done(result, dlg=dlg, was_running=was_running):
                if result != QDialog.Accepted:
                    return
                if was_running:
                    self.pomodoro.stop(quiet=True)
                self.pomodoro.start(dlg.values())

            dlg.finished.connect(on_done)
            return dlg

        self.show_dialog("pomodoro", make)

    def _menu_countdown(self):
        from timers import CountdownDialog

        def make():
            dlg = CountdownDialog(self)

            def on_done(result, dlg=dlg):
                if result != QDialog.Accepted:
                    return
                total = dlg.total_seconds()
                if total <= 0:
                    self.say("时长是 0 秒哦，先填个数字吧。")
                    return
                if self.countdown.is_running():
                    self.countdown.stop(quiet=True)
                self.countdown.start(total, dlg.task_type())

            dlg.finished.connect(on_done)
            return dlg

        self.show_dialog("countdown", make)

    def _menu_countdown_day(self):
        from countdown_day import open_countdown_day
        open_countdown_day(self)

    def _menu_todo(self):
        from todo import TodoDialog
        self.show_dialog("todo", lambda: TodoDialog(self))

    def _menu_open_collect(self):
        # 2026-10-24 补充⑮：用户反馈「收藏文件夹打不开」——实测 os.startfile()
        # 在低完整性进程 / 受限环境里会直接抛 PermissionError [WinError 5]，
        # 而这是窗口程序、没有控制台，异常一抛就等于「点了没反应」。
        # 所以按 os.startfile → explorer.exe → 抄路径 三级往下退，别静默失败。
        import os
        import subprocess
        path = config.COLLECT_DIR
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        try:
            os.startfile(str(path))
            return
        except OSError:
            pass
        try:
            subprocess.Popen(["explorer.exe", str(path)], close_fds=True)
            return
        except OSError:
            pass
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(str(path))
        self.say("文件夹叫不开，路径抄你剪贴板了，自己粘到地址栏嘛。")

    def _menu_settings(self):
        from settings_dialog import SettingsDialog
        self.show_dialog("settings", lambda: SettingsDialog(self))

    # ---------- 在线模式（聊天） ----------
    def _llm_ready(self):
        """离线还是在线：总开关打开，且地址 / key / 模型三样都填了才算在线。"""
        llm = self.settings.get("llm") or {}
        if not isinstance(llm, dict) or not llm.get("enabled"):
            return False
        return all(str(llm.get(k) or "").strip()
                   for k in ("base_url", "api_key", "model"))

    def _menu_chat(self):
        from chat_ui import ChatWindow
        self.show_dialog("chat", lambda: ChatWindow(self))

    def _reset_chat_history(self):
        """每次启动把聊天记录清空（用户要求：重启不留下次的对话）。"""
        try:
            save_chat_history({"messages": [], "usage": {}, "last_date": ""})
        except Exception:
            pass                         # 文件写不了也别拦着桌宠启动

    def _ai_click(self):
        """被戳一下：先压到底再弹（视觉上就是「我在想」），然后让模型现编一句。"""
        now = time.monotonic()
        if now - self._ai_click_at < config.AI_CLICK_DEBOUNCE:
            return                       # 连点防抖：弹指之间那几下算同一下
        self._ai_click_at = now
        if not self._pressing:
            self._press_fx()
        self._end_bounce()               # 走 SQUASH_TAP_MS 的 tap 分支＝压到底再弹
        if self._ai_busy or self.net.busy:
            return                       # 单飞：上一个还在路上，这次只回弹、不排队
        ctx = brain.context(self)
        if not brain.allow("click", ctx):
            return                       # 今天的吐槽名额用完了，就安静一下
        self._ai_busy = True
        self.net.chat(brain.build_messages("click", ctx), "click")

    def _ai_active(self):
        """自己开口。本批没有桌面事件，纯占位：同类冷却过了才说一句。"""
        if self._ai_busy or self.net.busy or self.talking:
            return
        ctx = brain.context(self)
        if not brain.allow("active", ctx):
            return
        self._ai_busy = True
        self.net.chat(brain.build_messages("active", ctx), "active")

    def _on_ai_done(self, kind, text, err):
        # 聊天窗自己贴记录、自己说话；这里只管「点一下」和「自己开口」
        if kind == "voice":
            # 语音问的那句回来了（也可能是 20 秒超时/断网）：同一个气泡换内容
            if err or not str(text or "").strip():
                self._on_voice_failed(err)   # 语音这条路统一说「没听清」，不甩「电波不通」
            else:
                self._on_voice_reply(text)
            return
        if kind not in ("click", "active"):
            return
        self._ai_busy = False
        if err or not str(text or "").strip():
            self._on_ai_error(err)
            return
        line = brain.clean(text) or str(text).strip()
        if line:
            self.say(line, active=True)

    def _on_ai_error(self, err="", text=""):
        """请求挂了：压一下、留闭眼帧、响一声，再说那句固定的话（60 秒内只一次）。"""
        now = time.monotonic()
        if now < self._ai_err_until:
            return
        self._ai_err_until = now + config.AI_ERR_COOLDOWN
        sound.play("error.wav")
        if not self._pressing:
            self._press_fx()
        self._end_bounce()
        self.say(text or "唉......电波貌似接收失败了，{nickname}去检查一下吧？")
        if err in ("auth", "rate", "billing"):
            chat = self._dlgs.get("chat")
            if chat is not None and chat.isVisible():
                chat.note("钥匙好像不对（401），去设置里看一眼" if err == "auth"
                          else "账户余额不够了（402），去充点钱吧" if err == "billing"
                          else "问得太勤了（429），隔一会儿再说")

    # ---------- 语音（按住热键说话） ----------
    def _voice_sync(self):
        """语音总开关：没打开、没有本地模型就彻底不轮询热键（不占资源、不误触）。"""
        voice = self.settings.get("voice") or {}
        self.voice.configure(voice if isinstance(voice, dict) else {})

    def _voice_listening(self, on):
        """按下：自己按压回弹一下、闭眼、头顶开始转圈。松开不睁眼——还在等识别和回答。"""
        if not on:
            return                       # 收尾统一走 _voice_finish()
        self._voice_busy = True
        if self.state == S.STAND and not self._pressing:
            self._press_fx()             # 自己按一下（压扁 + 闭眼帧 + 捏一下的音效）
            self._end_bounce()           # 再弹回来
        self._voice_look(True)           # _end_bounce 会把闭眼收成 0.5 秒，这里盖回去

    def _voice_look(self, on):
        """闭眼（stand5）+ 头顶转圈：录音、识别、等回答这段时间全程保持。

        收尾时**当场睁眼**（不留那半秒闭眼），她想早点看见你。
        """
        if on:
            self._bounce_frame = "stand5"
            self._bounce_until = float("inf")
            if self.state == S.STAND:
                self._apply_frame("stand5")
        elif self._bounce_frame == "stand5":
            self._bounce_frame = ""
            self._bounce_until = 0.0
        self._spin(on)

    def _voice_finish(self):
        """这一轮说完了（拿到回答 / 失败 / 误触）：睁眼、转圈收掉。"""
        self._voice_busy = False
        self._voice_guard.stop()
        self._voice_look(False)

    def _spin(self, on):
        """头顶那个「大脑宕机」转圈：开＝每 VOICE_SPIN_MS 换一格，关＝停并收回遮罩。"""
        if not on:
            if not self._spin_on:
                return
            self._spin_on = False
            self._spin_timer.stop()
            self._apply_mask()           # 转圈走了，遮罩收回精确轮廓
            self.update()
            return
        if self._spin_on:
            return
        if not self._spin_frames:
            self._load_spin()
        if not self._spin_frames:
            return                       # 贴图不在就当没有，不转也不报错
        self._spin_on = True
        self._spin_step = 0
        self._spin_timer.start()
        self._apply_mask(wide=True)      # 转圈画在帽子顶上，遮罩得放宽到外接矩形
        self.update()

    def _load_spin(self):
        """读 贴图\\加载\\1..12.png（按 DPR 渲染一次，第一次用到才读）。"""
        try:
            files = sorted((p for p in config.VOICE_SPIN_DIR.glob("*.png")
                            if p.stem.isdigit()), key=lambda p: int(p.stem))
        except OSError:
            return
        phys = max(1, int(round(config.VOICE_SPIN_SIZE * self._dpr)))
        frames = []
        for path in files:
            try:
                img = Image.open(str(path)).convert("RGBA")
            except OSError:
                return
            img = img.convert("RGBa").resize((phys, phys), Image.LANCZOS).convert("RGBA")
            pix = _pil_to_qpixmap(img)
            pix.setDevicePixelRatio(self._dpr)
            frames.append(pix)
        self._spin_frames = frames

    def _spin_tick(self):
        if not self._spin_frames:
            return
        self._spin_step = (self._spin_step + 1) % len(self._spin_frames)
        self.update()

    def _paint_spin(self, p):
        """画在她帽子顶上——同一个窗口里画，所以她一走动转圈跟着走。"""
        if not self._spin_on or not self._spin_frames:
            return
        size = config.VOICE_SPIN_SIZE
        x = int(self.width() * config.VOICE_SPIN_X - size / 2.0)
        y = int(self.height() * config.VOICE_SPIN_Y)
        p.drawPixmap(x, y, self._spin_frames[self._spin_step])

    def _on_voice_heard(self, text):
        """听清了：主人说的一字一句先显示在气泡里，再当聊天输入发给她（不弹聊天窗）。"""
        text = str(text or "").strip()
        if not text:
            self._voice_finish()
            return
        self._say_user(text)
        self._voice_record("user", text)
        if not self._llm_ready():
            self._voice_finish()             # 没配模型：话至少留在气泡里，别装听不见
            return
        ctx = self.chat_ctx(self._voice_context())
        self._voice_guard.start()            # 最多等 20 秒，超时自己睁眼吭一句
        self.net.chat(brain.build_messages("chat", ctx), "voice")

    def _voice_context(self):
        """带给模型的上文：聊天记录最后 20 条（刚说的那句已经在里面了）。"""
        msgs = load_chat_history().get("messages") or []
        return [{"role": m.get("role") or "user", "content": str(m.get("content") or "")}
                for m in msgs[-20:]]

    def _voice_record(self, role, content):
        """记一笔聊天记录：聊天窗开着就让它自己写（会落盘+刷新），没开就直接写盘。"""
        chat = self._dlgs.get("chat")
        if chat is not None:
            chat._push(role, content)
            return
        hist = load_chat_history()
        msgs = hist.setdefault("messages", [])
        msgs.append({"role": role, "content": str(content),
                     "ts": time.time(), "active": False})
        del msgs[:-200]
        save_chat_history(hist)

    def _on_voice_reply(self, text):
        """回答回来了：同一个气泡换内容，转圈和闭眼收掉。"""
        self._voice_finish()
        if self.state in (S.STAND, S.REST):
            self._press_fx()             # 听完话再弹一下：跟被点一下同款小动画
            self._end_bounce()
            # 这一下只留压扁回弹，眼睛当场睁开（不然又要多闭半秒）
            self._bounce_frame = ""
            self._bounce_until = 0.0
        line = brain.clean(text) or str(text).strip()
        if not line:
            return
        chat = self._dlgs.get("chat")
        live = chat is not None and chat.isVisible()
        self.say(line, active=live)          # 聊天窗开着时 say 会自己记一笔
        if not live:
            self._voice_record("assistant", line)

    def _on_voice_failed(self, err=""):
        """没录上 / 没听清：先睁眼收圈；误触（short）一声不吭，真失败才吭那一句。"""
        self._voice_finish()
        if err == "short":
            return
        self._on_ai_error(err, "……我没听清，再来一次？")

    # ---------- 桌面感知（看见你在干什么） ----------
    def _watch_sync(self):
        """「看见你在干什么」总开关：一开就采样，一关就彻底停（省电，也让人放心）。"""
        watch = self.settings.get("watch") or {}
        if isinstance(watch, dict) and watch.get("enabled"):
            self.activity.start()
        else:
            self.activity.stop()

    def _screen_text(self, app, title):
        """塞给模型的「你现在看得到什么」：标题 + 程序 + 手感 + 还开着什么。"""
        text = "%s（%s）；%s" % (title, app, self.activity.feel(self._fs_active))
        bg = self.activity.background()
        if bg:
            text += "；电脑上还开着：%s" % bg
        return text

    def watch_screen(self):
        """聊天窗要用：现在能看见什么。总开关关着 / 全屏躲着 / 还没采到 → ("", "")。"""
        watch = self.settings.get("watch") or {}
        if not isinstance(watch, dict) or not watch.get("enabled"):
            return "", ""
        if self._fullscreen_hidden:
            return "", ""
        app, title = self.activity.current
        if not app:
            return "", ""
        return app, self._screen_text(app, title)

    def chat_ctx(self, history):
        """聊天窗的 ctx：带上人设 + 现在看得见什么（没开总开关就什么都不带）。"""
        app, screen = self.watch_screen()
        ctx = brain.context(self, activity=pretty(app), screen=screen)
        ctx["history"] = history
        return ctx

    def _watch_ready(self):
        """现在能不能因为她看见你在干什么而开口。"""
        if self._fullscreen_hidden or not self.isVisible():
            return False          # 全屏躲着 / 收进托盘：不发请求，也不弹气泡
        if not (self.settings.get("watch") or {}).get("enabled"):
            return False
        return not (self._ai_busy or self.net.busy)

    def _watch_request(self, ctx, ask):
        """真把这句话发给模型。ctx 由 brain.context() 给，ask 是这一句的旁白。"""
        ctx["ask"] = ask
        self._ai_busy = True
        self.net.chat(brain.build_messages("active", ctx), "active")

    def _watch_say(self, app, screen, ask):
        """过一遍冷却 / 每日上限，过了才发。返回发没发出去。"""
        ctx = brain.context(self, activity=pretty(app), screen=screen)
        if not brain.allow("active", ctx):
            return False              # 同一个程序刚说过 / 今天说得够多了
        self._watch_request(ctx, ask)
        return True

    def _on_activity_changed(self, app, title):
        """换了前台程序。"""
        if not self._watch_ready():
            return
        screen = self._screen_text(app, title)
        if self._idle_back_pending:
            self._idle_back_pending = False
            if time.monotonic() - self._back_at >= config.ACTIVITY_BACK_COOLDOWN:
                if self._watch_say(
                        app, screen,
                        "{nickname}刚走开一阵，现在回来了，正在用 %s。"
                        "说一句「你可算回来了」，像小孩那样随口一点。" % pretty(app)):
                    self._back_at = time.monotonic()
                    return
        self._watch_say(
            app, screen,
            "刚切到了 %s，你看看{nickname}这会儿在干什么，随口说一句："
            "打游戏就凑上去夸两句、或者吵着要一起玩；干活就盯着他，"
            "念叨两句别一直不停。别问他在干什么，你已经在看着了。"
            "后面那几句（是不是全屏、这个程序待了多久、在不在动键鼠）只是给你判断用："
            "全屏又一直在动手，多半在打游戏；窗口开着、键鼠时停时动，多半在写东西或看东西。"
            "别把这些话原样念出来。" % pretty(app))

    def _on_idle_started(self, seconds):
        # 人都走了，这会儿说「你回来了」没人听：记一笔，等他下次换程序时再补
        if not self._watch_ready():
            return
        self._idle_back_pending = True

    def _on_active_streak(self, minutes):
        """连着忙满 50 分钟：催休息。这条不受每日上限限制，真熬太久就该被念。"""
        now = time.monotonic()
        if now - self._streak_at < config.ACTIVITY_STREAK_COOLDOWN:
            return
        if not self._watch_ready():
            return
        self._streak_at = now
        app, title = self.activity.current
        if app:
            screen = self._screen_text(app, title)
        else:
            screen = ""
        self._watch_request(
            brain.context(self, activity=app, screen=screen),
            "{nickname}已经连着忙了 %d 分钟，中间一直没歇过。催他起来动一动、歇会儿，"
            "别讲大道理，就一句。" % int(minutes))

    # ---------- 全屏时躲起来 ----------
    def _check_fullscreen(self):
        """前台是全屏窗口就躲到看不见，退出全屏再回原位。返回当前是否全屏。

        注意：不能调 hide_pet()——它有托盘兜底，托盘不可用时会拒绝隐藏。
        """
        watch = self.settings.get("watch") or {}
        full = self._foreground_fullscreen()
        was = self._fs_active
        self._fs_active = full                 # 「手感」里要告诉模型是不是全屏，跟躲不躲无关
        # 连着看两次都全屏才躲（慢 3 秒）：输入法候选、覆盖层这类窗口偶尔抢一下前台，
        # 一次误判就消失、得靠托盘才找回来，比慢 3 秒难查多了
        self._fs_hits = self._fs_hits + 1 if full else 0
        if not isinstance(watch, dict) or not watch.get("hide_in_fullscreen", True):
            return False
        if full and self._fs_hits == 2 and not self._fullscreen_hidden:
            if self.isVisible():
                self._fullscreen_hidden = True
                self.hide()                      # 位置不动，回来还是原地
        elif not full and was:
            if self._fullscreen_hidden:
                self._fullscreen_hidden = False
                self.show()
        return full

    def leave_fullscreen_hidden(self):
        """托盘里手动点了「显示」：这次全屏就别再自动躲了（用户就是想看）。"""
        self._fullscreen_hidden = False

    def _foreground_fullscreen(self):
        """前台窗口是不是「刚好铺满一块显示器、而且没有标题栏」的全屏窗口。

        只看尺寸会误判最大化的普通窗口，所以再要求没有 WS_CAPTION。
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            for mine in (self.winId(), self.bubble.winId()):
                if hwnd == int(mine):
                    return False                 # 自己抢到前台了，不算全屏

            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in SHELL_CLASSES:
                return False                 # 桌面本身 / 任务栏 / 输入法宿主这类系统叠层
            if overlay(hwnd):
                return False                 # 分层 / 透明 / 不抢焦点的覆盖层，不是真全屏

            GWL_STYLE, WS_CAPTION = -16, 0x00C00000
            if user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION:
                return False                 # 有标题栏：最大化的普通窗口，别乱躲

            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
            class _MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD),
                            ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD)]
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            mon = user32.MonitorFromWindow(hwnd, 2)      # MONITOR_DEFAULTTONEAREST
            if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
                return False
            m, tol = info.rcMonitor, config.FULLSCREEN_TOL
            return (abs(rect.left - m.left) <= tol
                    and abs(rect.top - m.top) <= tol
                    and abs(rect.right - m.right) <= tol
                    and abs(rect.bottom - m.bottom) <= tol)
        except Exception:                    # 没桌面（自检）或系统抽风：就当不是全屏
            return False

    # ---------- 设置刷新 ----------
    def refresh_settings(self):
        self.settings = load_settings()
        self._watch_sync()          # 「看见你在干什么」一开一关立刻生效，不用重启
        self._voice_sync()          # 语音开关 / 地址 / 热键同理

    def _apply_nickname(self, text):
        # 台词里的称呼统一写成 {nickname}，dialogue.pick() 里已经替换过一遍；
        # 这里再兜一次：万一某句模板 .format() 失败被原样返回，气泡里也不会漏出 {nickname}。
        if not text:
            return text
        nick = self.settings.get("nickname", "你") or "你"
        return text.replace("{nickname}", nick)

    # ---------- 赠礼（拖放文件） ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            # 声明为 Copy：真正的移动由我们自己完成，避免资源管理器在
            # 我们失败回滚时仍然删掉源文件
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        from pathlib import Path
        urls = e.mimeData().urls()
        e.setDropAction(Qt.CopyAction)
        e.accept()
        if not urls:
            return
        items = []
        total = 0
        already = 0
        for u in urls:
            raw = u.toLocalFile()
            if not raw:
                continue
            p = Path(raw)
            try:
                if not p.exists():
                    continue
            except OSError:
                continue
            # 绝不动程序自己的目录及其祖先
            if self._is_app_or_ancestor(p):
                continue
            if self._is_inside_collect(p):
                already += 1       # 已经在收藏夹里，算「已收下」而不是失败
                continue
            items.append(p)
            total += self._path_size(p)
        if not items and not already:
            return
        if total > config.GIFT_MAX_BYTES:
            self.say(dialogue.pick("gift_too_big") or "太大啦，我吃不下……")
            return
        moved = already
        for p in items:
            ok, why = self._move_into_collect(p)
            self._log_gift(p, ok, why)
            if ok:
                moved += 1
        if moved:
            self.say(dialogue.pick("gift"), mood="happy")
        else:
            self.say(dialogue.pick("gift_fail") or "诶……这个动不了。")

    def _move_into_collect(self, p):
        """把文件真正「移动」到 收藏\\：同盘改名；跨盘复制后删源并校验。

        任一步失败都回滚掉刚落到 收藏\\ 的副本，绝不留下「源和目标都在」
        的复制粘贴假象。返回 (是否成功, 原因)。
        """
        import os
        config.COLLECT_DIR.mkdir(parents=True, exist_ok=True)
        target = config.COLLECT_DIR / p.name
        try:
            if target.exists() or target.is_symlink():
                target = self._unique_target(p)
        except OSError as ex:
            return False, f"目标路径异常: {ex}"
        try:
            same_volume = os.stat(str(p)).st_dev == os.stat(str(config.COLLECT_DIR)).st_dev
        except OSError:
            same_volume = False
        if same_volume:
            first = ""
            try:
                os.replace(str(p), str(target))
                if p.exists():
                    first = "同盘移动后源文件仍存在"
                else:
                    return True, "同盘移动"
            except OSError as ex:
                first = f"同盘移动失败: {ex}"
            # 回退：低完整性进程（exe 被打上 Low 标签时）改不动普通位置的
            # 文件，os.replace 会被拒；改用「复制进收藏 → 删源」这条路，
            # 并把首因写进日志，方便一眼看出是权限问题还是别的毛病
            ok, why = self._move_by_copy(p, target)
            if ok:
                return True, f"{why}（同盘回退；首因 {first}）"
            return False, f"{first} → {why}"
        return self._move_by_copy(p, target)

    def _move_by_copy(self, p, target):
        """复制到 收藏\\ → 清只读位 → 删源 → 校验；任一步失败都回滚副本。

        绝不留下「源和目标都在」的复制粘贴假象。返回 (是否成功, 原因)。
        """
        import os
        import shutil
        import stat
        try:
            if p.is_dir():
                shutil.copytree(str(p), str(target))
            else:
                shutil.copy2(str(p), str(target))
        except OSError as ex:
            self._rollback(target)
            return False, f"复制到收藏失败: {ex}"
        try:
            if p.is_dir():
                shutil.rmtree(str(p))
            else:
                os.chmod(str(p), os.stat(str(p)).st_mode | stat.S_IWRITE)
                os.unlink(str(p))
        except OSError as ex:
            self._rollback(target)
            return False, f"删除源文件失败: {ex}"
        if p.exists():
            self._rollback(target)
            return False, "删除源文件后源仍然存在"
        return True, "复制后删源"

    @staticmethod
    def _rollback(target):
        import shutil
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(str(target), ignore_errors=True)
            elif target.exists() or target.is_symlink():
                target.unlink()
        except OSError:
            pass

    @staticmethod
    def _integrity_level():
        """当前进程的完整性级别（S-1-16-4096 = Low）。

        exe 若被打上 Low 标签（放在沙箱/低完整性目录里），进程也是 Low，
        此时改不动普通位置的文件，赠礼就会报「拒绝访问」。
        """
        try:
            import ctypes
            from ctypes import wintypes

            advapi32 = ctypes.windll.advapi32
            kernel32 = ctypes.windll.kernel32
            # 必须声明签名：GetCurrentProcess 返回伪句柄 -1，按默认 c_int
            # 传出去会被截断，OpenProcessToken 就会失败
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.LocalFree.argtypes = [wintypes.HANDLE]
            advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                  ctypes.POINTER(wintypes.HANDLE)]
            advapi32.OpenProcessToken.restype = wintypes.BOOL
            advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                     ctypes.c_void_p, wintypes.DWORD,
                                                     ctypes.POINTER(wintypes.DWORD)]
            advapi32.GetTokenInformation.restype = wintypes.BOOL
            advapi32.ConvertSidToStringSidW.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
            advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

            token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008,
                                             ctypes.byref(token)):
                return "未知"
            try:
                need = wintypes.DWORD(0)
                advapi32.GetTokenInformation(token, 25, None, 0, ctypes.byref(need))
                if not need.value:
                    return "未知"
                buf = ctypes.create_string_buffer(need.value)
                if not advapi32.GetTokenInformation(token, 25, buf, need.value,
                                                    ctypes.byref(need)):
                    return "未知"
                sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p)).contents.value
                text = ctypes.c_wchar_p()
                if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                    return "未知"
                try:
                    return text.value or "未知"
                finally:
                    kernel32.LocalFree(text)
            finally:
                kernel32.CloseHandle(token)
        except Exception:
            return "未知"

    @staticmethod
    def _log_gift(p, ok, why):
        # 赠礼诊断日志：每次拖放一行（时间 / 结果 / 原因 / 源路径 / 进程完整性级别）
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            line = "%s\t%s\t%s\t%s\tIL=%s\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"),
                "OK" if ok else "FAIL", why, p, PetWindow._integrity_level())
            with open(config.DATA_DIR / "gift.log", "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    @staticmethod
    def _is_app_or_ancestor(p):
        try:
            rp = p.resolve()
            app = config.APP_DIR.resolve()
        except OSError:
            return True
        return rp == app or rp in app.parents

    @staticmethod
    def _path_size(p):
        if p.is_file():
            try:
                return p.stat().st_size
            except OSError:
                return 0
        total = 0
        try:
            for child in p.rglob("*"):
                if child.is_file():
                    try:
                        total += child.stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def _is_inside_collect(self, p):
        try:
            p.resolve().relative_to(config.COLLECT_DIR.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _unique_target(p):
        target = config.COLLECT_DIR / p.name
        stem = p.stem
        suffix = p.suffix
        i = 1
        while target.exists():
            target = config.COLLECT_DIR / f"{stem}_{i}{suffix}"
            i += 1
        return target

    def hide_pet(self):
        # 兜底：托盘不可用就干脆不隐藏，否则芙兰会「叫不回来」
        from PySide6.QtWidgets import QSystemTrayIcon
        if self.tray is None or not QSystemTrayIcon.isSystemTrayAvailable():
            self.say("托盘图标好像不见了……我先不躲起来，免得主人找不到我。")
            return
        self.hide()
        self.tray.icon.show()          # 保险：隐藏前确认托盘图标确实是显示的
        self.tray.update_visibility()

    def quit_pet(self):
        self.bubble.close()
        QApplication.instance().quit()

    def set_tray(self, tray):
        self.tray = tray

    def hideEvent(self, e):
        self.bubble.hide()
        super().hideEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        # 半透明窗口不会自动擦背景：压扁/颤抖时贴图挪位，上一帧的边会残留成"破损"。
        # 每帧先把整块擦成透明，再画当前帧。
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        k = self._squash
        dx = self._wobble_dx
        if abs(k) < 1e-3 and abs(dx) < 1e-3:
            p.drawPixmap(0, 0, self._cur_pix)
            self._paint_spin(p)          # 头顶转圈：只在不压扁时画（压扁那 0.5 秒先让她弹回来）
            return
        # 压扁/颤抖：按物理像素逐行 1:1 拷贴图（整数行），全程不重采样。
        # 缩放采样会把轮廓像素变成半透明，叠在桌面上就是"边缘被吃掉"；
        # 逐行拷只是丢行/挪行，每个画出来的像素都和原图一模一样。
        # 底边为锚：最底一行不动，压缩量从上面丢掉（和鲸鱼插件 transform-origin 50% 100% 同理）。
        img = self._cur_img
        if img is None:
            return
        dpr = self._dpr
        p.scale(1.0 / dpr, 1.0 / dpr)     # 之后一律用物理像素坐标，1:1 贴图
        dw, dh = img.width(), img.height()
        s = 1.0 - (1.0 - config.SQUASH_SCALE_Y) * k
        if s <= 0.05:
            return
        top = dh - int(round(dh * s))
        off_x = int(round(dx * dpr))
        for dy in range(top, dh):
            srow = int(round((dy - top) / s))
            if srow < 0:
                srow = 0
            elif srow >= dh:
                srow = dh - 1
            p.drawImage(off_x, dy, img, 0, srow, dw, 1)
