# 芙兰 LLM 化 · 工作流提示词（5 个对话，可直接复制）

> 2026-10-23 · 配套设计文档：[2026-10-18-llm-chat-vision-design.md](2026-10-18-llm-chat-vision-design.md)
> 用法：**每开一个新对话，先整段复制 §0 通用块，再复制对应轮次的块**，一次只做一轮。
> 每轮结束必须写交接文档；不写就等于没做完。

---

## §0 通用块（每个对话都先贴这段）

```text
你是「芙兰桌宠」项目的执行者。项目根目录：C:\Users\CupCakeQAQ_\Desktop\芙兰
技术栈：Windows 10/11 + Python 3.12 + PySide6 + Pillow，PyInstaller onedir 打包。

开工前必须按顺序读完（别猜，读全文）：
1. 交接文档.md —— 至少「三、技术要点」「四、构建运行」「六、当前状态与待办」
2. docs\superpowers\specs\2026-10-18-llm-chat-vision-design.md —— 本项目的设计
3. 本轮要改的 src\*.py 文件全文

铁律：
- 只做本轮清单里的改动。清单外的"顺手优化"一律不做——用户说过「越修 bug 越多还不如不修」。
- 不新增第三方依赖（只用标准库 + 已有 PySide6 / Pillow / winsound）。要装包先停下来问我。
- 不在代码里写死任何 API key，不主动联网。
- 台词、界面文案必须口语、没有 AI 味；称呼一律写成 {nickname} 占位符。
- 用户靠双击用程序、不跑命令行：凡是给他跑的测试都要做成 GBK 编码的 .bat（参考 工具\界面自检.bat）。
- 改任何 .py 之后必须重新打包，否则用户双击到的是旧 exe。打包前先确认没有正在运行的 芙兰朵露.exe（旧进程会把旧 settings.json 写回去）。
- 每一步大改都要写进 交接文档.md（追加到「六、当前状态与待办 → 已完成」末尾，模板见文末）。

交付顺序（缺一不可，最后才报告）：
1 改代码
2 跑自检：& .venv\Scripts\python.exe 工具\ui_check.py
   —— 必须看到 SELFCHECK OK（段数 = 本轮要求）。注意它的退出码可能是 0xC0000409，看输出别看退出码。
3 冒烟：& .venv\Scripts\python.exe 工具\repack.py --smoke
4 原地换 exe：& .venv\Scripts\python.exe 工具\repack.py
5 记下新 芙兰朵露.exe 的字节数（Get-Item）
6 写交接文档（含上面的字节数、ui_check 段数、改了哪些函数）
7 回复我：只给三行结论——改了什么 / 怎么验 / 还剩什么。不要贴大段代码。
```

---

## §1 第二十批（对话 1/5）：双模式骨架 + 聊天窗 + 全屏隐藏

