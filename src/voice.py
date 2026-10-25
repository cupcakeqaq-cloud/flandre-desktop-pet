# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""按住热键说话（2026-10-25 第二十五批，第二十七批换成 paraformer 本地模型）。

按住说话键（默认 F8，可以在设置页改成任意键 / 组合键）说话，松开就转成文字，
转出来的文字当「用户输入」交给聊天。芙兰**不出声**（没有 TTS），她只回气泡。

- 热键：50ms 轮询 GetAsyncKeyState，不装键盘钩子（装钩子会被杀软盯上）
- 录音：先试 winmm 的 MCI（一句命令搞定，自带 WAV 封装）；MCI 打不开再退 waveIn*
- 识别：本地离线模型（`model/asr/` 里的 sherpa-onnx paraformer-zh，不联网、不花钱）；
  只有本地模型不在、旧配置里还留着地址时才 POST {stt_base_url}/audio/transcriptions
- 没开开关 / 没有本地模型 / 键名不认识 → 定时器都不启动，一个字节都不采
"""

import array
import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

import config
import data_manager
from net import _http_error

MOCK_ENV = "FLANDRE_VOICE_MOCK"   # 自检用：不碰麦克风、不联网，喂一段假录音＋假识别结果
LOG_ENV = "FLANDRE_VOICE_LOG"     # 排障用：按下/松开每次变化都写 data\_voice_log.txt
MOCK_TEXT = "今天有点累。"

# 能当热键的键名（F 区、字母、数字、空格和几个常用符号）。名字统一大写。
VK_NAMES = {"F%d" % n: 0x6F + n for n in range(1, 13)}
VK_NAMES.update({chr(ord("A") + i): 0x41 + i for i in range(26)})
VK_NAMES.update({str(i): 0x30 + i for i in range(10)})
VK_NAMES.update({
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
})
# 修饰键：VK_SHIFT / VK_CONTROL / VK_MENU 是「左右都算」的通用码，正好够用
MOD_NAMES = {"CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12, "WIN": 0x5B}
MOD_ORDER = ("CTRL", "SHIFT", "ALT", "WIN")
# 键盘钩子给的是「左右分开」的码（A2 左 Ctrl / A3 右 Ctrl…），GetAsyncKeyState 用的是
# 不分的 11/10/12 —— 不换算的话 Ctrl+Shift 永远等不到「按着」，热键就彻底失灵
MOD_RAW = {0x10: (0xA0, 0xA1), 0x11: (0xA2, 0xA3),
           0x12: (0xA4, 0xA5), 0x5B: (0x5B, 0x5C)}

MCI_ALIAS = "flrec"
STT_TIMEOUT = 20.0

# RegisterHotKey 用的修饰位（系统把这几个键位算进「组合键」里）
HOTKEY_ID = 0xA17E
MOD_FLAGS = {0x11: 0x0002, 0x10: 0x0004, 0x12: 0x0001, 0x5B: 0x0008}
MOD_NOREPEAT = 0x4000

# 低级键盘钩子：抓「按住/松开」最靠得住的一条路——不看焦点、输入法和游戏都吞不掉它
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_QUIT = 0x0012

try:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    winmm = ctypes.WinDLL("winmm", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
except (AttributeError, OSError):     # 非 Windows 上只 import 不崩
    user32 = winmm = kernel32 = None

if user32 is not None:
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.RegisterHotKey.restype = ctypes.c_int
    user32.RegisterHotKey.argtypes = [ctypes.c_size_t, ctypes.c_int,
                                      ctypes.c_uint, ctypes.c_uint]
    user32.UnregisterHotKey.restype = ctypes.c_int
    user32.UnregisterHotKey.argtypes = [ctypes.c_size_t, ctypes.c_int]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_uint]
    user32.UnhookWindowsHookEx.restype = ctypes.c_int
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_size_t, ctypes.c_size_t]
    user32.GetMessageW.restype = ctypes.c_int
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p,
                                   ctypes.c_uint, ctypes.c_uint]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.PostThreadMessageW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                          ctypes.c_size_t, ctypes.c_ssize_t]
    kernel32.GetCurrentThreadId.restype = ctypes.c_uint

HOOKPROC = getattr(ctypes, "WINFUNCTYPE", None)
if HOOKPROC is not None and user32 is not None:
    HOOKPROC = HOOKPROC(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_size_t)


# ---------- 底层小工具 ----------
class _WaveFormat(ctypes.Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD)]


class _WaveHdr(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p),
                ("dwBufferLength", wintypes.DWORD),
                ("dwBytesRecorded", wintypes.DWORD),
                ("dwUser", ctypes.c_size_t),
                ("dwFlags", wintypes.DWORD),
                ("dwLoops", wintypes.DWORD),
                ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_size_t)]


class _KbdllHook(ctypes.Structure):
    """低级键盘钩子回调里那个 KBDLLHOOKSTRUCT。"""
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


def _mock():
    return os.environ.get(MOCK_ENV) == "1"


def parse_hotkey(text):
    """把 "Ctrl+Shift+F8" 拆成 (修饰键 VK 元组, 主键 VK)；不认识返回 None。

    也允许只有修饰键（"Ctrl+Shift" 这种推着说话），这时主键是 0。
    """
    parts = [p.strip().upper() for p in str(text or "").split("+") if p.strip()]
    if not parts:
        return None
    mods, key = [], 0
    for part in parts:
        if part in MOD_NAMES:
            if MOD_NAMES[part] not in mods:
                mods.append(MOD_NAMES[part])
        elif part in VK_NAMES and not key:
            key = VK_NAMES[part]
        else:
            return None
    if not key and not mods:
        return None
    return tuple(mods), key


def hotkey_text(parts):
    """反着来：给界面显示规范写法（顺序固定 Ctrl+Shift+Alt+Win）。"""
    if not parts:
        return ""
    mods, key = parts
    names = [n for n in MOD_ORDER if MOD_NAMES[n] in (mods or ())]
    for name, code in sorted(VK_NAMES.items()):
        if code == key:
            # 同一个 VK 可能有多个名字（比如 "A" 和大写），挑最短那个
            names.append(name)
            break
    return "+".join(names)


def _mci(cmd):
    """发一条 MCI 命令，成功返回 0（非 0 就是错误码）。"""
    if winmm is None:
        return -1
    try:
        return int(winmm.mciSendStringW(cmd, None, 0, 0))
    except Exception:
        return -1


def _wav_bytes(pcm):
    """16k / 单声道 / 16bit 的 WAV 头 + 数据。不用标准库 wave，打包时才不用补模块。"""
    rate, ch, bits = config.VOICE_SAMPLE_RATE, 1, 16
    n = len(pcm)
    head = (b"RIFF" + (36 + n).to_bytes(4, "little") + b"WAVE"
            + b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
            + ch.to_bytes(2, "little") + rate.to_bytes(4, "little")
            + (rate * ch * bits // 8).to_bytes(4, "little")
            + (ch * bits // 8).to_bytes(2, "little") + bits.to_bytes(2, "little")
            + b"data" + n.to_bytes(4, "little"))
    return head + pcm


def _wav_seconds(path):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return 0.0
    at = raw.find(b"data")
    if at >= 0 and len(raw) >= at + 8:
        n = int.from_bytes(raw[at + 4:at + 8], "little")
        if n <= 0 or n > len(raw) - at - 8:
            n = len(raw) - at - 8        # 有的录音端把长度写成 0 / 0xFFFFFFFF
    else:
        n = max(0, len(raw) - 44)
    return n / float(config.VOICE_SAMPLE_RATE * 2)


def stt_endpoint(base_url):
    """填到域名就行，后面自动补 /audio/transcriptions（已经带上就不重复补）。"""
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/audio/transcriptions"):
        return url
    return url + "/audio/transcriptions"


def _transcribe(cfg, path):
    """发一次识别请求，返回 (文字, 错误码)。"""
    # 在线识别这条老路早就收进抽屉了（现在走本地模型），urllib 只在真要用时导：
    # 它一拽就是 email / argparse / http.client 四十毫秒，别让它白占启动时间
    import urllib.error
    import urllib.request

    url = stt_endpoint(cfg.get("stt_base_url"))
    if not url:
        return "", "bad"
    boundary = "----flandre" + os.urandom(12).hex()
    model = str(cfg.get("stt_model") or "").strip() or "whisper-1"
    parts = [
        ("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n"
         % (boundary, model)).encode("utf-8"),
        ("--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nzh\r\n"
         % boundary).encode("utf-8"),
        ("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
         "filename=\"voice.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
         % boundary).encode("utf-8"),
    ]
    try:
        parts.append(Path(path).read_bytes())
    except OSError:
        return "", "mic"
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))

    headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    key = str(cfg.get("stt_api_key") or "").strip()
    if key:
        # 两个头都发：硅基流动的文档里两种写法都出现过（bearerAuth / x-api-key），
        # 多带一个不会被拒，省得用户不知道该照哪张图填。
        headers["Authorization"] = "Bearer " + key
        headers["x-api-key"] = key
    req = urllib.request.Request(url, data=b"".join(parts),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=STT_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        return "", _http_error(e.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return "", "net"
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "", "bad"
    text = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
    return text, "" if text else "bad"


# ---------- 本地离线识别（sherpa-onnx） ----------
_LOCAL_LOCK = threading.Lock()
_LOCAL_REC = None


def local_files():
    """模型目录齐不齐：返回 (tokens, model)，缺一个就 None。

    2026-10-25 第二十七批：从「流式 zipformer 14M」换成「paraformer 中文非流式」——
    按住说话本来就不用边说边认，松手后一次性转准得多。
    """
    folder = Path(config.STT_MODEL_DIR)
    tokens = folder / "tokens.txt"
    if not tokens.is_file():
        return None
    models = sorted(p for p in folder.glob("model*.onnx") if p.is_file())
    if not models:
        return None
    # 优先 int8（小一半、快一截）；没有就退回 fp32
    model = ([p for p in models if ".int8." in p.name] or models)[0]
    return tokens, model


def local_recognizer():
    """第一次用到才加载模型（大几百毫秒），之后一直复用。"""
    global _LOCAL_REC
    if _LOCAL_REC is not None:
        return _LOCAL_REC
    files = local_files()
    if files is None:
        return None
    with _LOCAL_LOCK:
        if _LOCAL_REC is not None:
            return _LOCAL_REC
        try:
            import sherpa_onnx
        except ImportError:            # 老版本 exe 里没打进去：当作没装
            return None
        tokens, model = files
        _LOCAL_REC = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(model), tokens=str(tokens),
            num_threads=min(4, os.cpu_count() or 1),
            decoding_method="greedy_search",
            sample_rate=config.VOICE_SAMPLE_RATE, feature_dim=80)
        return _LOCAL_REC


def wav_samples(path):
    """读出 16bit PCM 的采样（第 9 行那个 _wav_bytes 也是这个格式，MCI 存的也一样）。"""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return array.array("f")
    at = raw.find(b"data")
    if at < 0 or len(raw) < at + 8:
        return array.array("f")
    n = int.from_bytes(raw[at + 4:at + 8], "little")
    start = at + 8
    if n <= 0 or n > len(raw) - start:
        n = len(raw) - start
    ints = array.array("h")
    ints.frombytes(raw[start:start + (n & ~1)])
    return array.array("f", (v / 32768.0 for v in ints))


def _transcribe_local(path):
    """本地模型转一段 wav，返回 (文字, 错误码)。"""
    rec = local_recognizer()
    if rec is None:
        return "", "stt"
    samples = wav_samples(path)
    if not samples:
        return "", "bad"
    try:
        stream = rec.create_stream()
        stream.accept_waveform(config.VOICE_SAMPLE_RATE, samples)
        # 尾巴补 0.3 秒静音：不补的话最后半个字经常被切掉
        tail = array.array("f", [0.0] * int(0.3 * config.VOICE_SAMPLE_RATE))
        stream.accept_waveform(config.VOICE_SAMPLE_RATE, tail)
        rec.decode_stream(stream)
        text = str(stream.result.text or "").strip()
    except Exception:                  # 模型坏了 / 内存不够：别把线程带走
        return "", "stt"
    return text, "" if text else "bad"


# ---------- 对外的那个 ----------
class Voice(QObject):
    """按住热键说话：按下开录，松开转文字。"""

    heard = Signal(str)       # 转写成功：这句话当用户输入
    failed = Signal(str)      # mic / net / auth / rate / bad / stt / short（误触）
    recording = Signal(bool)  # 开始 / 结束录音（桌宠换「我在听」的表情）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = {}
        self._held = False
        self._rec = None
        self._started = 0.0
        self._engine_cache = None
        self._hwnd = 0
        self._claimed = False
        self._hooked = False       # 低级键盘钩子装上了没有
        self._key_down = False     # 钩子看到的「热键按着没有」
        self._pressed = set()      # 钩子记的当前按住的键
        self._hook = None
        self._hook_proc = None
        self._hook_tid = 0
        self._hook_thread = None
        self._last_down = None
        self._hook_seen = 0.0
        self._log_path = (Path(data_manager.DATA_DIR) / "_voice_log.txt"
                          if os.environ.get(LOG_ENV) == "1" else None)
        self._timer = QTimer(self)
        self._timer.setInterval(config.VOICE_TICK_MS)
        self._timer.timeout.connect(self._poll)
        # 排障用：设了 FLANDRE_STT_PROBE=<wav 路径> 就先跑一遍本地识别，
        # 结果写成 data\_stt_probe.txt（打包后的 exe 到底能不能加载模型，只能这么看）
        probe = os.environ.get("FLANDRE_STT_PROBE")
        if probe:
            QTimer.singleShot(0, lambda: self._probe_local(probe))

    # ---------- 排障日志 ----------
    def _log(self, text):
        """只在设了 FLANDRE_VOICE_LOG=1 时写盘：热键不灵的时候靠它看事实。"""
        if self._log_path is None:
            return
        try:
            stamp = time.strftime("%H:%M:%S")
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write("%s %s\n" % (stamp, text))
        except OSError:
            self._log_path = None

    def _probe_local(self, path):
        text, err = _transcribe_local(path)
        for _ in range(20):                 # 钩子是另开的线程，等它装好再报
            if self._hooked or not self._ready():
                break
            time.sleep(0.05)
        try:
            (Path(data_manager.DATA_DIR) / "_stt_probe.txt").write_text(
                "engine=%s err=%s claim=%s hook=%s hotkey=%s text=%s" % (
                    self._engine(), err, self._claimed, self._hooked,
                    self._cfg.get("hotkey"), text),
                encoding="utf-8")
        except OSError:
            pass

    # ---------- 开关 ----------
    def set_hwnd(self, hwnd):
        """系统级热键要一个窗口句柄：占住这个键之后，别的程序（含全屏游戏）就抢不走。"""
        self._hwnd = int(hwnd or 0)

    def configure(self, cfg=None):
        """按设置开/关热键轮询。没开开关、没有本地模型、键名不认识 → 定格不启动。"""
        self._cfg = dict(cfg or {})
        self._held = False
        self._last_down = None
        self._engine_cache = None
        self._claim()
        self._hook_sync()
        if self._ready() and not _mock():
            self._timer.start()
        else:
            self._timer.stop()
        self._log("configure ready=%s engine=%s claim=%s hook=%s hotkey=%s enabled=%s hwnd=%s" % (
            self._ready(), self._engine(), self._claimed, self._hooked,
            self._cfg.get("hotkey"), self._cfg.get("enabled"), self._hwnd))

    def _claim(self):
        """跟系统把这个键「占住」（RegisterHotKey）。

        好处：游戏/别的软件把它当快捷键用的时候，键会先给我们，不会被吞掉；
        代价：占着的时候这个键在别的程序里就不灵了（推着说话本来也不该灵）。
        只有带主键的组合能注册；改设置就重注册，关掉就还回去。
        """
        self._release()
        if user32 is None or not self._hwnd or not self._ready():
            return
        mods, vk = self._vk()
        if not vk:
            return                        # 只有修饰键（Ctrl+Shift 这种）没法注册，退回轮询
        flags = MOD_NOREPEAT
        for mod in mods:
            flags |= MOD_FLAGS.get(mod, 0)
        self._claimed = bool(user32.RegisterHotKey(self._hwnd, HOTKEY_ID, flags, vk))

    def _release(self):
        if self._claimed and user32 is not None and self._hwnd:
            user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
        self._claimed = False

    # ---------- 低级键盘钩子 ----------
    def _hook_sync(self):
        """够格听键就装钩子，不够格就卸掉。"""
        want = (user32 is not None and HOOKPROC is not None
                and self._ready() and not _mock())
        if want and not self._hooked and self._hook_thread is None:
            self._hook_start()
        elif not want and self._hook_thread is not None:
            self._hook_stop()

    def _hook_start(self):
        self._pressed = set()
        self._key_down = False
        self._hook_thread = threading.Thread(
            target=self._hook_loop, name="fl-hotkey", daemon=True)
        self._hook_thread.start()

    def _hook_stop(self):
        tid = self._hook_tid
        self._hooked = False
        self._key_down = False
        self._hook_thread = None
        if user32 is not None and tid:
            user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)   # 让它自己退出消息循环

    def _hook_loop(self):
        """钩子线程：装 WH_KEYBOARD_LL，然后原地跑消息循环（钩子回调靠它分发）。"""
        self._hook_tid = int(kernel32.GetCurrentThreadId())
        proc = HOOKPROC(self._hook_key)
        self._hook_proc = proc                 # 必须留引用，被回收会直接崩
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0)
        if not self._hook:
            self._hook_tid = 0
            self._hook_thread = None
            return
        self._hooked = True
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._hooked = False
        self._key_down = False
        self._hook_tid = 0

    def _hook_key(self, code, wparam, lparam):
        """每次按键都过这儿：只记状态，绝不吞键（永远 CallNextHookEx 放行）。"""
        if code >= 0:
            try:
                kb = ctypes.cast(lparam, ctypes.POINTER(_KbdllHook)).contents
                vk = int(kb.vkCode)
                self._hook_seen = time.monotonic()
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    self._pressed.add(vk)
                elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                    self._pressed.discard(vk)
                key = self._vk()
                if key is not None:
                    mods, main = key
                    self._key_down = (self._held_any(main) if main else True) and \
                        all(self._held_any(m) for m in mods)
            except Exception:          # 钩子回调里绝不能抛
                pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _held_any(self, vk):
        """这个键（左右不分的那种码）按着没有：钩子记的是左右分开的码。"""
        if vk in self._pressed:
            return True
        return any(raw in self._pressed for raw in MOD_RAW.get(vk, ()))

    def listening(self):
        """现在是不是在听热键（自检用）。"""
        return self._ready()

    def press(self):
        if self._held:
            return
        self._held = True
        self._begin()

    def release(self):
        if not self._held:
            return
        self._held = False
        self._finish()

    def _pick_engine(self, cfg):
        """现在用哪个引擎：本地模型在就用本地；没有模型、但旧配置里还留着地址，才走在线。"""
        if local_files() is not None:
            return "local"
        return "online" if str(cfg.get("stt_base_url") or "").strip() else ""

    def _engine(self, cfg=None):
        if cfg is not None:
            return self._pick_engine(cfg)
        if getattr(self, "_engine_cache", None) is None:
            self._engine_cache = self._pick_engine(self._cfg)
        return self._engine_cache

    def _ready(self):
        if user32 is None:
            return False
        if not self._cfg.get("enabled"):
            return False
        if not self._engine():
            return False
        return self._vk() is not None

    def _vk(self):
        """设置里的说话键 → (修饰键元组, 主键 VK)；不认识 / 没填返回 None。"""
        return parse_hotkey(self._cfg.get("hotkey"))

    # ---------- 轮询 ----------
    def _poll_down(self, key):
        """老老实实问系统：主键（如果有）和所有修饰键都按着吗。"""
        mods, vk = key
        if vk and not (user32.GetAsyncKeyState(vk) & 0x8000):
            return False
        for mod in mods:
            if not (user32.GetAsyncKeyState(mod) & 0x8000):
                return False
        return True

    def _down(self, key):
        """两路取「或」：轮询说按着就算按着，钩子说按着也算。

        钩子更准（不看焦点、输入法吞不掉），轮询是它被系统悄悄摘掉时的兜底；
        要松手得两边都不按——但钩子两秒没动静就当它死了，别让松手卡在这儿。
        """
        if self._poll_down(key):
            return True
        if not (self._hooked and self._key_down):
            return False
        return time.monotonic() - self._hook_seen < 2.0

    def _poll(self):
        key = self._vk() if self._ready() else None
        if key is None:
            return
        down = self._down(key)
        if down != self._last_down:
            self._last_down = down
            self._log("down=%s hooked=%s" % (down, self._hooked))
        if down and not self._held:
            self.press()
        elif not down and self._held:
            self.release()
        elif self._rec is not None and \
                time.monotonic() - self._started >= config.VOICE_MAX_SECONDS:
            self._finish()        # 说太久了：截断；键还按着呢，不重开

    # ---------- 录 ----------
    def _begin(self):
        if not self._ready() or self._rec is not None:
            return
        rec = self._rec_start()
        if rec is None:
            self.failed.emit("mic")
            return
        self._rec = rec
        self._started = time.monotonic()
        self.recording.emit(True)

    def _finish(self):
        rec = self._rec
        if rec is None:
            return
        self._rec = None
        path, seconds = self._rec_stop(rec)
        self.recording.emit(False)
        if path is None:
            self.failed.emit("mic")
            return
        if seconds < config.VOICE_MIN_SECONDS:
            try:
                Path(path).unlink()      # 误触：太短了，直接丢
            except OSError:
                pass
            self.failed.emit("short")    # 只是让桌面把闭眼/转圈收掉，不吭声
            return
        self._stt(path)

    def _rec_start(self):
        if _mock():
            return ("mock", None)
        if _mci("open new type waveaudio alias %s" % MCI_ALIAS) == 0:
            _mci("set %s time format ms bitspersample 16 channels 1 samplespersec %d"
                 % (MCI_ALIAS, config.VOICE_SAMPLE_RATE))
            if _mci("record %s" % MCI_ALIAS) == 0:
                return ("mci", None)
            _mci("close %s" % MCI_ALIAS)
        return self._wave_start()        # MCI 不通：退 waveIn* 那一套

    def _rec_stop(self, rec):
        kind = rec[0]
        if kind == "mock":
            return self._mock_wav()
        if kind == "mci":
            path = self._wav_path()
            ok = _mci('save %s "%s"' % (MCI_ALIAS, path)) == 0
            _mci("close %s" % MCI_ALIAS)
            if not ok or not path.exists():
                return None, 0.0
            return path, _wav_seconds(path)
        return self._wave_stop(rec[1])

    # ---------- waveIn* 退路 ----------
    def _wave_start(self):
        if winmm is None:
            return None
        rate = config.VOICE_SAMPLE_RATE
        fmt = _WaveFormat(1, 1, rate, rate * 2, 2, 16, 0)
        handle = ctypes.c_void_p()
        # WAVE_MAPPER = -1 / CALLBACK_NULL = 0：不给回调，靠 dwBytesRecorded 收数据
        if winmm.waveInOpen(ctypes.byref(handle), 0xFFFFFFFF, ctypes.byref(fmt),
                            0, 0, 0) != 0:
            return None
        size = int(rate * 2 * config.VOICE_MAX_SECONDS) + 8192
        buf = ctypes.create_string_buffer(size)
        hdr = _WaveHdr()
        hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
        hdr.dwBufferLength = size
        if winmm.waveInPrepareHeader(handle, ctypes.byref(hdr),
                                     ctypes.sizeof(hdr)) != 0:
            winmm.waveInClose(handle)
            return None
        if winmm.waveInAddBuffer(handle, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0 \
                or winmm.waveInStart(handle) != 0:
            winmm.waveInUnprepareHeader(handle, ctypes.byref(hdr),
                                        ctypes.sizeof(hdr))
            winmm.waveInClose(handle)
            return None
        return ("wave", (handle, hdr, buf))

    def _wave_stop(self, state):
        handle, hdr, buf = state
        winmm.waveInStop(handle)
        winmm.waveInReset(handle)
        got = int(hdr.dwBytesRecorded)
        winmm.waveInUnprepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
        winmm.waveInClose(handle)
        if got <= 0:
            return None, 0.0
        path = self._wav_path()
        try:
            Path(path).write_bytes(_wav_bytes(buf.raw[:got]))
        except OSError:
            return None, 0.0
        return path, got / float(config.VOICE_SAMPLE_RATE * 2)

    # ---------- 文件 ----------
    def _wav_path(self):
        path = Path(data_manager.DATA_DIR) / "_voice_tmp.wav"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass                          # 建不出来就让它后面 save 失败、走 failed 提示
        return path

    def _mock_wav(self):
        """自检用：一段 16k 单声道静音，够过 0.6 秒门槛。"""
        path = self._wav_path()
        try:
            Path(path).write_bytes(_wav_bytes(b"\x00\x00" * int(config.VOICE_SAMPLE_RATE * 0.8)))
        except OSError:
            return None, 0.0
        return path, 0.8

    # ---------- 识别 ----------
    def _stt(self, path):
        if _mock():
            self.heard.emit(MOCK_TEXT)
            return
        cfg = dict(self._cfg)
        threading.Thread(target=self._stt_worker, args=(cfg, path),
                         daemon=True).start()

    def _stt_worker(self, cfg, path):
        try:
            try:
                if self._engine(cfg) == "local":
                    text, err = _transcribe_local(path)
                else:
                    text, err = _transcribe(cfg, path)
            except Exception:             # 线程里炸了别把整个程序带走
                text, err = "", "net"
            # 认完了就把录音删掉：这是用户机器上的音频，不该留在 data\ 里
            try:
                Path(path).unlink()
            except OSError:
                pass                      # 删不掉（被杀毒锁住之类）不影响这次说话
        finally:
            if text:
                self.heard.emit(text)
            else:
                self.failed.emit(err or "stt")
