# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

import random
import time

_dialogue = None


def _ensure():
    global _dialogue
    if _dialogue is None:
        from data_manager import load_dialogue
        _dialogue = load_dialogue()


def _nickname():
    from data_manager import load_settings
    return load_settings().get("nickname", "你") or "你"


def _fmt(text, ctx):
    """填占位符；填不了就原样返回（和 pick() 一个脾气）。"""
    if not isinstance(text, str):
        return text
    try:
        return text.format(**ctx)
    except Exception:
        return text


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
        ctx["nickname"] = _nickname()
    return _fmt(line, ctx)


def pick_choice():
    """随机取一个「带选项」的对话 dict（{line, options:[{label, reply}]}），无则返回 None。

    选项文字是直接画在气泡按钮上的，既不经过 pick()、也不经过 pet_window._apply_nickname，
    所以这里就得把占位符填掉，否则按钮上会露出字面的 {nickname}。
    """
    _ensure()
    choices = _dialogue.get("choices")
    if not choices:
        return None
    ch = random.choice(choices)
    if not isinstance(ch, dict):
        return None
    ctx = {"nickname": _nickname()}
    out = dict(ch)
    out["line"] = _fmt(ch.get("line", ""), ctx)
    opts = []
    for o in ch.get("options") or []:
        if isinstance(o, dict):
            o = dict(o)
            o["label"] = _fmt(o.get("label", ""), ctx)
            o["reply"] = _fmt(o.get("reply", ""), ctx)   # reply 之后还会过 _apply_nickname，幂等
        opts.append(o)
    out["options"] = opts
    return out


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
