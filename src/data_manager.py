# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

import json
import threading

from config import DATA_DIR, CHAT_HISTORY, COLLECT_DIR, OLD_COLLECT_DIR

_lock = threading.Lock()

# 自定义类型的数量上限（两处各自最多 3 个）
MAX_CUSTOM_TYPES = 3

# 番茄钟上次使用的参数（记住用户习惯，下次打开就是上次的配置）
DEFAULT_POMODORO = {
    "focus": 25,
    "break": 5,
    "cycles": 4,
    "long_every": 4,
    "long_break": 15,
    "task_type": "",
}

DEFAULT_SETTINGS = {
    "nickname": "你",
    "bubble_offset": None,
    "bubble_duration": 5.0,
    # 番茄钟倒计时期间每秒刷新气泡（会临时抬高气泡自动隐藏时长）
    "live_bubble": True,      # 计时器运行中每秒刷新气泡里的剩余时间
    "ui_font": "source",      # "source"=内置思源黑体 / "system"=系统字体（需重启）
    "active_talk_interval": [40, 120],
    # 内置任务类型 / 事件类型（常量，UI 里只读）
    "task_types": ["学习", "工作", "读书", "写作"],
    "countdown_types": ["考试", "约会", "见面", "面试", "纪念日", "生日"],
    # 用户自定义类型（可保存 / 可删除，各自最多 MAX_CUSTOM_TYPES 个）
    "custom_task_types": [],
    "custom_countdown_types": [],
    "pomodoro": dict(DEFAULT_POMODORO),
    # 在线模式（聊天）。enabled + 地址 / key / 模型都填了才算在线
    "llm": {
        "enabled": False,
        "base_url": "https://api.deepseek.com",
        "api_key": "",
        "model": "deepseek-chat",
        "temperature": 0.9,
        "max_tokens": 300,
        "timeout": 20,
    },
    # 主动看你屏幕（这一批只用到 hide_in_fullscreen，其余留给后面）
    "watch": {"enabled": False, "cooldown_s": 600, "daily_cap": 100,
              "hide_in_fullscreen": True},
    # 语音（按住说话键说话，认字全在本机做；没有本地模型就完全不碰麦克风）
    "voice": {"enabled": False, "hotkey": "F8"},
}


def _migrate_collect_dir():
    # 2026-10-24 补充⑮：收藏夹改名成「芙兰的收藏」。老目录还在、新目录还没建，
    # 就整个 rename 过去（里面的赠礼跟着走）；rename 不行就留着，不删用户的东西。
    try:
        if OLD_COLLECT_DIR.is_dir() and not COLLECT_DIR.exists():
            OLD_COLLECT_DIR.rename(COLLECT_DIR)
    except OSError:
        pass


def ensure_dirs():
    _migrate_collect_dir()
    for d in (DATA_DIR, COLLECT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write_json(path, data):
    ensure_dirs()
    with _lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)


def load_settings():
    data = dict(DEFAULT_SETTINGS)
    saved = _read_json(DATA_DIR / "settings.json", {})
    if isinstance(saved, dict):
        data.update(saved)
    return data


def save_settings(settings):
    _write_json(DATA_DIR / "settings.json", settings)


# ---------- 自定义类型（任务类型 / 事件类型）----------
def _type_keys(kind):
    """kind: 'task' 或 'countdown' -> (内置键, 自定义键)"""
    if kind == "task":
        return "task_types", "custom_task_types"
    return "countdown_types", "custom_countdown_types"


def sanitize_types(items):
    """去空白、去重、保序、截断到上限。"""
    out = []
    for x in items or []:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= MAX_CUSTOM_TYPES:
            break
    return out


def get_custom_types(kind):
    base_key, custom_key = _type_keys(kind)
    settings = load_settings()
    builtin = [str(x) for x in settings.get(base_key, [])]
    # 内置列表里可能残留历史版本的「自定义」占位项，去掉
    builtin = [x for x in builtin if x != "自定义"]
    customs = sanitize_types(settings.get(custom_key, []))
    customs = [x for x in customs if x not in builtin]
    return builtin, customs


def set_custom_types(kind, items):
    base_key, custom_key = _type_keys(kind)
    settings = load_settings()
    builtin = [str(x) for x in settings.get(base_key, [])]
    builtin = [x for x in builtin if x != "自定义"]
    settings[custom_key] = [x for x in sanitize_types(items) if x not in builtin]
    save_settings(settings)
    return settings[custom_key]


def get_all_types(kind):
    builtin, customs = get_custom_types(kind)
    return builtin + customs


def load_dialogue():
    return _read_json(DATA_DIR / "dialogue.json", {})


def load_todos():
    return _read_json(DATA_DIR / "todos.json", [])


def save_todos(todos):
    _write_json(DATA_DIR / "todos.json", todos)


def load_countdown():
    return _read_json(DATA_DIR / "countdown.json", [])


def save_countdown(items):
    _write_json(DATA_DIR / "countdown.json", items)


# ---------- 聊天记录（在线模式） ----------
def _chat_path():
    # 用模块里的 DATA_DIR 拼，自检把 DATA_DIR 指到临时目录时也跟着走
    return DATA_DIR / CHAT_HISTORY.name


def load_chat_history():
    data = _read_json(_chat_path(), {})
    if not isinstance(data, dict):
        data = {}
    messages = data.get("messages")
    if not isinstance(messages, list):
        messages = []
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    return {
        "messages": [m for m in messages if isinstance(m, dict)],
        "usage": {str(k): int(v) for k, v in usage.items()
                  if isinstance(v, int) or str(v).isdigit()},
        "last_date": str(data.get("last_date") or ""),
    }


def save_chat_history(history):
    _write_json(_chat_path(), history)
