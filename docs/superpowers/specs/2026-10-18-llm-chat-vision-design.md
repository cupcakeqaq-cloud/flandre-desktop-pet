# 芙兰接入对话模型 / 双模式 / 桌面感知 / 语音（设计文档 v2）

> 2026-10-23 · 状态：**待用户审阅** · 审完才写实现计划、才动代码
> 项目：`C:\Users\CupCakeQAQ_\Desktop\芙兰`（桌宠「芙兰朵露」，PySide6 + PyInstaller onedir）
> v2 变更：按用户 2026-10-23 的新规范改成 **离线 / 在线 双模式**，并锁定错误台词、功能提示边界、点击节流、语音只做 STT。

## 1. 目标

| # | 目标 | 对应模块 |
|---|---|---|
| G1 | **双模式**：默认离线；填了 API 才进在线模式 | `llm_mode` 判定 + 菜单/设置显隐 |
| G2 | 在线模式能打字聊天 | `chat_ui.py` + `net.py` |
| G3 | 在线模式芙兰自主说话，**闲聊不再用预设台词** | `brain.py` |
| G4 | 在线模式语音输入（按住热键说话） | `voice.py` + STT |
| G5 | 芙兰"看见"你在干什么并吐槽 | `activity.py` |
| G6 | 修 bug：全屏（游戏/浏览器 F11）时桌宠悬空，应隐藏 | `pet_window.py` |

**不做**：芙兰出声（TTS，用户明确不要「用文字气泡回答即可」）；屏幕截图上传；多模态模型；唤醒词常开麦克风。

## 2. 双模式规格（本次核心）

| | **离线模式（默认）** | **在线模式（填了 API）** |
|---|---|---|
| 打字聊天 | **没有入口**（右键菜单不显示「聊天」） | 有：右键「聊天」开小窗 |
| 点击芙兰 | 现有逻辑：`dialogue.json` 随机台词 / 选项 / 连点生气 | **模型即兴一句**（防抖 + 单飞） |
| 主动说话 | 现有 40~120 秒随机台词 | 状态变化才说 + 同类冷却 10 分钟 + 每日 100 条 |
| 选项按钮对话 | 保留（约 15%） | **删掉** |
| 闲聊/吐槽台词 | `dialogue.json` | **全部模型生成** |
| 语音 | 无 | F8 按住说话 → STT → 文字 |
| 功能提示 | 预设 | **预设**（见下） |
| 网络 | 零请求 | 只在用户触发/事件触发时请求 |

