# -*- coding: utf-8 -*-
"""把 贴图/ 里的所有角色状态离线渲染成透明底 MOV（QuickTime RLE + alpha），供宣传片剪辑。

用法（工作区根目录）：
    .venv\\Scripts\\python.exe 工具\\导出宣传素材.py

输出：宣传素材\\*.mov + 宣传素材\\素材清单.md
依赖：Pillow；ffmpeg 依次找 环境变量 FFMPEG、工具\\ffmpeg\\ffmpeg.exe、.tmp\\ffmpeg\\ffmpeg.exe、PATH。

渲染参数全部读 src/config.py，动作时序照抄 src/pet_window.py：
站立/说话/表情、走路、奔跑、打盹、被拎起挣扎、坠落、点击压扁回弹、语音转圈。
程序里窗口只有 240x240（缩到 24% 显示），这里按贴图原始 1000x1000 出图，剪辑里缩放使用即可。
"""
from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import config  # noqa: E402  只读常量，不启动 Qt

W = 1000                      # 输出画布 = 贴图原始尺寸
FPS = 30                      # 与程序主循环 TICK_MS=33 一致
OUT_DIR = ROOT / "宣传素材"
PICK_DX = int(round(config.PICK_FRAME_DX / config.SCALE))   # 240 逻辑像素 → 1000 画布
TREMBLE = config.TREMBLE_PX / config.SCALE
SPIN = int(round(config.VOICE_SPIN_SIZE / config.DISPLAY_SIZE * W))
SPIN_X = int(round(W * config.VOICE_SPIN_X - SPIN / 2))
SPIN_Y = int(round(W * config.VOICE_SPIN_Y))
SPIN_STEP = config.VOICE_SPIN_MS / 1000.0

S1 = ("站立/1.png", False, 0)     # 站立
S2 = ("站立/2.png", False, 0)     # 说话（张嘴）
S3 = ("站立/3.png", False, 0)     # 生气
S4 = ("站立/4.png", False, 0)     # 星星眼
S5 = ("站立/5.png", False, 0)     # 闭眼
S6 = ("站立/6.png", False, 0)     # 流汗
R1L = ("奔跑/1.png", False, 0)
R2L = ("奔跑/2.png", False, 0)
R1R = ("奔跑/1.png", True, 0)
R2R = ("奔跑/2.png", True, 0)
P1 = ("拎起/1.png", False, PICK_DX)
P2 = ("拎起/2.png", False, PICK_DX)
F1L = ("拎起/3.png", False, 0)
F2L = ("拎起/4.png", False, 0)
LDL = ("拎起/5.png", False, 0)
F1R = ("拎起/3.png", True, 0)
F2R = ("拎起/4.png", True, 0)
LDR = ("拎起/5.png", True, 0)
D1 = ("休息/1.png", False, 0)     # 打盹被打扰的嫌弃脸
D2 = ("休息/2.png", False, 0)     # 闭眼打盹


def frames(seconds: float) -> int:
    return max(1, int(round(seconds * FPS)))


# ---------- 贴图加载 / 变换（照抄 pet_window._load_frame 与 paintEvent 的算法） ----------
_cache = {}


def load(spec):
    if spec in _cache:
        return _cache[spec]
    rel, mirrored, dx = spec
    img = Image.open(str(config.TEX_DIR / rel)).convert("RGBA")
    if mirrored:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        dx = -dx                       # 镜像后「右移」要取反，见 _load_frame
    if dx:
        img = offset(img, dx)
    _cache[spec] = img
    return img


def offset(img, dx, dy=0):
    if not dx and not dy:
        return img
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy))
    return out


def squash(img, k, wob):
    """压扁/颤抖：底边为锚、逐行 1:1 拷贝（不重采样），与 paintEvent 同一套做法。"""
    if abs(k) < 1e-3 and abs(wob) < 1e-3:
        return img
    img = offset(img, int(round(wob)))
    if abs(k) < 1e-3:
        return img
    s = 1.0 - (1.0 - config.SQUASH_SCALE_Y) * k
    if s <= 0.05:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    stride = W * 4
    top = W - int(round(W * s))
    raw = img.tobytes()
    out = bytearray(W * stride)
    for dy in range(top, W):
        srow = int(round((dy - top) / s))
        srow = 0 if srow < 0 else (W - 1 if srow >= W else srow)
        out[dy * stride:(dy + 1) * stride] = raw[srow * stride:(srow + 1) * stride]
    return Image.frombytes("RGBA", (W, W), bytes(out))


