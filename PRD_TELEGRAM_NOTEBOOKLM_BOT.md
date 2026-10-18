# 项目需求与技术规格说明书：Telegram NotebookLM 播客与信息图生成 Bot

---

## 1. 项目概述与目标

本项目构建了一个基于 Telegram Bot 的全自动多模态素材剪藏与 Google NotebookLM **双人对话播客 + 知识信息图** 协同生成系统。

用户在移动端或桌面端 Telegram 向专属机器人发送文章链接、随手富文本、图片、PDF 文档或音频文件；机器人完成素材预处理与多模态解析后，调度 Antigravity CLI（以 Headless 无头模式运行），由 Antigravity 调度 NotebookLM MCP（Model Context Protocol）工具链完成全流程：

1. 创建对应主题的 NotebookLM 笔记本；
2. 批量注入多模态素材（图片素材经 Gemini 多模态 Vision 提取并转化为纯文本结构化 Markdown 文档，确保离线 Studio 管线能够完整读取）；
3. 在同一笔记本内同时触发两项官方生成任务：
   - **双人对话播客（Audio Overview / Deep Dive）**：全程中文（普通话）深度讨论；
   - **知识信息图（Infographic）**：纵向（Portrait）、标准详细度（Standard）、全中文呈现；
4. 轮询并下载两份成品文件至指定输出工作区；
5. 最终通过 Telegram 双通道依次推送信息图与播客音频；
6. 确认推送成功后，自动执行延迟清理，释放暂存区与本地临时文件；若失败则完整保留素材以便一键重试。

---

## 2. 系统架构与数据流图

```text
[用户 Telegram 客户端] (白名单 ID: ALLOWED_USER_ID)
       │
       ▼ (发送 URL / 文本 / 语音 / 音频 / 图片 / PDF)
[Telegram Bot 服务] (基于 python-telegram-bot + HTTPXRequest)
       │
       ├─► 消息接收与用户白名单硬过滤 (非本人直接静默丢弃)
       ├─► 素材暂存与格式预处理 (图片经 Gemini Vision 提取为结构化 Markdown .md)
       └─► 触发指令 `/make [可选标题]`
              │
              ├─► 标题决议策略：
              │     ├─ 用户显式指定 ──► 直接使用自定义标题
              │     └─ 用户留空 ─────► 临时占位标题 ──► 后续捕获 NotebookLM 自动生成标题
              │
              ▼ (组装非交互式结构化 Prompt)
       [Antigravity CLI 子进程] (Headless 模式: agy -p / antigravity -p)
              │
              ▼ (调度 Model Context Protocol 服务)
       [gemini-notebook-mcp / notebooklm-mcp 服务]
              │
              ├─► notebook_create (创建目标笔记本)
              ├─► source_add (批量挂载 URL 与本地绝对路径文件)
              ├─► studio_create #1 (触发生成中文双人 Deep Dive 播客音频)
              ├─► studio_create #2 (触发生成纵向标准知识信息图 Infographic)
              ├─► studio_status (轮询检查两项生成物直至均变为 completed/ready)
              └─► download_artifact (分别下载音频 .m4a 与信息图 .png)
              │
              ▼ (产物多重候选目录扫描与落盘归集)
       [多候选目录智能扫描与归集] (outputs/、workspace/、~/Downloads/gemini-notebook)
              │
              ▼ (双生成物落盘交付与标题捕获)
[Telegram Bot 服务]
       │
       ├─► Step 1: 解析 stdout JSON 捕获 NotebookLM 自动生成标题并回填通知
       ├─► Step 2: send_photo / send_document (推送知识信息图)
       ├─► Step 3: send_audio (推送 40MB+ 双人深度播客音频，携带最终标题)
       └─► Step 4: 清除本次任务暂存区，并物理清理 workspace/downloads 临时文件（_extracted.md 及原始图片）
              │
              ▼
[用户 Telegram 客户端] (成功接收图文与音频成果)
```

---

## 3. 安全与访问控制规范

1. **Telegram 用户白名单（核心鉴权）**：
   - 允许的用户 ID：`ALLOWED_USER_ID`（整型常量）。
   - 拦截策略：所有消息处理器与指令处理器底层均挂载 `filters.User(user_id=ALLOWED_USER_ID)`。
   - 非白名单请求处理：一律**静默丢弃（Silent Drop）**，不予回包，不在用户端产生任何状态响应，避免被外部探测与滥用。