**"功能提示保留预设"清单**（这些不能延迟、不能漏）：番茄钟完成/休息、倒计时结束、整点报时、打盹点醒（`rest_wake`）、倒数日提醒、赠礼成功/失败、托盘丢失兜底、`@"@" 开头」的计时器控制回执。它们继续走 `dialogue.pick()`，**在线模式也不改成模型**。

**模式判定**：`llm.enabled == true` 且 `base_url`/`api_key`/`model` 三项非空 → 在线；否则离线。设置页改动立刻反映到菜单（关掉在线模式时，「聊天」菜单项隐藏、聊天窗若开着就关闭）。

## 3. 失败处理（用户逐字指定）

在线模式请求失败（超时/断网/401/429/5xx）时的**唯一预设例外**：

- 台词（用户 2026-10-23 定稿，错字已改为「接收」）：`唉......电波貌似接收失败了，{nickname}去检查一下吧？`（把「你」按项目规范换成 `{nickname}`）
- 表现：**切闭眼帧（`贴图\站立\5.png`）+ 按压回弹动画** + 播放 `sound\error.wav`（44,136 字节，已存在）
- 实现：复用第十九批已有的 `_press_fx()` / `_end_bounce()`（`config.SQUASH_*`），再 `sound.play_file(SOUND_DIR/"error.wav")`，然后 `say(...)`
- **节流**：60 秒内只播 1 次，避免点一下响一下；期间请求失败静默，不刷屏

## 4. 点击节流（用户选：防抖 + 不排队）

- 点击 → 立刻压扁回弹 + 切闭眼帧（**已有机制**，作为"我在想"的视觉反馈）
- 同时发一次请求；**请求在飞（`busy`）时再点：只做回弹+闭眼，不发新请求、不排队**
- 去抖：400ms 内的连点合并为一次
- 回复到达 → `say(text)` 出气泡 + 恢复表情；请求失败 → §3 的错误反馈
- 代价（已与用户确认）：连点不会句句都回；好处是不烧 token、不卡顿

## 5. 现状（2026-10-23 13:4x 核对；这棵树当时**正被另一个会话改动**，数值请以 `交接文档.md` 最后一条为准）

- `src\pet_window.py` 已有**点击回弹**：`_press_fx()` / `_end_bounce()` / `_cancel_bounce()` / `_on_wobble()` / `_on_nap_hold()`，`_bounce_frame="stand5"`（`贴图\站立\5.png`，文件不存在自动退化 `1.png`）
- **第二十一批（13:34 收尾）改动**：遮罩在压扁期间临时放宽到外接矩形、弹回收回；绘制改成整数行条带 1:1 拷贝（`drawImage` 整行，不重采样）；**`SQUASH_SCALE_X` 已删**（不再横向加宽）；帧改**懒加载**（只同步解 stand1/2/5）；点击音效拆成 `sound\squish_press.wav` / `sound\squish_release.wav`
- `sound\` 有 5 个 wav：`error.wav`(44,136) / `tada.wav` / `TADA (2).wav` / `squish_press.wav` / `squish_release.wav`；`data\settings.json` 无任何 llm/voice/watch 键
- `工具\ui_check.py` = **20 段**（退出码可能是 0xC0000409，看输出）；`src\sound.py` 有 `play(name)`、`task_done()`、`squish_press()`、`squish_release()`，播 `error.wav` 直接 `sound.play("error.wav")`
- `工具\repack.py` 的 `project_modules()` 只用于**替换 PYZ 里已存在的模块**，`rebuild_pyz()` 遍历的是旧 TOC → **新增 `src\*.py` 不会被加进去**，必须加"追加新模块"逻辑
- `工具\repack.py` 的 `project_modules()` 只用于**替换 PYZ 里已存在的模块**，`rebuild_pyz()` 遍历的是旧 TOC → **新增 `src\*.py` 不会被加进去**，必须加约 10 行"追加新模块"
- `_internal` 里没有 QtMultimedia / winmm.dll → 录音只能用 `ctypes` 调系统 MCI 或 `waveIn*`
- `bubble.py` 无输入控件；`say()`（`pet_window.py:327`）是唯一台词出口

## 6. 架构

```
右键「聊天」──► chat_ui.py ──┐
F8 按住说话──► voice.py  ───┼─► net.py（urllib，子线程，OpenAI 兼容）
窗口活动采样──► activity.py ─┘        │
                                      ▼
                                 brain.py（说不说/说什么/限流/清洗）
                                      │
                    pet_window.say()（唯一出口，表情/气泡/昵称全复用）
```

**线程**：`threading.Thread(daemon=True)` + 主线程持有的 `QObject` 信号回调；工作线程绝不碰 QWidget；同时最多 1 个请求；超时 20s。
**依赖**：只用标准库 `urllib`/`ctypes` + 已有 `winsound`，**不新增第三方包**，`_internal` 体积不变，打包仍走 `repack.py`。

## 7. 模块

### 7.1 `src\net.py`（新增 ~200 行）
```python
class Net(QObject):
    done = Signal(str, str, str)   # kind("chat"/"stt"/"probe"), text, err
    def chat(self, messages): ...  # 异步
    def transcribe(self, wav_path): ...
    def probe(self): ...
```
- `POST {base_url}/chat/completions`，body `{model, messages, temperature, max_tokens, stream:false}`；`base_url` 归一化（去尾 `/`，缺 `/v1` 自动补，用户填 `https://api.deepseek.com` 也能用）
- 错误→人话：401「钥匙不对」/429「说太快了」/超时·网络「电波不通」；401/429 进入冷却
- `FLANDRE_LLM_MOCK=1` 环境变量 → 返回固定文本，供无 key 自测和 `ui_check.py` 离屏验证

### 7.2 `src\chat_ui.py`（新增 ~180 行）
非模态小窗，复用 `theme` 卡片/QSS：标题「和芙兰说话」+ 只读记录 `QTextBrowser` + `QLineEdit` + 「说」；回车发送；发送中显示「芙兰在想…」；回复到达 → 追加记录 + `pet.say(text)`；Esc 关闭；关窗不中断请求；离线模式下此窗不创建。
历史：`data\chat_history.json` = `{"messages":[{role,content,ts}], "usage":{"2026-10-23":37}, "last_date":"..."}`，保留 200 条，启动载入最近 10 轮。
**记录里也要显示芙兰主动说的话**（用户 2026-10-23 确认）：`brain` 主动吐槽/点击即兴的台词同样写进 `messages`（`role:"assistant"`，带 `"active": true` 标记），窗口开着时实时追加，用户能看到她刚说了什么。

