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
              └─► download_artifact (分别下载音频 .m4a 与信息图 .png 至 workspace/outputs)
              │
              ▼ (双生成物落盘交付)
[Telegram Bot 服务]
       │
       ├─► Step 1: send_photo / send_document (推送知识信息图)
       ├─► Step 2: send_audio (推送 40MB+ 双人深度播客音频)
       └─► Step 3: 清除本次任务暂存区，并物理清理 workspace/downloads 临时文件与提取源
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

---

## 6. 测试验证与验收标准

1. **白名单校验**：白名单用户正常使用所有指令；非白名单用户发送任何消息，Bot 无响应。
2. **多模态素材剪藏**：连续发送 1 个 URL、1 段文本、1 张图片与 1 段录音，`/status` 显示共 4 份素材，且图片已成功提取为 Markdown 文档。
3. **双产物全流程生成**：
   - 执行 `/make 测试综述`，子进程拉起并平稳运行。
   - Telegram 收到纵向标准信息图（PNG 高清图片）。
   - Telegram 收到普通话对谈的 Deep Dive 播客音频（M4A）。
4. **清理与重试验证**：
   - 成功推送后，暂存素材自动清空，`workspace/downloads` 对应临时文件及提取源被物理清理。
   - 模拟网络中断测试失败，暂存素材完整保留，直接发送 `/make` 可成功恢复执行。