2. **群组限制（BotFather 侧配置）**：
   - 在 `@BotFather` 中针对机器人开启配置：`Bot Settings -> Allow Groups? -> Turn groups off`，严格禁止机器人被拉入任何公开或私有群组。
3. **敏感凭证管理**：
   - Telegram Bot Token、User ID、代理设置等敏感参数必须通过 `.env` 读取，严禁硬编码。
   - 所有公开文档、提交代码与示例中严格使用通用占位符（如 `your_telegram_bot_token_here`、`123456789`）。

---

## 4. 核心功能与模块设计

### 4.1 素材接收与预处理模块（Telegram Ingestion）

- **链接提取**：通过正则匹配用户发送文本中的所有 `http://` / `https://` 链接，提取为独立 URL 素材。
- **纯文本随手记**：用户发送的不含 URL 的纯文本，自动落盘为 UTF-8 编码的 `.txt` 文件并记录本地绝对路径。
- **文档与音频接收**：
  - 文档：支持 `.pdf`、`.docx`、`.txt`、`.md` 等。
  - 音频：支持 `.mp3`、`.m4a`、`.wav` 以及 Telegram 语音消息（`.ogg`）。
  - 文件下载后规范命名并统一存入 `./workspace/downloads/`。
- **图片多模态解析（Gemini Vision 提取为 Markdown）**：
  - **问题背景**：Google NotebookLM 的 Studio 离线管线（音频概览与信息图）目前仅检索与读取可提取的纯文本流。早期方案通过 Pillow 将图片打包为无文字层的 PDF 时，NotebookLM 离线 Studio 模型无法从中提取到任何有效文字字符，导致截图内容被合成完全忽略。
  - **解决方案**：重构 `services/converter.py` 中的 `convert_image_to_markdown` 异步函数。接收到图片后，调度多模态 Vision 模型提取图片中的所有文本内容，保持原文完整性与事实准确性，并整理为规范的 Markdown 格式（保留标题、段落、列表与引用层级）落盘存为 `workspace/downloads/{image_stem}_extracted.md`。
  - **双通道调度**：
    1. 优先使用已在宿主环境登录授权的 Antigravity CLI（`agy` / `antigravity`，调度 `gemini-3.8-flash-medium`）免 Key 智能提取；
    2. 支持在 `.env` 中选填 `GEMINI_API_KEY`，使用 `httpx` 调用官方多模态 REST API 快速提取。
  - **价值效果**：该机制彻底解决了离线 Studio 管线无法读取截图内容的关键问题，使截图中的技术架构、长文内容能够 100% 参与到随后的播客对谈与信息图生成中。

### 4.2 批处理暂存与延迟释放机制（Staging & Delayed Cleanup）

- **会话暂存**：用户可跨时间、跨类型连续发送素材，系统以 `user_id` 在内存字典 `user_staging` 中进行缓冲。
- **延迟释放策略（重要设计）**：
  - 发起 `/make` 时，系统先对暂存列表进行快照备份，**不立即清空暂存区**。
  - 只有在**信息图与音频均成功推送到 Telegram** 之后，才从暂存区中移除该批素材，并物理删除 `workspace/downloads` 中对应的临时文件（包括提取的 `_extracted.md` 文件及其对应的原始下载图片）。
  - 若在 CLI 执行、网络传输或 Telegram 推送过程中发生任何异常，**完整保留素材清单与本地下载文件**，用户仅需在会话中输入 `/make` 即可原地重试，无需重复上传。

### 4.3 Antigravity CLI 驱动模块（Subprocess Invocation）

- **执行指令与参数规范**：
  - 统一调用 `agy` 或 `antigravity`：`-p "<prompt>" --model gemini-3.8-flash-medium --print-timeout 35m --dangerously-skip-permissions`。
  - 必须开启非交互与免确认权限，确保无头环境下平稳调度。
- **运行目录（CWD）**：
  - 统一指向项目根目录下的 `./workspace`。
- **环境隔离与继承**：
  - 完整继承包含 `~/.local/bin` 的 PATH，以及可选的 `HTTP_PROXY` / `HTTPS_PROXY` 代理设置。
  - 显式声明 `NOTEBOOKLM_DOWNLOAD_DIR` 与 `NOTEBOOKLM_HL="zh-CN"`。