```text
本轮目标：让程序有「离线 / 在线」两种模式，在线时能打字聊天；顺手修掉全屏时桌宠悬空的 bug。

【必做 1】工具\repack.py 支持新增模块
现在 rebuild_pyz() 只重编译旧 TOC 里已存在的项目模块，新增的 src\*.py 打不进去。
改成：先按旧 TOC 重建（已有模块编译替换、其余原样搬运），再把 src\ 下「新增的 .py（除 main.py）」作为新条目追加进 PYZ。
必须沿用文件里已有的 toc_entries() / serialize_toc()，别自己拼字节。改完用 --check 验证能比对出新增模块。

【必做 2】src\config.py
新增常量：FULLSCREEN_TOL = 2（全屏判定像素容差）、ACTIVITY_TICK_MS = 3000；
CHAT_HISTORY = DATA_DIR / "chat_history.json"。

【必做 3】src\data_manager.py
DEFAULT_SETTINGS 追加三块（旧 settings.json 靠 load_settings 的 update 自动补齐）：
  "llm":   {"enabled": false, "base_url": "https://api.deepseek.com", "api_key": "",
            "model": "deepseek-chat", "temperature": 0.9, "max_tokens": 300, "timeout": 20}
  "watch": {"enabled": false, "cooldown_s": 600, "daily_cap": 100, "hide_in_fullscreen": true}
  "voice": {"enabled": false, "hotkey": "F8", "stt_base_url": "", "stt_api_key": "", "stt_model": "whisper-1"}
新增 load_chat_history() / save_chat_history()，结构：
  {"messages": [{"role": "user|assistant", "content": str, "ts": float, "active": bool}],
   "usage": {"YYYY-MM-DD": int}, "last_date": "YYYY-MM-DD"}
写盘沿用 _write_json 的 .tmp + replace 做法，加锁。

【必做 4】新建 src\net.py（约 200 行）
class Net(QObject)，信号 done = Signal(str, str, str)  # kind, text, err
  chat(messages)       —— POST {base_url}/chat/completions，Bearer key，OpenAI 兼容
  probe()              —— 测试连接
  transcribe(path)     —— 本轮先留空实现（返回 err="unsupported"），第四轮再写
要求：
- base_url 容错：去尾 /；用户填 https://api.deepseek.com 也自动补成 .../chat/completions；填了 /v1 就不重复补。
- 只用 urllib.request；threading.Thread(daemon=True) 发请求，结果用信号回主线程；主线程绝不阻塞。
- 同时只允许 1 个请求（内部 _busy 锁），超时用 llm.timeout 秒。
- err 归一化成这几个字符串之一："auth" / "rate" / "net" / "timeout" / "bad" / ""（空=成功）。
- 支持模拟：环境变量 FLANDRE_LLM_MOCK=1 时不开网络，直接回一句固定文本（自检要用）。

【必做 5】新建 src\chat_ui.py（约 180 行）
class ChatWindow(QDialog)：复用 theme.setup_dialog / theme.card_form / theme.QSS 一套，别自造样式。
布局：标题「和芙兰说话」+ 只读 QTextBrowser 记录 + QLineEdit + 「说」按钮；回车=发送；Esc=关闭。
行为：
- 发送 → 记录里追加「我：xxx」→ 调 pet.net.chat → 等信号（期间输入框置灰、按钮显示「芙兰在想…」）
- 收到 → 记录里追加「芙兰：xxx」→ pet.say(text) → 写 chat_history.json
- 失败（本轮简化）→ 记录里追加一行灰色小字「（电波不通）」；正式的错误台词留给第二十一批
- 提供 append_assistant(text, active=False)，供 pet_window 把芙兰主动说的话也写进记录（带「（主动）」标记也没关系，别难看就行）
- 关窗不中断请求

【必做 6】src\pet_window.py
- __init__：self.net = Net(self)；信号连到新方法 _on_ai_done(kind, text, err)
- 新方法 _llm_ready()：settings["llm"]["enabled"] 为真 且 base_url/api_key/model 三项非空
- contextMenuEvent 的 items 列表里，**仅当 _llm_ready() 时**在最前面插 ("聊天", "chat", self._menu_chat)
- _menu_chat：self.show_dialog("chat", lambda: ChatWindow(self))，复用现有非模态去重
- 新方法 _check_fullscreen()（ctypes，零依赖）：
    GetForegroundWindow → 排除自己 / Progman / WorkerW / Shell_TrayWnd →
    GetWindowRect 与 GetMonitorInfoW 的 rcMonitor 四边差 <= config.FULLSCREEN_TOL → 全屏
    同时要求该窗口没有 WS_CAPTION 样式，避免误判最大化的普通窗口
  挂到已有的 self.think（1 秒）里，每 3 次调一次；**不要新增 QTimer**。
- 进入全屏：self._fullscreen_hidden = True；若 isVisible() 就 self.hide()。
  注意：**不能调 hide_pet()**，它有托盘兜底会拒绝隐藏。
- 退出全屏：若 _fullscreen_hidden 且不是用户手动隐藏的，就 self.show() 回原位并清标记。
- 托盘手动「显示」（Tray.toggle）时清掉 _fullscreen_hidden，本次全屏不再自动隐藏。
- watch.hide_in_fullscreen 为假时整套不生效。

【必做 7】src\theme.py
_ICONS 里加 "chat"：30 点坐标系，照 tomato / folder 的 ("r"/"c"/"l", ...) 图元写法，做一个对话气泡（圆角方框 + 左下小尖角 + 三颗点）。20px 下必须能看清，不能糊成一团。

【必做 8】src\settings_dialog.py
照现有 _card(title, hint) 的写法加两张卡：
- 「对话模型」：启用开关 / base_url / api_key（QLineEdit setEchoMode Password）/ model / 温度 / 「测试连接」按钮（调 net.probe，结果用一行小字回显）
- 「芙兰看见你在干什么」：总开关 / 同类冷却（秒）/ 每日上限 / 全屏时隐藏我（勾选框）
_save() 里把 llm / watch 两组键写回 settings 并调用 pet.refresh_settings()；_reset() 一并回填。

【必做 9】工具\ui_check.py 加第 21 段
离线（默认 settings）时 ChatWindow 不被右键菜单项引用 / _llm_ready() 为假；
在线（直接改 pet.settings 内存）时 _llm_ready() 为真；
FLANDRE_LLM_MOCK=1 下 chat_history 读写 roundtrip 一致；
_check_fullscreen() 在无桌面环境下返回 False 且不抛异常；
设置对话框在含 llm 键的 settings 下能构造并保存。
自检总段数变成 21 段。

【不许碰】dialogue.json、番茄钟/倒计时/待办/倒数日、赠礼逻辑、气泡布局、任何台词文案。

【我怎么验收】
1 双击 exe：离线，右键菜单没有「聊天」，点芙兰还是老样子说话
2 设置里填好 base_url + key + model 保存 → 右键出现「聊天」→ 发「你好」→ 芙兰用气泡回一句，聊天窗里有记录
3 先点开一个网页按 F11 全屏 → 芙兰消失；退出全屏 → 回来，位置不变
4 把 key 删掉保存 → 菜单里「聊天」消失
```

