"""语音热键自检：只看设置和按键，不录音、不联网、不改任何文件。

双击 工具\\语音热键自检.bat 运行。看到「按下了」就说明 Windows 能把热键交给她。
"""
import ctypes
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config                                  # noqa: E402
from voice import _mock, local_files, parse_hotkey   # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

cfg = {}
try:
    data = json.loads((config.DATA_DIR / "settings.json").read_text(encoding="utf-8"))
    cfg = data.get("voice") or {}
except (OSError, ValueError):
    print("读不到 data\\settings.json（先在设置页保存一次就行）")

hotkey = str(cfg.get("hotkey") or "F8").strip() or "F8"
models = local_files()
key = parse_hotkey(hotkey)

print("=========== 语音热键自检 ===========")
print("说话键：%s（%s）" % (hotkey, "认识" if key else "不认识 —— 回设置页重录一次"))
if key:
    print("占键：%s" % ("系统层面占住（别的程序抢不走）" if key[1]
                        else "只有修饰键，占不住 —— 输入法/游戏的快捷键会先吃掉它，"
                             "建议录成 Ctrl+Shift+F8 这种带主键的"))
print("语音开关：%s" % ("开" if cfg.get("enabled") else "关着 —— 她不会理这个键"))
print("本地模型：%s" % (("在（%s）" % config.STT_MODEL_DIR) if models
                        else "没有 —— %s 里缺 model*.onnx 或 tokens.txt" % config.STT_MODEL_DIR))

if cfg.get("enabled") and not models:
    print("\n开关开着，但本地模型不在 —— 程序里她不会听热键（重装/解压时别漏 model 目录）。")

if _mock():
    print("\n（FLANDRE_VOICE_MOCK=1 开着，热键轮询不会启动，先关掉这个环境变量）")
    sys.exit(0)

if key:
    print("\n下面 10 秒内，按住 %s 别松，再松开。不录音，只是看按键。" % hotkey)
    held = False
    downs = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < 10.0:
        mods, vk = key
        now = all(bool(user32.GetAsyncKeyState(m) & 0x8000) for m in mods)
        if vk:
            now = now and bool(user32.GetAsyncKeyState(vk) & 0x8000)
        t = time.monotonic() - t0
        if now and not held:
            held = True
            downs += 1
            print("  [%.1f 秒] 按下了" % t)
        elif not now and held:
            held = False
            print("  [%.1f 秒] 松开了（这一段在程序里就当成一句话）" % t)
        time.sleep(0.05)

    print("")
    if downs:
        print("看得到按键：热键轮询没问题（共 %d 次）。" % downs)
    else:
        print("十秒里一次都没看到 %s。可能是：1) 按的键跟上面写的不一样；"
              "2) 这个键被别的程序独占了；3) 键盘/输入法的问题。换个键再试一次。"
              % hotkey)
