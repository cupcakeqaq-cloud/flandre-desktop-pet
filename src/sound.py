# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""任务完成音效。

只用标准库 winsound（Windows 自带），**不引入 QtMultimedia**——
打包后的 `_internal` 里没有 Qt6Multimedia，装了会白白涨体积。

2026-10-08 第七批：改用 `SND_FILENAME | SND_ASYNC` 按路径播放。
以前用 `SND_MEMORY | SND_ASYNC` 是**错的**：winsound 实测直接抛
`RuntimeError: Cannot play asynchronously from memory`，而异常又被
`except Exception` 静默吞掉，所以「完成音效」一直没响过。
SND_FILENAME 由系统自己读文件、自己回收，不需要缓存字节、也不需要
持引用 + QTimer 延迟释放。

音效文件来自用户放在 `芙兰\\sound\\` 的两个 wav：
  tada.wav      单个任务完成（专注时段结束 / 倒计时归零 / 待办勾选完成）
  TADA (2).wav  番茄钟整组（全部循环）做完
"""

try:
    import winsound
except ImportError:                      # 非 Windows 平台：静默降级
    winsound = None

from config import SOUND_DIR

TASK_DONE = "tada.wav"
CYCLE_DONE = "TADA (2).wav"

_available = None


def _probe():
    global _available
    if _available is None:
        _available = bool(winsound) and SOUND_DIR.is_dir()
    return _available


def play(name):
    """异步播放，出错一律静默（没声音不该影响桌宠运行）。"""
    if not _probe():
        return
    path = SOUND_DIR / name
    if not path.is_file():
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def task_done():
    """单个任务完成 → tada.wav"""
    play(TASK_DONE)


def cycle_done():
    """番茄钟整组做完 → TADA (2).wav"""
    play(CYCLE_DONE)
