import random
import time

_dialogue = None


def _ensure():
    global _dialogue
    if _dialogue is None:
        from data_manager import load_dialogue
        _dialogue = load_dialogue()


def pick(category, **ctx):
    """随机取一条指定类别的文案；支持 {name}/{days}/{hour}/{nickname} 等占位符。"""
    _ensure()
    lines = _dialogue.get(category)
    if not lines:
        return ""
    line = random.choice(lines)
    if not isinstance(line, str):
        return ""
    if "nickname" not in ctx:
        from data_manager import load_settings
        ctx["nickname"] = load_settings().get("nickname", "你") or "你"
    try:
        return line.format(**ctx)
    except Exception:
        return line


def pick_choice():
    """随机取一个「带选项」的对话 dict（{line, options:[{label, reply}]}），无则返回 None。"""
    _ensure()
    choices = _dialogue.get("choices")
    if not choices:
        return None
    return random.choice(choices)


def current_season():
    m = time.localtime().tm_mon
    if 3 <= m <= 5:
        return "spring"
    if 6 <= m <= 8:
        return "summer"
    if 9 <= m <= 11:
        return "autumn"
    return "winter"


def period_key():
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 13:
        return "noon"
    if 13 <= h < 17:
        return "afternoon"
    if 17 <= h < 23:
        return "evening"
    return "night"


def pick_season():
    if random.random() < 0.25:
        return pick("season_rain")
    return pick("season_" + current_season())