## 7.2b 菜单与入口
- `theme._ICONS` 现有：`hide / eye / tomato / timer / day / todo / folder / settings / quit`，**没有 chat** → 本轮在 `theme._ICONS` 加一个 `chat` 图标（30 点坐标系、照 `tomato`/`folder` 的 `("r"/"c"/"l", ...)` 图元写法：圆角方框 + 左下小尖角 + 三颗点）
- `pet_window.contextMenuEvent` 的 `items` 列表插在最前：「聊天」/`"chat"`/`self._menu_chat`（在线模式才加这一项；离线模式这一行直接不出现）
- `_menu_chat` 用现有 `show_dialog("chat", lambda: ChatWindow(self))` 复用非模态去重逻辑

### 7.3 `src\brain.py`（新增 ~200 行）
- `build_messages(kind, ctx)`：人设（照交接文档 §1.1）+ 场景（时间/番茄钟/待办/看到的活动）+ 输出硬约束
- 输出约束：只输出台词；不加引号/括号/动作描写；1~2 句 ≤40 字；称呼 `{nickname}`
- 清洗：去首尾引号/星号/`（）`、按句读截到 60 字内
- 节流：同类事件冷却 `watch.cooldown_s=600`；每日吐槽上限 `watch.daily_cap=100`（计数在 `chat_history.json` 的 `usage`）；用户主动来聊不占吐槽名额但同样单飞

### 7.4 `src\activity.py`（新增 ~160 行，纯 ctypes）
3 秒采样：`GetForegroundWindow` → `GetWindowTextW` + 进程名（`QueryFullProcessImageNameW`）+ `GetLastInputInfo`（空闲秒数）。
事件：`activity_changed(app,title)` / `idle_started(sec)` / `active_streak(min)`（≥50 分钟催休息）。
**"在干什么"交给模型判断**（把标题+进程名塞进上下文），不做本地软件白名单。过滤自身窗口。

### 7.5 `src\voice.py`（新增 ~180 行）
- 热键：50ms `QTimer` + `GetAsyncKeyState` 轮询 → 按下开始、松开结束（真"按住说话"）；默认 `F8`，可配
- 录音：`ctypes` 调 `mciSendStringW`（`open new type waveaudio alias flrec` → `set flrec time format ms bitspersample 16 channels 1 samplespersec 16000` → `record` → `save` → `close`）；MCI 不行退化 `waveIn*`；失败给人话提示
- STT：`POST {stt_base_url}/audio/transcriptions` multipart（`file`+`model`+`language=zh`），结果当作用户输入进聊天流程
- 未配 STT → 菜单项置灰并说明原因
- ⚠️ 未决：STT 服务商（OpenAI `whisper-1` / 硅基流动 `SenseVoiceSmall` / 本地 `whisper.cpp`），语音那一轮再定

### 7.6 全屏隐藏（`pet_window.py` +60 行）
```
hwnd = GetForegroundWindow()
自身/Progman/WorkerW/Shell_TrayWnd → 不算
GetWindowRect(hwnd) 与 MonitorFromWindow→GetMonitorInfoW(rcMonitor) 四边差 ≤2px
且无 WS_CAPTION → 全屏
```
- 进入：记状态 → `_fullscreen_hidden=True` → **直接 `self.hide()`**（不能用 `hide_pet()`，它有托盘兜底会拒绝隐藏）→ 暂停主动说话与活动吐槽
- 退出：`show()` 回原位 + 恢复计时
- 托盘手动「显示芙兰」→ 清标记，本次全屏不再自动隐藏
- 开关：`watch.hide_in_fullscreen`（默认 true）

### 7.7 设置页新卡
- 「对话模型」：启用 / `base_url` / `api_key`（密码框）/ `model` / 温度 / 「测试连接」
- 「芙兰看见你在干什么」：总开关 / 同类冷却 / 每日上限 / 全屏时隐藏我
- 数据的默认值（旧 `settings.json` 自动补齐）：
```json
"llm":   {"enabled": false, "base_url": "https://api.deepseek.com", "api_key": "",
          "model": "deepseek-chat", "temperature": 0.9, "max_tokens": 300, "timeout": 20},
"watch": {"enabled": false, "cooldown_s": 600, "daily_cap": 100, "hide_in_fullscreen": true},
"voice": {"enabled": false, "hotkey": "F8", "stt_base_url": "", "stt_api_key": "",
          "stt_model": "whisper-1"}
```

## 8. 提示词骨架

```
你是「芙兰朵露·斯卡蕾特」，495 岁、住在{主人}电脑里的小吸血鬼，淘气但贴心。
1 只输出台词本身：不写动作、不写心理、不加括号引号、不解释。
2 1~2 句，最多 40 字。口语，可以带语气词。
3 禁止书面句式（虽然…但是 / 由于…因此 / 首先）。
4 称呼一律用 {nickname}。
5 你正看着屏幕：{窗口标题} / {进程名}。（仅 watch.enabled 时填，否则整行删除）
```

## 9. 参考的开源项目（只借思路，不抄代码）