---

## §2 第二十一批（对话 2/5）：在线模式接管闲聊 + 错误反应 + 删选项

```text
本轮目标：在线模式下，芙兰说话不再用 data\dialogue.json 的预设闲聊，改成模型现编；请求失败时给她一个专用反应。

【必做 1】新建 src\brain.py（约 200 行）
- build_messages(kind, ctx) -> list[dict]
  kind: "chat" / "click" / "active"
  人设：芙兰朵露·斯卡蕾特，495 岁、住在{nickname}电脑里的小吸血鬼，淘气但贴心；不能晒太阳；有翅膀但飞不起来。
  输出硬约束（必须写进 system）：
    1 只输出台词本身，不写动作、不写心理、不加括号或引号、不解释
    2 1~2 句，最多 40 字，口语，可以带语气词
    3 禁止书面句式（虽然…但是 / 由于…因此 / 首先 / 综上所述）
    4 称呼一律用 {nickname}
    5 上下文里会给你"主人屏幕上是什么"，用得上就提一句，不要硬提
- clean(text)：去首尾引号/星号/顿号；去掉（）【】括起来的舞台提示；按 。！？~ 切到最多 2 句，总长超 60 字就截断
- 节流：同类事件（同一个 kind + 同一个 activity 分类）冷却 settings["watch"]["cooldown_s"]，默认 600 秒；
  每日吐槽上限 settings["watch"]["daily_cap"]（100），计数用 chat_history.json 的 usage 当天计数；
  用户主动发的消息不算吐槽名额，但同样受"单飞"限制。
- 未配置 watch.enabled 时，上下文里**不要**出现窗口标题/进程名这一行。

【必做 2】src\pet_window.py 接管点击与主动说话
- _on_click：若 _llm_ready() 且 state 在 STAND/WALK/RUN：
    · 走"防抖 + 单飞"：距上次点击 < 400ms 的点击忽略；self._ai_busy 为真时只做按压回弹（已有 _press_fx/_end_bounce）不发请求
    · 点击立刻 _press_fx() + 马上 _end_bounce()（走 SQUASH_TAP_MS 的 tap 分支＝压到底再弹），视觉上就是"我在想"
    · 发 net.chat(brain.build_messages("click", 上下文))
    · **不再**调用 _pick_chat_line / pick_choice（在线模式没有选项按钮，也没有预设闲聊）
  REST / PICKED / FALL 保持原逻辑不变。
- _on_active_talk：在线模式下改成"事件驱动"——没有新事件就不说话；有事件（由第三批的 activity 提供）且过了冷却才说。
  本批先做成"每隔 10 分钟最多说一次的随机闲话"占位，第三批再接真实事件。
- _pick_chat_line / _on_option_chosen：**保留原样**给离线模式用，不要删。
- _on_ai_done：kind=="click"/"active" 且 err=="" → say(text)；err!="" → _on_ai_error()。
- 新方法 _on_ai_error()：
    · 60 秒冷却（self._ai_err_until），冷却内静默
    · sound.play("error.wav")（sound.py 已有 play()）
    · _press_fx() 后立刻 _end_bounce()（=按压回弹），并让闭眼帧 stand5 保持（跑完 tap 分支自然就是这个效果）
    · say("唉......电波貌似接收失败了，{nickname}去检查一下吧？")    ← 一字不改，注意是"接收"
    · 401/429 时在聊天窗里追加一行灰字说明
- show_live / timer_done_overlay / hourly / rest_wake / 计时器回执：**一行都不许改**（功能提示保留预设）。

【必做 3】src\chat_ui.py
在线模式下打开聊天窗时同步显示芙兰主动说的话：pet 每次 say 完（仅在线模式、且原因不是功能提示）调用 chat_window.append_assistant(text, active=True)。

【必做 4】工具\ui_check.py 加第 22 段
- FLANDRE_LLM_MOCK=1：模拟点击 → 走完 _on_ai_done → 气泡文本非空且来自 mock
- 连点 3 次（间隔 50ms）只发 1 次请求
- 模拟失败 3 次 → 只有 1 次播报（冷却生效），且台词里含「接收失败」
- 在线模式 say() 不产生选项按钮；离线模式仍然有
自检总段数变成 22 段。

【不许碰】dialogue.json 的任何一个字、计时器、待办、赠礼、气泡布局、气泡拖动。

【我怎么验收】
1 在线模式点芙兰：立刻压扁回弹，一两秒后气泡出现一句现编的话（不是 dialogue.json 里的）
2 快速连点 5 下：只回 1~2 句，不卡、不排队
3 把 key 改成错的再点：芙兰压一下、播 error.wav、说「唉......电波貌似接收失败了，xx 去检查一下吧？」，60 秒内不再重复
4 番茄钟跑完：完成音效 + 原有预设提示语，跟以前一样
5 离线模式：点她仍然是 dialogue.json 的台词，选项按钮也还在
```