- **双生成物 Prompt 结构化约束**：
  1. `notebook_create(title=...)`
  2. `source_add` 逐个挂载 URL 与本地文件。
  3. 双任务触发：
     - **音频生成**：`studio_create(artifact_type="audio", confirm=True, audio_format="deep_dive", language="zh", focus_prompt="...")`，强制中文普通话讨论。
     - **信息图生成**：`studio_create(artifact_type="infographic", confirm=True, orientation="portrait", detail_level="standard", language="zh", focus_prompt="...")`，指定纵向、标准详细度（降低字数变形）、中文。
  4. 轮询等待：每隔 15~20 秒调用 `studio_status` 检查，直至两项均为 `completed`。
  5. 下载输出：分别调用 `download_artifact` 将音频与信息图保存至 `./workspace/outputs/`。
- **多重候选目录扫描策略（Candidate Directory Scanning）**：
  - 鉴于底层 MCP 工具在不同平台环境下可能输出到系统默认下载路径，系统设计了多重候选扫描矩阵：
    - 主输出目录：`./workspace/outputs/`
    - 工作区目录：`./workspace/`
    - 回退目录：`~/Downloads/gemini-notebook/`
  - 任务结束后，系统跨上述目录扫描时间戳在任务启动后的最新音频（`.m4a`/`.mp3`/`.wav`）与信息图（`.png`/`.jpg`/`.pdf`），若不在目标 `outputs/` 则自动原子移动并规范归集。

#### 4.3.1 智能标题生成与输出捕获子流程

为改善用户体验，系统支持两套标题自动化机制：

1. **素材前置标题提炼（`generate_title_from_sources`）**：
   - **调用时机**：当用户直接发送 `/make` 未携带自定义标题，或需要提前提炼摘要标题时调用。
   - **执行逻辑**：
     - 汇总所有暂存素材的 URL 与文件路径，构造精炼 Prompt，要求模型生成 8-15 个汉字的专业中文标题，且仅输出标题正文。
     - 异步拉起 Antigravity 子进程（使用 `ANTIGRAVITY_MODEL`），注入 60 秒硬超时保护。
     - 获取模型输出后，自动截取首行并过滤前缀与包裹字符（如 `标题：`、`Title:`、`《》`、`【】`），校验 5-50 字符长度边界。
2. **NotebookLM 运行态标题提取与回退三级策略**：
   - **实时输出提取**：在 `run_antigravity_podcast_pipeline` 监听子进程标准输出时，解析包含 JSON 格式的输出行，从中提取 NotebookLM 创建或更新后返回的真实笔记本标题 `{"title": "..."}`。
   - **三级优先级回退矩阵**：
     - **第一优先级（用户输入）**：若用户在 Telegram 发送了 `/make 自定义标题`，始终以用户指定标题为准。
     - **第二优先级（NotebookLM 自动生成）**：若用户未传标题，且子进程捕获到了 NotebookLM 返回的合法 `title`，则更新标题并在 Telegram 提示 `✨ NotebookLM 自动生成标题：《...》`。
     - **第三优先级（时间戳兜底）**：若前序均未获取到，使用初始化时生成的时间戳兜底标题（`播客速递_YYYYMMDD_HHMM`）。

### 4.4 状态轮询、双通道交付与网络加固（Delivery）

- **超时保护**：
  - 由于 NotebookLM 同时合成长篇音频与信息图耗时通常在 8~18 分钟，系统全局硬超时设置为 **1800 秒（30 分钟）**，彻底移除易产生误报的空闲检测，避免误杀正常任务。
- **进度消息反馈**：
  - 执行过程中，Bot 自动在 Telegram 中更新进度（1/4 创建 -> 2/4 挂载 -> 3/4 深度合成中 -> 4/4 交付）。
- **双通道推送**：
  - 📊 **信息图推送**：
    - 若为图片格式（PNG/JPG/WEBP），调用 `reply_photo`，附带说明文案《知识信息图（纵向·标准版）》。
    - 若为 PDF 文档，调用 `reply_document`。
  - 🎙️ **播客音频推送**：
    - 调用 `reply_audio` 推送原生音频卡片，附带标题、时长与大小信息。