| 仓库 | 语言 | 星 | 许可证 | 可借鉴 |
|---|---|---|---|---|
| [LYiHub/pub-local-jarvis](https://github.com/LYiHub/pub-local-jarvis) | Python | 519 | **MIT** | Windows 屏幕+音频感知的采样与"该不该开口"策略；本地多模态 |
| [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | Python | 14,331 | Other(NOASSERTION) | 免手语音、打断、屏幕视觉的整体流程；**许可证需先读清才能抄代码** |
| [zhuge-Tom/moepet](https://github.com/zhuge-Tom/moepet) | Python | 11 | 无 | 屏幕感知 + 独立记忆的组织方式；**无许可证 = 不能抄代码** |
| [ruguo0119/AI-Desktop-Pet](https://github.com/ruguo0119/AI-Desktop-Pet) | JavaScript | 21 | 无 | 陪聊+记忆+视觉的最小实现思路；Electron/Live2D，技术栈不同 |

**为什么不能直接用**：① 它们都以 Live2D/Electron 为渲染骨架，芙兰是 PySide6 精灵帧 + 成熟状态机，换上等于重做；② 依赖会拉进 torch/faster-whisper/openai/sounddevice，`_internal` 从 55MB 涨到几百 MB，还会破坏 `repack.py` 秒级打包；③ 两个仓库没有许可证，法律上不能抄代码。
**结论**：抄"怎么设计"，不抄"代码"。本项目继续零新依赖实现。

## 10. 分期（每轮一个对话，结束写交接文档）

| 对话 | 批次 | 内容 | 验收 |
|---|---|---|---|
| **0（本轮）** | — | 问答 + 本文档 + 用户审阅 → 再写实现计划 | 你说「可以」 |
| **1** | 第二十批 | **双模式骨架** + 聊天窗 + 设置两张卡 + 全屏隐藏 + `repack.py` 支持新模块 | 离线时无聊天入口、点击照旧；填 API 后能聊；F11 全屏消失/恢复；`SELFCHECK OK` |
| **2** | 第二十一批 | 在线模式接管闲聊：点击即兴（防抖+单飞+闭眼思考）、主动说话、错误台词+`error.wav`+回弹、删选项 | 在线时点她出模型话；断网出「电波接收失败」并播 error.wav；不烧重复请求 |
| **3** | 第二十二批 | 桌面感知：`activity.py` → 打游戏夸 / 工作监工 / 连续 50 分钟催休息 | 开游戏说游戏话；冷却与日上限生效 |
| **4** | 第二十三批 | 语音：F8 按住录音 → STT → 聊天 | 按住说一句，气泡回一句；没配 STT 时热键无副作用 |
| **5** | 第二十四批 | 收尾：冒烟、20 段自检、README 改「不联网」声明、发布包（含 `贴图\站立\5.png`） | 双击 exe 全功能验收 |

**合计 5 个开发对话（+本轮）。** 最坏情况做到对话 1~3 就满足 90% 需求；语音随时可砍。

## 11. 风险

| 风险 | 对策 |
|---|---|
| 网络调用卡 33ms 主循环 | 全子线程 + 20s 超时 + 失败静默 |
| 费用失控 | 状态变化才说 + 10 分钟冷却 + 每日 100 条 + 点击不排队 |
| 模型话太长炸气泡 | `max_tokens` + 60 字硬截断 |
| AI 味（用户最在意） | 提示词硬约束 + 清洗 + 每轮给你看真实输出 |
| 明文 key | 仅存本地 `data\settings.json`（已 gitignore、不进发布包） |
| 窗口标题外发 | 仅 `watch.enabled` 时进提示词 |
| 全屏误判 | 2px 容差 + 必须无 `WS_CAPTION` + 开关 |
| 录音设备被占 | MCI→waveIn 两级退化 + 人话提示 |
| 新模块打不进 exe | 先改 `repack.py` 并 `--check`，每轮 `--smoke` |
| 第十九批还没提交 | **开工前先提交这批**（`贴图\站立\5.png`、`sound\error.wav` 一起），否则改动混在一个 diff 里 |

## 12. 未决

1. STT 服务商（语音轮定）。
2. ~~台词「接受」是否应为「接收」~~ → 已定：**接收**。
3. ~~聊天窗是否显示芙兰主动说的话~~ → 已定：**显示**（见 §7.2）。
4. **待用户确认**：交接文档「第二十批」记了按压变形修复 / `BLINK_HOLD_SECONDS=0.5` / `sound\squish.wav` + `sound.squish()` / exe 2,560,602 字节，但工作区里 `sound.py` 是 2026-10-11 的版本、没有 `squish()`、`sound\` 没有 `squish.wav`、exe 仍是 2,560,506。这一批到底做了又被回滚，还是只写进了文档？