_spin = {}


def spin_frame(n):
    if n not in _spin:
        img = Image.open(str(config.VOICE_SPIN_DIR / f"{n}.png")).convert("RGBA")
        img = img.convert("RGBa").resize((SPIN, SPIN), Image.LANCZOS).convert("RGBA")
        _spin[n] = img
    return _spin[n]


def out_back(t):
    # QEasingCurve::OutBack，default amplitude 1.70158
    t -= 1.0
    return 1.0 + 2.70158 * t * t * t + 1.70158 * t * t


def compose(spec, k=0.0, wob=0.0, spin=None):
    canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    if spec is not None:
        canvas.paste(squash(load(spec), k, wob), (0, 0))
    if spin is not None:
        canvas.paste(spin_frame(spin), (SPIN_X, SPIN_Y))
    return canvas


# ---------- 各状态的时间线（数值全部来自 config.py / pet_window.py） ----------
def still(spec, seconds):
    n = frames(seconds)
    return ({"spec": spec} for _ in range(n))


def cycle(a, b, interval, seconds):
    n = frames(seconds)
    return ({"spec": a if int((i / FPS) / interval) % 2 == 0 else b} for i in range(n))


def struggle(seconds=7.0):
    """被拎起：0~1s 保持姿势，1~5s 由慢到快，5~7s 变慢，之后随机（源码 _tick_picked）。"""
    rng = random.Random(20261024)
    phase = 0.0
    interval = config.STRUGGLE_FAST
    next_roll = 0.0
    accel = max(config.STRUGGLE_ACCEL_END - config.STRUGGLE_SWITCH, 0.001)
    slow = max(config.STRUGGLE_SLOW_END - config.STRUGGLE_ACCEL_END, 0.001)
    for i in range(frames(seconds)):
        t = i / FPS
        if t < config.STRUGGLE_SWITCH:
            yield {"spec": P1}
            continue
        e2 = t - config.STRUGGLE_SWITCH
        if e2 < accel:
            iv = 0.5 + e2 / accel * (config.STRUGGLE_FAST - 0.5)
        elif e2 < accel + slow:
            iv = config.STRUGGLE_FAST + (e2 - accel) / slow * (config.STRUGGLE_SLOW - config.STRUGGLE_FAST)
        else:
            if t >= next_roll:
                interval = rng.uniform(config.STRUGGLE_RANDOM_MIN, config.STRUGGLE_RANDOM_MAX)
                next_roll = t + rng.uniform(*config.STRUGGLE_RANDOM_HOLD)
            iv = interval
        phase += (1.0 / FPS) / max(iv, 0.001)
        yield {"spec": P1 if int(phase) % 2 == 0 else P2}


def fall(mirrored, hold=0.35):
    """松开后坠落：从 1.5 身位高按源码重力（700，终速 800）下落，离地不足 1/3 身位换 4.png。"""
    f1, f2, land = (F1R, F2R, LDR) if mirrored else (F1L, F2L, LDL)
    dt = 1.0 / FPS
    y = 1.5 * config.DISPLAY_SIZE
    v = 0.0
    while True:
        yield {"spec": f2 if y <= config.FALL_NEAR_GROUND else f1}
        v = min(v + 700.0 * dt, 800.0)
        y -= v * dt
        if y <= 0:
            break
    for _ in range(frames(hold)):
        yield {"spec": land}


def rise(hold=2.0, angry=1.5):
    """落地趴 2 秒后起身，生气质问（站立\\3.png）。"""
    for _ in range(frames(hold)):
        yield {"spec": LDL}
    for _ in range(frames(angry)):
        yield {"spec": S3}


def tap():
    """轻点：按下换闭眼帧 + 压扁，按住不足 SQUASH_TAP_MS 直接压到底再弹回。"""
    t_press = 0.30
    t_release = t_press + 0.12
    press = config.SQUASH_MS / 1000.0
    rebound = config.SQUASH_REBOUND_MS / 1000.0
    total = t_release + max(rebound, config.BLINK_HOLD_SECONDS) + 0.2
    for i in range(frames(total)):
        t = i / FPS
        if t < t_press:
            yield {"spec": S1}
            continue
        if t < t_release:
            k = out_back((t - t_press) / press)
        elif t < t_release + rebound:
            k = 1.0 - out_back((t - t_release) / rebound)
        else:
            k = 0.0
        yield {"spec": S5 if t < t_release + config.BLINK_HOLD_SECONDS else S1, "k": k}