- **网络加固配置**：
  - 初始化 Telegram Application 时配置 `HTTPXRequest`：
    `connect_timeout=60.0`, `read_timeout=300.0`, `write_timeout=300.0`，保障 40MB+ 大音频传输不因网络抖动中断。

---

## 5. 异常处理与容错矩阵

| 异常场景 | 检测与捕获方式 | 应对与恢复策略 |
| :--- | :--- | :--- |
| **未授权访问** | `update.effective_user.id != ALLOWED_USER_ID` | 底层过滤器静默丢弃，记录 Warning 日志，不作任何响应。 |
| **纯图片无法直接被离线管线解析** | 接收到 `message.photo` / 图片文档 | 调用 `convert_image_to_markdown` 进行多模态 Vision 文字提取，转为规范 Markdown 文档落盘入库，用户无感知。 |
| **工具交互卡顿** | 缺少确认参数 | CLI 附加 `--dangerously-skip-permissions` / `-y`，Prompt 显式指定 `confirm=True`。 |
| **长任务云端生成耗时** | 运行耗时超过常规 10 分钟 | 全局超时配置为 1800s（30 分钟），无阻塞等待，避免误杀正常任务。 |
| **超大音频推送超时** | `TimedOut` / `NetworkError` | `HTTPXRequest` 超时加固为 300s；若依然上传失败，素材完整保留，提示用户原地重试。 |
| **单文件超限（> 50MB）** | 检查音频体积 `file_size_bytes > 50MB` | 拦截 Telegram 官方上传限制，保留本地完整文件并向用户提示本地提取路径。 |
| **标题提炼超时或格式异常** | `asyncio.TimeoutError` / 长度异常 | 自动降级回退至时间戳默认标题（`播客速递_...`），主流程不受任何阻断。 |
| **生成物存放路径偏差** | `output_dir` 未发现文件 | 启动多候选目录扫描（`workspace/`、`~/Downloads/gemini-notebook`），智能搜寻并迁移归集。 |

---

## 6. 测试验证与验收标准

1. **白名单校验**：白名单用户正常使用所有指令；非白名单用户发送任何消息，Bot 无响应。
2. **多模态素材剪藏**：连续发送 1 个 URL、1 段文本、1 张图片与 1 段录音，`/status` 显示共 4 份素材，且图片已成功提取为 Markdown 文档。
3. **双产物全流程生成**：
   - 执行 `/make 测试综述`，子进程拉起并平稳运行。
   - Telegram 收到纵向标准信息图（PNG 高清图片）。
   - Telegram 收到普通话对谈的 Deep Dive 播客音频（M4A）。
4. **标题智能生成验证**：
   - 暂存素材后发送无参数指令 `/make`；
   - 验证系统正常触发标题捕获或提炼逻辑；
   - 验证 Telegram 进度消息展示 `✨ NotebookLM 自动生成标题：《...》`；
   - 验证推送的信息图文案与音频卡片名称使用自动提炼的标题。
5. **清理与重试验证**：
   - 成功推送后，暂存素材自动清空，`workspace/downloads` 对应临时文件（包括 `_extracted.md` 及原始下载图片）被物理清理。
   - 模拟网络中断测试失败，暂存素材完整保留，直接发送 `/make` 可成功恢复执行。
6. **运维脚本与自动化部署验证**：
   - 运行 `./health-check.sh`，输出 5 项体检结果且返回码为 0。
   - 运行 `./cleanup.sh --dry-run` 正确输出过期文件清单且不执行删除；运行 `./cleanup.sh --force` 完成安全清理。
   - 运行 `./deploy.sh`，成功拉取最新提交、更新依赖、重启服务并通过健康检查；若引入语法错误导致启动失败，脚本自动回滚代码并恢复前一稳定版本。

---

## 7. 运维体系与部署架构（Operations & Deployment Architecture）

为确保生产环境的高可用、易维护与免人工干预，系统建立了一套包含自动化脚本、系统守护进程与全链路监控的运维工程体系。

### 7.1 运维脚本工具链架构

整个运维工具链以 `common.sh` 为公共核心基座，规范了环境依赖自检、路径解析、PID 锁管理和统一的 ANSI 彩色格式化输出：