---

## §3 第二十二批（对话 3/5）：桌面感知

```text
本轮目标：让芙兰"看见"你在干什么——打游戏夸操作/想一起玩，工作就监工，连续工作 50 分钟催休息。

【必做 1】新建 src\activity.py（约 160 行，纯 ctypes，零依赖）
每 config.ACTIVITY_TICK_MS（3 秒）采样一次：
  GetForegroundWindow → GetWindowTextW（标题，截断到 60 字）
  QueryFullProcessImageNameW（进程名，只取 basename，如 chrome.exe / GenshinImpact.exe）
  GetLastInputInfo（空闲秒数 = (GetTickCount() - dwTime) / 1000）
事件（用 QObject 信号抛给 pet_window）：
  activity_changed(app, title) —— 换了前台程序（同程序换窗口标题不算）
  idle_started(seconds)        —— 空闲超过 5 分钟
  active_streak(minutes)       —— 连续有输入 ≥ 50 分钟（期间没有 5 分钟以上空闲）
过滤：自己进程、Progman/WorkerW/Shell_TrayWnd、标题为空的窗口都不算。
"在打游戏还是在工作"**不在本地判断**，把 app + title 原样塞给模型，让模型自己说。

【必做 2】src\pet_window.py
- __init__ 里创建 self.activity = Activity(self)，接信号
- 收到 activity_changed → brain.build_messages("active", {...}) 前先过 brain 的冷却与每日上限；
  过了就发请求，回复走 say(text)
- idle_started → say(dialogue.pick("idle_back"))？不行——功能提示才用预设。
  这里改成让模型说一句"你回来了"，但**每小时最多 1 次**，别烦人。
- active_streak ≥ 50 分钟 → 让模型催休息（同类冷却 30 分钟）；这条永远允许，不受每日上限限制
- 全屏隐藏期间（_fullscreen_hidden）不发任何请求，也不弹气泡
- watch.enabled 为假时 Activity 不启动（省电，也别让人怀疑它偷看）

【必做 3】设置页
「芙兰看见你在干什么」卡里的总开关一旦打开，立刻生效（不用重启）：Activity.start()/stop()。
卡片下面加一行灰字说明：只读窗口标题和程序名，不截图、不上传画面。

【必做 4】工具\ui_check.py 加第 23 段
- Activity 在无桌面环境构造/采样不崩
- 冷却逻辑：同一 activity 连发 3 次事件只有第 1 次通过
- 每日上限：模拟 usage 已到 100 时不再通过
- 全屏隐藏状态下不产生请求
自检总段数变成 23 段。

【不许碰】_on_click 的防抖逻辑、错误反应、聊天窗、计时器、待办。

【我怎么验收】
1 开一局游戏玩 2 分钟：芙兰主动说一句跟游戏相关的话（不是通用台词）
2 切到 VS Code / Word 写东西：她说"监工"味的话
3 连续工作 50 分钟（可以临时把阈值调到 3 分钟测）：她催你去休息
4 关掉「看见你在干什么」开关：全程一句都不说
5 全屏游戏：芙兰隐藏，且不乱说话
```