def hold():
    """按住不放：压到最扁 + 闭眼 + 7Hz 左右颤抖（源码 _press_fx / _on_wobble）。"""
    t_press = 0.20
    press = config.SQUASH_MS / 1000.0
    total = t_press + press + 1.0
    for i in range(frames(total)):
        t = i / FPS
        if t < t_press:
            yield {"spec": S1}
            continue
        if t < t_press + press:
            yield {"spec": S5, "k": out_back((t - t_press) / press)}
        else:
            el = t - t_press - press
            yield {"spec": S5, "k": 1.0,
                   "wob": TREMBLE * math.sin(2 * math.pi * config.TREMBLE_HZ * el)}


def voice(seconds=1.92):
    """按住语音键：闭眼 + 头顶转圈（12 格，每格 80ms）；1.92s = 转两圈，可无缝循环。"""
    for i in range(frames(seconds)):
        yield {"spec": S5, "spin": int((i / FPS) / SPIN_STEP) % 12 + 1}


def spin_only(seconds=0.96):
    yield from ({"spec": None, "spin": int((i / FPS) / SPIN_STEP) % 12 + 1}
                for i in range(frames(seconds)))


CLIPS = [
    ("01-站立-待机", "常驻", True, "站立待机（站立/1.png）", "pet_window.py:360-371", lambda: still(S1, 2.0)),
    ("02-站立-说话", "常驻", True, "说话状态，张嘴帧（站立/2.png）", "pet_window.py:369-370", lambda: still(S2, 2.0)),
    ("03-站立-生气", "表情", True, "少量点击/被惹火（站立/3.png）", "pet_window.py:682-684", lambda: still(S3, 2.0)),
    ("04-站立-开心", "表情", True, "星星眼，计时器完成/收到赠礼（站立/4.png）", "pet_window.py:403-406", lambda: still(S4, 2.0)),
    ("05-站立-闭眼", "表情", True, "按压/语音时的闭眼差分（站立/5.png）", "pet_window.py:723-725", lambda: still(S5, 2.0)),
    ("06-站立-流汗", "表情", True, "无语流汗（站立/6.png）", "brain.py:102-110", lambda: still(S6, 2.0)),
    ("07-走路-向左", "自动动作", True, "站立时随机走两步，复用奔跑两帧、0.30s 切帧", "pet_window.py:849-865",
     lambda: cycle(R1L, R2L, config.WALK_FRAME_INTERVAL, 2.0)),
    ("08-走路-向右", "自动动作", True, "同上，镜像朝右", "pet_window.py:849-865",
     lambda: cycle(R1R, R2R, config.WALK_FRAME_INTERVAL, 2.0)),
    ("09-奔跑-向左", "自动动作", True, "随机奔跑，0.15s 切帧", "pet_window.py:828-847",
     lambda: cycle(R1L, R2L, config.RUN_FRAME_INTERVAL, 2.0)),
    ("10-奔跑-向右", "自动动作", True, "同上，镜像朝右", "pet_window.py:828-847",
     lambda: cycle(R1R, R2R, config.RUN_FRAME_INTERVAL, 2.0)),
    ("11-打盹-睡着", "自动动作", True, "无操作 15 分钟后坐下打盹（休息/2.png）", "pet_window.py:983-995", lambda: still(D2, 3.0)),
    ("12-打盹-被吵醒", "互动", True, "打盹中被点，嫌弃脸（休息/1.png）", "pet_window.py:668-676", lambda: still(D1, 2.0)),
    ("13-拎起-挣扎", "互动", False, "被拎起：先停 1s，再由慢到快挣扎（两帧 + 翅膀位移补偿）", "pet_window.py:871-894",
     lambda: struggle()),
    ("14-坠落落地-向左", "互动", False, "松手坠落：3.png → 快贴地 4.png → 落地 5.png（原地姿势序列，位移在剪辑里做）",
     "pet_window.py:896-930", lambda: fall(False)),
    ("15-坠落落地-向右", "互动", False, "向右甩出时整段镜像", "pet_window.py:896-930", lambda: fall(True)),
    ("16-摔倒-趴地", "互动", False, "摔到地上保持 2 秒（落地帧整体陷下 7px 的桌面补偿未烘焙，摆位交给剪辑）",
     "pet_window.py:899-905", lambda: still(LDL, 2.0)),
    ("17-摔倒-爬起生气", "互动", False, "趴 2 秒 → 起身生气质问", "pet_window.py:899-905", lambda: rise()),
    ("18-点击-压扁回弹", "互动", False, "轻点一下：闭眼 + 压扁 + 松手过冲回弹", "pet_window.py:716-757", lambda: tap()),
    ("19-点击-按住颤抖", "互动", False, "按住不放：压到最扁并左右颤抖（循环播放即按住中）", "pet_window.py:772-783", lambda: hold()),
    ("20-语音-闭眼转圈", "互动", True, "说话/录音待机：闭眼 + 头顶 12 格转圈", "pet_window.py:1276-1352", lambda: voice()),
    ("21-加载-转圈叠加层", "叠加层", True, "只有头顶转圈（透明底，可单独叠在任意画面上）", "pet_window.py:1319-1352",
     lambda: spin_only()),
]


