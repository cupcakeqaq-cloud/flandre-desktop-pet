# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

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
COLLECT_DIR = APP_DIR / "芙兰的收藏"
# 2026-10-24 补充⑮：收藏夹从「收藏」改名，老目录在启动时连内容一起搬过来（见 data_manager.ensure_dirs）
OLD_COLLECT_DIR = APP_DIR / "收藏"
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

# 弹出菜单：线性图标是代码画的（打包版没带 Qt6Svg），关掉就退回纯文字菜单
ICON_IN_MENU = True
MENU_ICON_COLOR = "#836953"
MENU_ICON_SIZE = 20          # 18 时描出来的番茄看不清细节，20 刚好

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

# 频繁点击：窗口内累计 CLICK_ANNOY_COUNT 次就生气（贴图切「站立\3.png」+ 一句不耐烦）
CLICK_ANNOY_COUNT = 5                    # 触发所需点击数（触发后重新计数）
CLICK_ANNOY_WINDOW = 3.0                 # 计数窗口（秒），窗口外的旧点击自动作废

# 点击回弹（按下压扁 + 松开弹回；鲸鱼插件是 scaleY(0.88) scaleX(1.05)，
# 这里只压纵向：横向一缩放，竖边像素会被重采样吃成半透明锯齿，所以放弃 1.05）
SQUASH_SCALE_Y = 0.88                    # 压扁时纵向压到
SQUASH_MS = 220                          # 按下压扁时长（鲸鱼插件 transition 0.22s 同款）
SQUASH_REBOUND_MS = 320                  # 松开弹回时长（比压下慢一点，过冲才看得见）
SQUASH_TAP_MS = 140                      # 按住不足这么久就直接压到底再弹（照 pressUp 的 tap 处理）
SQUASH_MASK_PAD = 7                      # 遮罩左右各放宽的像素（给颤抖留余量，防翅膀尖被切）
TREMBLE_PX = 2.0                         # 按住时的颤抖幅度（左右各几像素）
TREMBLE_HZ = 7.0                         # 按住时的颤抖频率
BLINK_HOLD_SECONDS = 0.5                 # 松开后闭眼 5.png 再留多久（约 0.5~0.8s）
NAP_WAKE_HOLD_MS = 5000                  # 打盹中按住多久才算被吵醒

# 在线模式（模型现编台词）：连点当作同一下 / 请求失败那句的冷却
AI_CLICK_DEBOUNCE = 0.4                  # 秒，距上一次点击不到这么久就忽略
AI_ERR_COOLDOWN = 60.0                   # 秒，「电波接收失败」60 秒内只播一次

# 全屏检测（比窗口矩形和显示器矩形，四边各允许差这么多像素）
FULLSCREEN_TOL = 2

# 桌面感知（activity.py）：只看前台程序的进程名 / 窗口标题 + 空闲时长，不截图
ACTIVITY_IDLE_SECONDS = 300              # 超过这么久没摸键鼠就算「人不在」（一次空闲只报一次）
ACTIVITY_ACTIVE_GAP = 60                 # 空闲不到这么久算「还在动」；连续工作只认连续的输入
ACTIVITY_STREAK_SECONDS = 50 * 60        # 连续有输入满这么久就催休息（想快速测：临时改 180）
ACTIVITY_STREAK_COOLDOWN = 30 * 60.0     # 「催休息」同类冷却（秒）
ACTIVITY_BACK_COOLDOWN = 3600.0          # 「你回来了」每小时最多一次（秒）
ACTIVITY_TITLE_MAX = 60                  # 窗口标题最多留这么多字（塞进提示词，别太长）
ACTIVITY_MOVE_SECONDS = 2.0              # 空闲不到 2 秒算「这会儿正在动键鼠」（判断猛操作还是只看）
# 「看你屏幕」这类后台活儿的节拍（毫秒）；宁可慢一点，别每帧都去问 Windows
ACTIVITY_TICK_MS = 3000
# 聊天记录（在线模式）
CHAT_HISTORY = DATA_DIR / "chat_history.json"

# 语音（按住热键说话 → 转文字 → 当用户输入交给她）。芙兰不出声，只回气泡
VOICE_TICK_MS = 30                 # 热键轮询间隔（30ms：手一按就抓到，资源几乎没差别）
VOICE_SAMPLE_RATE = 16000          # 16k 单声道 16bit：所有语音识别接口都吃这个
VOICE_MIN_SECONDS = 0.6            # 短于这个当误触，直接丢掉（不吭声）
VOICE_MAX_SECONDS = 60.0           # 按住超过这个就自动截断，不往接口里塞一分钟的废话
VOICE_WAIT_SECONDS = 20.0          # 松开之后最多等这么久：转圈久了要自己收，不能空转
# 头顶那个「大脑宕机」转圈（录音 + 等回答时转，12 张透明 PNG）
VOICE_SPIN_DIR = TEX_DIR / "加载"
VOICE_SPIN_SIZE = 64               # 画多大（240 的窗口里的逻辑像素）
VOICE_SPIN_X = 0.46                # 圆心横向位置（占窗口宽度的比例；0.46 = 帽尖正中）
VOICE_SPIN_Y = 0.00                # 上沿纵向位置（占窗口高度的比例；帽尖已在 3.8px，贴顶）
VOICE_SPIN_MS = 80                 # 每格停留多久（12 格转一圈约 1 秒）
# 本地离线识别（sherpa-onnx + 中文小模型）：模型放程序目录里，不塞进 exe
STT_MODEL_DIR = APP_DIR / "model" / "asr"