---

## §4 第二十三批（对话 4/5）：语音输入（只做 STT，不做 TTS）

```text
本轮目标：按住 F8 说话 → 松开后转成文字 → 当作用户输入发给模型 → 气泡回答。芙兰**不出声**。

【必做 1】新建 src\voice.py（约 180 行，纯 ctypes）
- 热键：QTimer(50ms) 轮询 GetAsyncKeyState(VK_F8)；按下开始录、松开结束录
  （settings["voice"]["hotkey"]，本轮只支持 F8 / F9 两个键名，别的名字给提示）
- 录音：ctypes 调 winmm 的 MCI（mciSendStringW）：
    open new type waveaudio alias flrec
    set flrec time format ms bitspersample 16 channels 1 samplespersec 16000
    record flrec              → 松开
    save flrec "data\_voice_tmp.wav" → close flrec
  MCI 打不开（错误码）就退化到 waveIn* 一套；两套都不行就返回失败，让 UI 说人话。
- STT：POST {stt_base_url}/audio/transcriptions，multipart/form-data（file + model + language=zh），Bearer stt_api_key
  （whisper 兼容协议；硅基流动 SenseVoice 也走这个接口）
- 录音时长 < 0.6 秒视为误触，直接丢弃；> 60 秒自动截断
- 未配置 voice.stt_base_url 时热键完全不响应（不要提示，不要弹窗）

【必做 2】src\pet_window.py
- __init__ 里按 settings["voice"]["enabled"] 决定是否启动热键监听
- 录音中：切 stand5 闭眼帧（复用 _bounce_frame 机制）当"我在听"的反馈，不弹气泡
- 转写成功 → 文本当用户输入：若聊天窗开着就写进记录并发请求，没开就临时开一个（用户可能是想说话而不是打字）
- 转写失败 → 60 秒冷却内只提示一次（用第二十一批的 _on_ai_error，文案换成「我没听清…再来一次？」——这是唯一允许的额外预设文案）

【必做 3】设置页
「语音」卡：启用 / 热键 / STT 地址 / STT key / STT 模型。默认全空、开关关。

【必做 4】工具\ui_check.py 加第 24 段
- voice 模块在无麦克风环境 import 与构造不崩
- 未配置时热键回调是空操作
- 用 FLANDRE_VOICE_MOCK=1（返回一段 16k 单声道静音 wav 路径）跑通"录音→STT→进聊天流程"的桩
自检总段数变成 24 段。

【不许碰】TTS（不做）、聊天窗布局、点击逻辑、错误反应文案（除上面那一条）、计时器。

【我怎么验收】
1 设置里配好 STT 地址和 key、打开语音开关
2 按住 F8 说"今天好累" → 松开 → 聊天窗里出现你的话 → 芙兰气泡回答
3 不按说话键时，麦克风完全不工作（热键轮询 50ms 不占资源）
4 打游戏时按住 F8 说话也能用
```