```text
common.sh (公共环境、PID锁、日志函数、配置解析)
  ├── start.sh        (环境自检 -> PID查重 -> nohup后台启动 -> 存活验证)
  ├── stop.sh         (PID检测 -> SIGTERM优雅停止 -> 10s超时SIGKILL)
  ├── restart.sh      (原子调用 stop.sh + start.sh)
  ├── status.sh       (进程状态 -> 资源占用 -> 缓存统计 -> 配置自检)
  ├── logs.sh         (tail -f跟随 -> 行数截取 -> 错误过滤 -> 日志清理)
  ├── health-check.sh (5项体检: 进程/CLI/TG连通性/错误日志/磁盘 -> 状态码0/1/2)
  ├── cleanup.sh      (扫描缓存 -> 确认/免交互 -> 过期清理 -> 保留.gitkeep)
  └── deploy.sh       (Git检查 -> git pull -> pip install -> 重启 -> 体检 -> 自动回滚)
```

- **PID 锁安全机制**：通过 `.bot.pid` 实现单例进程保护，启动时检查 `kill -0 $PID` 防止重复拉起；退出时自动注销 PID 锁。
- **平滑停止策略**：`stop.sh` 优先发送 `SIGTERM` 信号，循环等待进程安全释放资源并完成清理；若超过 10 秒未退出，升级发送 `SIGKILL` 强制回收。

### 7.2 自动化部署与热更新流程（`deploy.sh`）

`deploy.sh` 实现了生产环境的零停机或近零停机持续集成与热更新：

1. **版本快照**：记录更新前的 Commit ID（`PREV_COMMIT`）与分支；
2. **工作区安全校验**：检查未提交代码，提示用户通过 `git stash` 保护本地变更；
3. **代码同步**：执行 `git pull origin <branch>` 获取最新提交；
4. **依赖自动化同步**：执行 `pip install -r requirements.txt`，确保新增依赖就绪；
5. **服务平滑重启**：调用 `./restart.sh` 重新拉起应用；
6. **健康巡检闭环**：调用 `./health-check.sh` 检验新进程存活与 Telegram API 连通性；
7. **自动化回滚保护（Rollback）**：若在重启或健康检查中检测到严重异常（返回码 2），脚本自动触发 `git reset --hard $PREV_COMMIT`，重新拉起稳定版本，确保生产服务永不宕机。

### 7.3 Systemd 生产守护与崩溃自愈

在 Linux 云服务器生产环境中，推荐通过 systemd 接管守护进程。系统提供了标准服务配置文件 `nlmpodcastbot.service`：

- **自愈重启策略**：配置 `Restart=always` 与 `RestartSec=5s`，当进程因宿主 OOM 或意外异常退出时，操作系统将在 5 秒内自动拉起。
- **资源限制与安全隔离**：配置 `LimitNOFILE=65535` 确保大文件传输不耗尽文件句柄；配置 `KillSignal=SIGTERM` 与 `TimeoutStopSec=15s` 实现平稳停机。
- **日志持久化重定向**：标准输出与错误输出直接重定向至 `./logs/bot.log`，同时被 systemd journal 捕获，支持通过 `journalctl -u nlmpodcastbot -f` 统一排查。

### 7.4 缓存管理与生命周期策略（`cleanup.sh`）

系统制定了分级过期回收策略，由 `cleanup.sh` 统一调度：

| 目录/对象 | 过期阈值 | 清理目标与规则 |
| :--- | :--- | :--- |
| `workspace/downloads/` | **> 24 小时** | 清理用户上传的临时文档、音频、原始图片及提取出的 Markdown，严格保留 `.gitkeep` |
| `workspace/outputs/` | **> 72 小时 (3天)** | 清理历史已交付的音频文件（.m4a/.mp3）与信息图（.png/.jpg/.pdf），严格保留 `.gitkeep` |
| `logs/` | **> 7 天** | 清理轮转归档的历史日志文件，保障磁盘空间充裕 |

- **安全预览（Dry Run）**：通过 `./cleanup.sh --dry-run` 仅输出匹配文件清单与预计释放空间，杜绝误删风险。
- **定时自动化执行**：通过 `./cleanup.sh --force` 免交互运行，可直接编排至 Crontab 任务（例如：`0 3 * * * /path/to/cleanup.sh --force`）。