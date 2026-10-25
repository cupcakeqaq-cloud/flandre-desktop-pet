# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""桌面感知：让芙兰知道你在干什么。

只问 Windows 三件事——前台是哪个程序、窗口标题是什么、键鼠多久没动过。
**不看画面、不截图**，拿到的就是两串文字，原样塞给模型。

「在打游戏还是在干活」这里一个字都不判断：写死进程名单既不准（改个名字就废）
又容易误伤，交给模型自己说人话。节拍复用 pet_window 的 think 定时器
（每 config.ACTIVITY_TICK_MS 调一次 tick），不另开 QTimer。
"""

import ctypes
import os
import time
from collections import deque
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

import config

# 桌面本身 / 任务栏 / 系统叠层：这些都不是「你在用的程序」
# Windows.UI.Core.CoreWindow = UWP 宿主，中文输入法的候选窗（TextInputHost）就是它，
# 它铺满全屏又没有标题栏，不排掉会被当成「全屏游戏」把人藏起来
SHELL_CLASSES = ("Progman", "WorkerW", "Shell_TrayWnd",
                 "Windows.UI.Core.CoreWindow", "CEF-OSC-WIDGET")
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 叠层窗口常带的扩展样式：透明 / 工具窗 / 分层 / 不抢焦点（NVIDIA、游戏内覆盖等）
_OVERLAY_EX = 0x00000020 | 0x00000080 | 0x00080000 | 0x08000000


def overlay(hwnd):
    """系统叠层（输入法候选、NVIDIA/游戏内覆盖、无障碍辅助窗）——不是真窗口。"""
    try:
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)      # GWL_EXSTYLE
        return bool(ex & _OVERLAY_EX)
    except Exception:
        return False

# 常见程序翻成人话（键一律小写）。表里没有就原样用 exe 名——不联网搜，猜错了更糟
_PRETTY = {
    "chrome.exe": "Chrome（浏览器）",
    "msedge.exe": "Edge（浏览器）",
    "firefox.exe": "Firefox（浏览器）",
    "code.exe": "VS Code（写代码）",
    "devenv.exe": "Visual Studio（写代码）",
    "pycharm64.exe": "PyCharm（写代码）",
    "winword.exe": "Word（写文档）",
    "excel.exe": "Excel（弄表格）",
    "powerpnt.exe": "PowerPoint（做幻灯片）",
    "explorer.exe": "文件资源管理器",
    "notepad.exe": "记事本",
    "mspaint.exe": "画图",
    "sai.exe": "SAI（画画）",
    "sai2.exe": "SAI（画画）",
    "photoshop.exe": "Photoshop（修图）",
    "clipstudiopaint.exe": "Clip Studio Paint（画画）",
    "gimp-2.10.exe": "GIMP（修图）",
    "genshinimpact.exe": "原神",
    "yuanshen.exe": "原神",
    "starrail.exe": "崩坏：星穹铁道",
    "zenlesszonezero.exe": "绝区零",
    "league of legends.exe": "英雄联盟",
    "leagueclientux.exe": "英雄联盟客户端",
    "steam.exe": "Steam",
    "wechat.exe": "微信",
    "weixin.exe": "微信",
    "qq.exe": "QQ",
    "tim.exe": "TIM",
    "discord.exe": "Discord",
    "spotify.exe": "Spotify（听歌）",
    "potplayermini64.exe": "PotPlayer（看视频）",
    "obsidian.exe": "Obsidian（记笔记）",
    "typora.exe": "Typora（写笔记）",
    "acrobat.exe": "PDF 阅读器",
    "acrord32.exe": "PDF 阅读器",
    "taskmgr.exe": "任务管理器",
    "windowsterminal.exe": "终端",
    "powershell.exe": "终端",
    "cmd.exe": "终端",
    "python.exe": "Python",
}


def pretty(app):
    """程序名翻成人话；表里没有就原样返回。"""
    if not app:
        return ""
    return _PRETTY.get(app.lower(), app)


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    """距上一次键盘 / 鼠标输入过了多少秒；拿不到就当 0（别把人误判成走开了）。"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        kernel32.GetTickCount.restype = wintypes.DWORD
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # GetTickCount 是 32 位、49.7 天回绕一次；差成负数就当刚绕过，按 0 算
        return max(0.0, (int(kernel32.GetTickCount()) - int(info.dwTime)) / 1000.0)
    except Exception:
        return 0.0