---

## §5 第二十四批（对话 5/5）：收尾、声明、发布包

```text
本轮目标：把功能收口、把"不联网"的旧声明改对、把发布包重新做出来、把交接文档补齐。

【必做 1】README.md
现在写的是"程序不联网、不收集信息"。改成准确说法：
- 默认（离线模式）：不联网、不收集任何信息
- 开启在线模式后才会连接**你自己填的** API 地址；窗口标题/程序名只在「看见你在干什么」打开时发给该 API；不截图
- API key 以明文存在 data\settings.json（本地），发布包里不含 data\settings.json
- 语音只在你按住热键时录音，录音文件用完即删

【必做 2】data\settings.json 与发布包
- 确认发布包里不含 data\settings.json、data\chat_history.json、data\_voice_tmp.wav
- 重建 桌面\芙兰朵露_发布版.zip（旧说法已作废，现在这个文件不存在）
- **必须包含 贴图\站立\5.png 和 sound\error.wav**，否则点击回弹与错误音效会静默失效

【必做 3】全链路手工验收（逐条做，别跳）
离线：启动 → 右键无「聊天」→ 点芙兰出预设台词 → 选项对话仍在 → 番茄钟/待办/赠礼正常 → 打盹/唤酲正常
在线：填 key → 右键「聊天」→ 打字聊 3 轮 → 点芙兰即兴说话 → 断网后点一次触发错误反应 → 恢复网络
感知：开游戏 2 分钟听一句、写文档 2 分钟听一句、连续工作触发催休息
语音：按住 F8 说一句，气泡回答
全屏：F11 全屏隐藏 / 退出恢复；托盘手动显示后本次全屏不再隐藏

【必做 4】工具\ui_check.py 全 24 段过；`工具\repack.py --smoke` 过；再 `--check` 确认 exe 与源码一致。

【必做 5】交接文档.md
补一节「八、在线模式（LLM）使用说明」：怎么申请 key、填什么、DeepSeek/硅基流动/Ollama 的 base_url 示例、
费用提示（每次点击 1 次调用，默认每天上限 100 条主动说话）、出问题先看哪里。
把「六、当前状态与待办」的遗留项逐条更新（fs 锯齿、托盘图标、bubble_moved 写盘保护等若仍未解决就照旧留着）。

【不许碰】任何已被用户验收过的界面细节（菜单几何、气泡尺寸、贴图参数）。
```

---

## §6 交接文档追加模板（每轮结束照抄这个格式）

```markdown
   - **2026-XX-XX 第二十批（对话 1/5）（用户原话摘要：「……」）**：
     - **改法**：`src\config.py` 新增 `FULLSCREEN_TOL=2` / `ACTIVITY_TICK_MS=3000` / `CHAT_HISTORY`；
       `src\data_manager.py` DEFAULT_SETTINGS 加 `llm`/`watch`/`voice` 三块 + `load_chat_history()/save_chat_history()`；
       `src\net.py`（新）`class Net(QObject)` 的 `chat()/probe()`，`FLANDRE_LLM_MOCK=1` 模拟；
       `src\chat_ui.py`（新）`class ChatWindow(QDialog)`；`src\pet_window.py` 新增 `_llm_ready()/_menu_chat/_check_fullscreen()/_on_ai_done()`；
       `工具\repack.py` `rebuild_pyz()` 支持追加新模块。
     - **自检**：`工具\ui_check.py` 新增「21. 双模式与聊天窗」段 → `SELFCHECK OK`（**21 段**）。
     - **打包**：`工具\repack.py --smoke` 过；原地换 exe 后 `芙兰朵露.exe` = X,XXX,XXX 字节。
     - **用户验收**：①②③（逐条写他实际看到的）
     - **遗留**：……
```
