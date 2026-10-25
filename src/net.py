# 著作权归 12あKa@被告人杯糕_ 所有；使用/二转/二改一律以 README.md（README.pdf）里的作者规则为准
# Copyright (C) 2026 12あKa@被告人杯糕_ —— 源代码由 deepseek-v4-flash 编写

"""在线模式的那一层网：聊天 / 测连接（语音转写留给第四轮）。

为什么单开线程：urllib 是阻塞的，在主线程里等一句回复，桌宠会整个僵住——
走路、眨眼、气泡全停。所以请求都在 daemon 线程里跑，结果用信号丢回主线程。
"""

import json
import os
import threading

from PySide6.QtCore import QObject, Signal

from data_manager import load_settings

MOCK_ENV = "FLANDRE_LLM_MOCK"      # 置 1 就不联网，自检和调试用
MAX_TEMPERATURE = 1.5              # 上限：再高模型开始胡言乱语（设置页也按这个封顶）
MOCK_TEXT = "嗯，在呢。"


def endpoint(base_url):
    """把用户填的地址补成完整的 chat/completions 地址。

    容忍末尾多余的「/」、只填到域名、自己已经写了 /v1、甚至整条都贴进来。
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):      # 已经写全了就别重复补
        return base
    return base + "/chat/completions"           # /v1 结尾的也走这儿，不会变 /v1/v1


def _http_error(code):
    if code in (401, 403):
        return "auth"
    if code == 402:
        return "billing"            # 硅基流动余额不足走这条（code 30001）
    if code == 429:
        return "rate"
    if 400 <= code < 500:
        return "bad"
    return "net"


def _current_llm(pet):
    settings = getattr(pet, "settings", None)
    if not isinstance(settings, dict):
        settings = load_settings()
    llm = settings.get("llm")
    return dict(llm) if isinstance(llm, dict) else {}


class Net(QObject):
    """所有网络请求的唯一出口。done(kind, text, err)，err 为空就是成功。"""

    done = Signal(str, str, str)        # kind, text, err

    def __init__(self, pet=None):
        super().__init__(pet)
        self.pet = pet
        self._lock = threading.Lock()    # 同时只放一个请求出去

    @property
    def busy(self):
        return self._lock.locked()

    # ---------- 对外的三个口子 ----------
    def chat(self, messages, kind="chat"):
        # kind 跟着 done 信号回来：聊天窗只认 "chat"，桌宠自己开口的是
        # "click"（被戳了一下）/ "active"（没人理，自己说话）
        self._spawn(kind, messages or [])

    def probe(self, cfg=None):
        # 探活只需要一次最便宜的请求：能拿回正常 JSON 就说明地址 / key / 网都通
        self._spawn("probe", [{"role": "user", "content": "在吗"}], cfg)

    def transcribe(self, path):
        # 第四轮才接语音转写，先明确回「没有这个功能」，别让调用方一直等
        self.done.emit("stt", "", "unsupported")

    # ---------- 内部 ----------
    def _spawn(self, kind, messages, cfg=None):
        thread = threading.Thread(
            target=self._worker,
            args=(kind, dict(cfg) if cfg else _current_llm(self.pet),
                  list(messages)),
            daemon=True)
        thread.start()

    def _worker(self, kind, cfg, messages):
        if not self._lock.acquire(blocking=False):
            return                       # 上一个还没回来：这次直接跳过，不排队
        try:
            text, err = self._request(kind, cfg, messages)
        except Exception:                # 线程里出什么岔子都别炸进程
            text, err = "", "net"
        finally:
            self._lock.release()
        self.done.emit(kind, text, err)

    def _request(self, kind, cfg, messages):
        # urllib 会连带拽进 email / argparse / http.client（约 40 ms），
        # 只在真要联网时才导，别让启动时白等——这是在 worker 线程里，不会卡界面
        import urllib.error
        import urllib.request

        if os.environ.get(MOCK_ENV) == "1":
            return ("" if kind == "probe" else MOCK_TEXT), ""

        url = endpoint(cfg.get("base_url"))
        key = str(cfg.get("api_key") or "").strip()
        model = str(cfg.get("model") or "").strip() or "deepseek-chat"
        if not url or not key:
            return "", "bad"

        # 温度夹在 0~1.5：文件里存着 2.0 也照旧发的话，deepseek-chat 会整段胡言乱语
        try:
            temp = float(cfg.get("temperature", 0.9))
        except (TypeError, ValueError):
            temp = 0.9
        temperature = min(MAX_TEMPERATURE, max(0.0, temp))

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": int(cfg.get("max_tokens", 300)),
            "stream": False,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + key},
            method="POST")
        timeout = float(cfg.get("timeout", 20))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            return "", _http_error(exc.code)
        except urllib.error.URLError as exc:
            reason = exc.reason
            return "", "timeout" if isinstance(reason, TimeoutError) else "net"
        except TimeoutError:
            return "", "timeout"
        except OSError:
            return "", "net"

        try:
            data = json.loads(raw.decode("utf-8", "replace"))
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return "", "bad"
        if kind == "probe":
            return "", ""
        return str(text or "").strip(), ""