def _exe_name(pid):
    """PID → 可执行文件名（chrome.exe）。取不到（权限 / 进程已退）返回空串。"""
    try:
        kernel32 = ctypes.windll.kernel32
        # 必须声明签名：句柄是 64 位，按默认 c_int 出去会被截断，CloseHandle 就关错东西
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf,
                                                       ctypes.byref(size)):
                return ""
            return os.path.basename(buf.value or "") or ""
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def foreground():
    """(程序名, 窗口标题)。桌面 / 任务栏 / 标题为空 / 自己 → ("", "")。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in SHELL_CLASSES or overlay(hwnd):
            return "", ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return "", ""                 # 自己（桌宠 / 气泡）不算「你在用」
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        text = " ".join((title.value or "").split())      # 标题里的换行压平成一行
        if not text:
            return "", ""
        return _exe_name(pid.value), text[:config.ACTIVITY_TITLE_MAX]
    except Exception:
        return "", ""


_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def windows(max_count=8):
    """现在开着、没最小化的窗口 [(程序名, 标题)]，按程序名去重。

    只读窗口标题和进程名（跟前台那条一个口径），拿到的是文字不是画面。
    """
    out, seen = [], set()
    try:
        user32 = ctypes.windll.user32
        me = os.getpid()

        def _each(hwnd, _lparam):
            if len(out) >= max_count:
                return False
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in SHELL_CLASSES or overlay(hwnd):
                return True
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == me:
                return True
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            text = " ".join((title.value or "").split())
            if not text:
                return True
            app = _exe_name(pid.value)
            if not app or app in seen:
                return True
            seen.add(app)
            out.append((app, text[:config.ACTIVITY_TITLE_MAX]))
            return True

        user32.EnumWindows(_WNDENUMPROC(_each), 0)
    except Exception:
        return []
    return out


class Activity(QObject):
    """前台程序 + 空闲状态。start() / stop() 跟着设置里的总开关走。"""

    activity_changed = Signal(str, str)      # 程序名, 窗口标题（换了程序才发，同程序换标题不发）
    idle_started = Signal(int)               # 空超过阈值（秒）；一次空闲只发一次
    active_streak = Signal(int)              # 连续有输入满这么久（分钟）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._app = None            # 当前程序名；None = 还没采过样
        self._title = ""
        self._idle = False
        self._busy_since = 0.0      # 这一轮「连续有输入」从什么时候开始
        self._app_since = 0.0       # 切到这个程序是什么时候
        self._motion = deque(maxlen=10)   # 最近 10 次采样（约 30 秒）里有没有在动

    # ---------- 开关 ----------
    def start(self):
        if self._enabled:
            return
        self._enabled = True
        self._app = None            # 重新采一次，别拿关掉以前的旧程序名比
        self._title = ""
        self._idle = False
        self._busy_since = 0.0
        self._app_since = 0.0
        self._motion.clear()

    def stop(self):
        self._enabled = False

    def is_running(self):
        return self._enabled

    @property
    def current(self):
        """最近一次采到的 (程序名, 窗口标题)。还没有就现问一次（刚开机就问「在干嘛」）"""
        if not self._app:
            app, title = foreground()
            if app:
                self._app, self._title = app, title
                self._app_since = time.monotonic()
        return (self._app or ""), self._title

    def background(self, limit=4):
        """除了前台那个，还开着哪些程序（只回名字）——给她判断你在干嘛用。"""
        app = (self._app or "").lower()
        names = []
        for name, _title in windows():
            if name.lower() == app or name in names:
                continue
            names.append(name)
        return "、".join(pretty(n) for n in names[:limit])

    # ---------- 采样 ----------
    def tick(self):
        """pet_window 每 config.ACTIVITY_TICK_MS 调一次。"""
        if not self._enabled:
            return
        now = time.monotonic()
        idle = idle_seconds()

        if idle >= config.ACTIVITY_IDLE_SECONDS:
            if not self._idle:
                self._idle = True
                self._busy_since = 0.0          # 走开过了，连续工作时间重新计
                self._app_since = 0.0           # 回来之后别报「这个程序待了两小时」
                self._motion.clear()
                self.idle_started.emit(int(idle))
            return                              # 人不在：不猜他在干什么

        self._idle = False
        self._motion.append(idle <= config.ACTIVITY_MOVE_SECONDS)
        # 验收用：环境变量 FLANDRE_STREAK_TEST=180 把 50 分钟压成 3 分钟
        need = float(os.environ.get("FLANDRE_STREAK_TEST") or config.ACTIVITY_STREAK_SECONDS)
        if idle <= config.ACTIVITY_ACTIVE_GAP:
            # 有输入：开始 / 继续累积连续工作时间（中间断过就由上面那段清掉）
            if not self._busy_since:
                self._busy_since = now
            elif now - self._busy_since >= need:
                self._busy_since = now           # 报过就重新计，下一轮再说
                self.active_streak.emit(int(need // 60))

        app, title = foreground()
        if not app:
            return
        if self._app is None:
            self._app, self._title = app, title   # 第一次采样只记下，不算「换程序」开口
            self._app_since = now
            return
        if app != self._app:
            self._app, self._title = app, title
            self._app_since = now
            self.activity_changed.emit(app, title)

    def feel(self, fullscreen=False):
        """给模型的一句「手感」：全屏没有、这个程序待多久、这半分钟在不在动。"""
        bits = ["全屏" if fullscreen else "窗口"]
        if self._app_since:
            mins = int((time.monotonic() - self._app_since) / 60)
            bits.append("这个程序待了 %d 分钟" % mins if mins >= 1 else "刚切过来")
        if self._motion:
            hot = sum(self._motion)
            if hot >= len(self._motion) * 0.6:
                bits.append("这半分钟一直在动键盘鼠标")
            elif hot <= len(self._motion) * 0.2:
                bits.append("这半分钟没怎么动，大概只是看着")
        return "；".join(bits)
