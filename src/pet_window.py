import random
import time
from enum import IntEnum

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QRegion, QPainter
from PySide6.QtWidgets import QWidget, QMenu, QApplication, QDialog
from PIL import Image

import config
import dialogue
import sound
import theme
from bubble import SpeechBubble
from data_manager import load_settings, save_settings
from timers import Pomodoro, Countdown
from hourly import HourlyReporter


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


def _pil_alpha_to_region(img):
    # 由 alpha 通道构建点击遮罩（alpha>0 的像素算可点击）
    alpha = img.getchannel("A").tobytes()
    w = img.width
    h = img.height
    region = QRegion()
    for y in range(h):
        base = y * w
        x = 0
        while x < w:
            if alpha[base + x] > 0:
                start = x
                while x < w and alpha[base + x] > 0:
                    x += 1
                region += QRegion(start, y, x - start, 1)
            else:
                x += 1
    return region


def _offset_frame(img, dx, dy):
    # 平移贴图内容（超出画布的部分被裁掉，空出来的部分保持透明）
    if not dx and not dy:
        return img
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


def _load_frame(path, size, dpr, mirrored=False, dx=0, dy=0):
    src = Image.open(str(path)).convert("RGBA")
    if mirrored:
        src = src.transpose(Image.FLIP_LEFT_RIGHT)
        dx = -dx                   # 镜像后「右移」在画布上要反过来才视觉一致
    # 高清渲染：PIL LANCZOS 高质量缩放，按 DPR 到物理分辨率，边缘更平滑
    phys = max(1, int(round(size * dpr)))
    hi = src.resize((phys, phys), Image.LANCZOS)
    hi = _offset_frame(hi, int(round(dx * dpr)), int(round(dy * dpr)))
    pix = _pil_to_qpixmap(hi)
    pix.setDevicePixelRatio(dpr)
    # 点击遮罩：逻辑分辨率，与贴图同源同算法，边界对齐
    lo = src.resize((size, size), Image.LANCZOS)
    lo = _offset_frame(lo, int(dx), int(dy))
    region = _pil_alpha_to_region(lo)
    return pix, region


class PetWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(config.DISPLAY_SIZE, config.DISPLAY_SIZE)

        self._dpr = max(1.0, float(QApplication.primaryScreen().devicePixelRatio()))

        # 预加载全部帧（高清像素图 + 点击遮罩）
        d = config.DISPLAY_SIZE
        self._frames = {
            "stand1": _load_frame(config.STAND_DIR / "1.png", d, self._dpr),
            "stand2": _load_frame(config.STAND_DIR / "2.png", d, self._dpr),
            "run1_L": _load_frame(config.RUN_DIR / "1.png", d, self._dpr),
            "run2_L": _load_frame(config.RUN_DIR / "2.png", d, self._dpr),
            "run1_R": _load_frame(config.RUN_DIR / "1.png", d, self._dpr, mirrored=True),
            "run2_R": _load_frame(config.RUN_DIR / "2.png", d, self._dpr, mirrored=True),
            # 被拎起的两帧：整体右移 PICK_FRAME_DX，补偿翅膀锚点的视觉偏移
            "pick1": _load_frame(config.PICK_DIR / "1.png", d, self._dpr,
                                 dx=config.PICK_FRAME_DX),
            "pick2": _load_frame(config.PICK_DIR / "2.png", d, self._dpr,
                                 dx=config.PICK_FRAME_DX),
            # 表情帧（站立 3=生气 / 4=开心），只在特定事件或选项触发时使用
            "angry": _load_frame(config.STAND_DIR / "3.png", d, self._dpr),
            "happy": _load_frame(config.STAND_DIR / "4.png", d, self._dpr),
            # 坠落三帧：放下后下坠(3) → 快接触任务栏(4) → 摔到地上(5)
            # 三帧默认朝左，向右甩出时整段镜像
            "fall1_L": _load_frame(config.PICK_DIR / "3.png", d, self._dpr),
            "fall2_L": _load_frame(config.PICK_DIR / "4.png", d, self._dpr),
            "land_L": _load_frame(config.PICK_DIR / "5.png", d, self._dpr),
            "fall1_R": _load_frame(config.PICK_DIR / "3.png", d, self._dpr, mirrored=True),
            "fall2_R": _load_frame(config.PICK_DIR / "4.png", d, self._dpr, mirrored=True),
            "land_R": _load_frame(config.PICK_DIR / "5.png", d, self._dpr, mirrored=True),
            # 休息（无操作打盹）：2.png = 闭眼打盹，1.png = 被吵醒的嫌弃脸
            "rest1": _load_frame(config.REST_DIR / "1.png", d, self._dpr),
            "rest2": _load_frame(config.REST_DIR / "2.png", d, self._dpr),
        }
        self._cur_frame = None
        self._cur_pix = None
        self._cur_region = None

        # 状态
        self.state = S.STAND
        self.direction = -1  # -1 左 / +1 右
        self.state_started = time.monotonic()
        self.run_duration = 0.0
        self.walk_duration = 0.0
        self._rest_pending_at = 0.0   # 空闲到点但还在跑/走：等满宽限期再坐下打盹
        self._rest_woken = False      # 打盹中被点醒（说话期间用 rest\1.png）
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
        self._last_tick = time.monotonic()
        self._dlgs = {}              # 非模态窗口（同类只留一个）

        # 接收拖放（赠礼）
        self.setAcceptDrops(True)

        # 功能模块
        self.pomodoro = Pomodoro(self)
        self.countdown = Countdown(self)
        self.hourly = HourlyReporter(self)

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

    # ---------- 工具 ----------
    def _apply_frame(self, key):
        if key == self._cur_frame:
            return
        self._cur_frame = key
        self._cur_pix, self._cur_region = self._frames[key]
        self.setMask(self._cur_region)
        self.update()

    def _stand_frame(self):
        # 站姿占位：计时器心情 > 对话表情 > 张嘴帧
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
        if key not in self._frames:
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
        """对话/事件触发表情帧：angry(站立3) / happy(站立4)，持续同气泡时长。"""
        key = mood if mood in ("angry", "happy") else ""
        if not key or key not in self._frames:
            return
        self.expression = key
        self.expression_until = time.monotonic() + float(
            self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))

    def say(self, text, options=None, mood=""):
        if not text and not options:
            return
        self._rest_wake_bubble = False
        text = self._apply_nickname(text)
        self.talking = True
        dur = float(self.settings.get("bubble_duration", config.BUBBLE_AUTO_HIDE))
        self.talk_until = time.monotonic() + dur
        if mood:
            self._set_expression(mood)
        else:
            # 新对话不带表情时收掉上一个表情
            self.expression = ""
            self.expression_until = 0.0
        self.bubble.show_message(text, options)
        self.bubble.show()
        self.bubble.raise_()
        self._position_bubble()

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
            self._dragging = False
            self._press_global = None
            self._snapped = False
            if not snapped:
                if was_dragging:
                    self._release_pick()
                else:
                    self._on_click()
        super().mouseReleaseEvent(e)

    def _start_pick(self):
        self.last_interaction = time.monotonic()
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
            # 被点醒：一句「不满被打扰」，贴图切 rest\1.png；对话结束自动回站立
            self._rest_woken = True
            self._rest_wake_count += 1
            self.say(dialogue.pick("rest_wake") or "唔……干嘛呀。")
            self._rest_wake_bubble = True
            if self._rest_wake_count >= config.REST_WAKE_LIMIT:
                # 一直点一直坐着不像话：点到上限就直接起身（台词还挂在气泡上，人会站起来说）
                self._leave_rest()
        elif self.state in (S.STAND, S.RUN) and self._clicks_annoyed():
            # 频繁点击：贴图切「stand\3.png」（angry 帧）+ 一句不耐烦
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
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(theme.QSS)
        menu.addAction("隐藏", self.hide_pet)
        menu.addSeparator()
        menu.addAction("番茄钟", self._menu_pomodoro)
        menu.addAction("倒计时", self._menu_countdown)
        menu.addAction("倒数日", self._menu_countdown_day)
        menu.addAction("待办清单", self._menu_todo)
        menu.addSeparator()
        menu.addAction("打开收藏文件夹", self._menu_open_collect)
        menu.addAction("设置", self._menu_settings)
        menu.addSeparator()
        menu.addAction("退出", self.quit_pet)
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
        import os
        config.COLLECT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(config.COLLECT_DIR))

    def _menu_settings(self):
        from settings_dialog import SettingsDialog
        self.show_dialog("settings", lambda: SettingsDialog(self))

    # ---------- 设置刷新 ----------
    def refresh_settings(self):
        self.settings = load_settings()

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
        """把文件真正「移动」到 collect\\：同盘改名；跨盘复制后删源并校验。

        任一步失败都回滚掉刚落到 collect\\ 的副本，绝不留下「源和目标都在」
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
        """复制到 collect\\ → 清只读位 → 删源 → 校验；任一步失败都回滚副本。

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
        p.drawPixmap(0, 0, self._cur_pix)