def find_ffmpeg():
    for cand in (os.environ.get("FFMPEG"), str(ROOT / "工具" / "ffmpeg" / "ffmpeg.exe"),
                 str(ROOT / ".tmp" / "ffmpeg" / "ffmpeg.exe")):
        if cand and Path(cand).is_file():
            return cand
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise SystemExit("找不到 ffmpeg：设 FFMPEG 环境变量，或放到 工具\\ffmpeg\\ffmpeg.exe")


def encode(ffmpeg, out, gen):
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{W}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "qtrle", "-pix_fmt", "argb", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    for item in gen:
        proc.stdin.write(compose(item.get("spec"), item.get("k", 0.0),
                                 item.get("wob", 0.0), item.get("spin")).tobytes())
        n += 1
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg 编码失败：{out.name}")
    return n


def main():
    ffmpeg = find_ffmpeg()
    OUT_DIR.mkdir(exist_ok=True)
    rows, total = [], 0
    for name, group, loop, desc, src, gen in CLIPS:
        out = OUT_DIR / f"{name}.mov"
        n = encode(ffmpeg, out, gen())
        size = out.stat().st_size
        total += size
        print(f"{name:<22} {n / FPS:5.2f}s  {size / 1e6:6.1f} MB")
        rows.append((name, group, loop, f"{n / FPS:.2f}s", f"{size / 1e6:.1f} MB", desc, src))
    md = ["# 宣传素材清单", "",
          f"由 `工具/导出宣传素材.py` 从源码与 `贴图/` 离线渲染生成：**{W}×{W} / {FPS}fps / "
          f"QuickTime Animation(qtrle) / 带 alpha 通道**，可直接拖进 PR / AE / 达芬奇 / 剪映。", "",
          f"共 {len(rows)} 条，合计 {total / 1e6:.0f} MB。程序里角色只显示 240×240，"
          f"剪辑时把素材缩到 24%（或直接缩放层）就是桌面上的实际观感。", "",
          "| 文件 | 分类 | 循环 | 时长 | 体积 | 说明 | 源码 |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, group, loop, dur, size, desc, src in rows:
        md.append(f"| {name}.mov | {group} | {'是' if loop else '否'} | {dur} | {size} | {desc} | `{src}` |")
    md += ["", "## 用法提示", "",
           "- 走路/奔跑是**原地循环**，位移请在剪辑软件里做（程序里是窗口移动，不是逐帧位移）。",
           "- 坠落是**原地姿势序列**（3→4→5），下落曲线请用剪辑软件的位置关键帧，"
           "或直接把 `14/15` 当作落地三段用。",
           "- `21-加载-转圈叠加层` 是纯透明底转圈，位置已经对齐帽子顶；"
           "如果直接叠在 `01` 上，与 `20` 的转圈位置完全一致。",
           "- 压扁/颤抖是按程序 paintEvent 的逐行 1:1 拷贝复刻的（不重采样），边缘不会发虚。",
           "- 全部为无损编码；如果剪辑软件不认 qtrle，用 ffmpeg 转 ProRes 4444：",
           "  `ffmpeg -i 输入.mov -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le 输出.mov`"]
    (OUT_DIR / "素材清单.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"完成：{len(rows)} 条，{total / 1e6:.0f} MB → {OUT_DIR}")


if __name__ == "__main__":
    main()
