import sys
from pathlib import Path

APP_NAME = "芙兰朵露"


def app_dir() -> Path:
    # 打包成 exe 后，资源与数据都在 exe 同级目录；开发时则是工作区根目录。
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = app_dir()
TEX_DIR = APP_DIR / "贴图"
DATA_DIR = APP_DIR / "data"
COLLECT_DIR = APP_DIR / "收藏"
FONT_DIR = APP_DIR / "font"
SOUND_DIR = APP_DIR / "sound"

STAND_DIR = TEX_DIR / "站立"
RUN_DIR = TEX_DIR / "奔跑"
PICK_DIR = TEX_DIR / "拎起"
REST_DIR = TEX_DIR / "休息"
ICON_PATH = TEX_DIR / "icon.ico"

# 显示尺寸（源图 1000x1000 等比缩放为方形）
DISPLAY_SIZE = 240
SCALE = DISPLAY_SIZE / 1000.0

# 拎起时「右翅尖端」锚点（源图坐标），该点对准鼠标指针
WING_ANCHOR = (690, 70)

# 贴图底部留白补偿：整体下移，消除「悬空」感
GROUND_OFFSET = 3

# 落地（拎起\5.png）时窗口整体下移，消除「悬空」感
# 起身/切到别的状态时自动复位，避免一直陷进任务栏
LAND_OFFSET_PX = 7

# 「被拎起」1.png / 2.png 整体右移（显示像素），修正翅膀锚点带来的视觉偏移
# 只挪贴图、不动 WING_ANCHOR；镜像帧会自动取反
PICK_FRAME_DX = 2

# 赠礼（拖放文件）单次允许的总量上限
GIFT_MAX_BYTES = 100 * 1024 * 1024       # 100 MiB（一次拖放所有条目累加）

# UI 主色
UI_COLOR = "#836953"

# 任务完成时的开心表情（站立 4.png）保持时长；同时会刷新气泡，所以两者取大值
DONE_MOOD_SECONDS = 6.0

# 主循环帧率
TICK_MS = 33                             # 常规约 30fps
FALL_TICK_MS = 16                        # 下坠期间 60fps（只在坠落状态生效）

# 时序（秒）
BUBBLE_AUTO_HIDE = 5.0
RUN_SPEED_PX = DISPLAY_SIZE * 2          # 每秒两个身位
RUN_FRAME_INTERVAL = 0.15                # 奔跑两帧切换间隔
RUN_MIN_SECONDS = 10.0
RUN_MAX_SECONDS = 60.0

# 挣扎（「被拎起」状态）
STRUGGLE_SWITCH = 1.0                    # 拎起后多久切换 2.png
STRUGGLE_ACCEL_END = 5.0                 # 由慢到快、加速至最快所用时间
STRUGGLE_SLOW_END = 7.0                  # 最快后「稍微变慢」结束的时刻
STRUGGLE_FAST = 0.15                     # 最快时的贴图切换间隔
STRUGGLE_SLOW = 0.28                     # 稍微变慢后的贴图切换间隔
STRUGGLE_RANDOM_MIN = 0.15               # 随机变快阶段的间隔下限
STRUGGLE_RANDOM_MAX = 0.35               # 随机变快阶段的间隔上限
STRUGGLE_RANDOM_HOLD = (0.8, 2.0)        # 随机阶段每隔多久重新抽一次速度

# 坠落（松手 → 拎起\3.png → 拎起\4.png → 落地 拎起\5.png）
FALL_NEAR_GROUND = DISPLAY_SIZE / 3.0    # 距任务栏不足该距离时切「下坠」帧
THROW_MIRROR_MIN_VX = 40.0               # 向右甩出速度超过该值则整段坠落镜像朝右
FALL_RECOVER = 2.0                       # 倒地(拎起\5.png)保持时长，之后起身站立

# 走路（站立态随机走两步，复用奔跑贴图，速度与切帧都比奔跑慢）
WALK_SPEED_PX = DISPLAY_SIZE             # 每秒一个身位（奔跑的一半）
WALK_FRAME_INTERVAL = 0.30               # 贴图切换间隔（奔跑的 2 倍，看起来是走不是跑）
WALK_MIN_SECONDS = 1.0                   # 每次走 1~2 个身位
WALK_MAX_SECONDS = 2.0
WALK_CHANCE = 0.015                      # 站立时每秒判定一次的概率（刻意压低）

# 休息（无操作打盹）：最后一次用户交互（左键点击 / 拖拽拎起）之后满这么久没动静就坐下打盹
# 想快速测打盹：把 REST_IDLE_SECONDS 临时改成 5.0，测完改回来
REST_IDLE_SECONDS = 15 * 60.0             # 固定 15 分钟，不分昼夜
REST_GRACE_SECONDS = 10.0                 # 到点时若在奔跑/走路：最多再等这么久
REST_WAKE_LIMIT = 3                       # 打盹中被点醒几次就直接起身（不然一直点一直坐着）

DRAG_THRESHOLD = 8                       # 点击/拖拽判定阈值（像素）

# 主动说话
ACTIVE_TALK_MIN = 40                     # 主动闲聊间隔下限（秒）
ACTIVE_TALK_MAX = 120                    # 主动闲聊间隔上限（秒）
ACTIVE_IDLE_CHANCE = 0.75                # 定时器到点时抽到闲聊的概率（其余是季节问候）
ACTIVE_SEASON_CHANCE = 0.08              # 定时器到点时抽到季节问候的概率
CLICK_IDLE_CHANCE = 0.25                 # 左键点击时抽到闲聊（而非短应答）的概率
CLICK_SEASON_CHANCE = 0.05               # 左键点击时抽到季节问候的概率
