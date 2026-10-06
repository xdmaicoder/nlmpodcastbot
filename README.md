# Telegram NotebookLM 播客与信息图生成机器人 (`telegram-nlm-podcast`)

基于 Telegram Bot 的全自动多模态素材剪藏与 Google NotebookLM **双人对话播客 + 知识信息图** 协同生成系统。

---

## 🌟 核心特性

- **多模态素材聚合**：
  - 🔗 **网页链接**：发送任意文章或文档 URL，自动抓取核心内容作为数据源。
  - 📝 **纯文本笔记**：直接发送长文本或随手记，自动保存为 UTF-8 文本素材。
  - 🖼️ **图片/截图多模态深度解析（Markdown 提取）**：
    - **背景与痛点**：NotebookLM 的 Studio 离线管线（音频概览与信息图）只读取可提取的纯文本流。早期若仅通过 Pillow 将图片打包为无文字层的 PDF，Studio 会无法提取到任何文字字符，导致生成的音频概览与信息图完全忽略截图内容。
    - **解决方案**：重构为“图片通过多模态 Vision 提取并转为结构化 Markdown（.md）文档”。接收图片后，调用多模态模型提取图片中的所有文本内容，保持原文完整性与事实准确性，并整理为规范的 Markdown 格式（保留标题、段落、列表与引用层级）落盘存入素材库，彻底解决了离线 Studio 管线无法读取截图内容的关键问题。
    - **双通道调度**：默认直接复用宿主环境已认证的 Antigravity CLI（`agy` / `antigravity`，调度 `gemini-3.8-flash-medium`）免 Key 智能提取；亦支持配置 `GEMINI_API_KEY` 走轻量 REST API 直连。
  - 📄 **结构化文档**：原生支持 PDF、Word（.docx）、TXT、Markdown（.md）等多种文档格式。
  - 🎙️ **音频与语音消息**：支持直接发送录音、语音消息（.ogg）或 MP3/M4A 音频材料。

- **双产物协同生成与交付**：
  - 🎙️ **双人播客音频（Deep Dive）**：基于所有聚合素材，生成全程使用**中文（普通话）**进行的深度、自然、生动的主持人对谈剖析。
  - 📊 **知识信息图（Infographic）**：在同一笔记本中同步生成知识信息图，严格规范为**纵向（Portrait）**、**标准详细度（Standard，精简字数、降低渲染变形）**与**中文呈现**。
  - 交付顺序：机器人优先推送高清信息图预览，随后推送原生防超时的 40MB+ 大音频播放卡片。

- **健壮的缓存管理与延迟释放机制**：
  - **交付成功后释放**：只有在信息图与播客音频均成功推送到 Telegram 后，才安全清空暂存区，并物理清理本地 `workspace/downloads` 产生的临时文件（包括提取产生的 `.md` 及其原始下载图片）。
  - **失败全量保留重试**：任一环节（CLI 报错、超时、网络中断、Telegram 上传中断等）失败时，暂存素材与本地转换文件均**完整保留**，用户只需在 Telegram 回复 `/make` 即可立即重试，无需重新上传素材。

- **30 分钟充裕全局保护与网络加固**：
  - **长超时无阻塞等待**：采用稳健的 1800 秒（30 分钟）全局硬超时保护，彻底移除可能误杀正常云端任务的脆弱空闲检测，从容应对 8~18 分钟的长篇深度材料合成。
  - **Telegram 请求超时加固**：通过定制 `HTTPXRequest`（连接超时 60s，读写超时设置为 300 秒），确保 40MB+ 大音频文件在代理环境或弱网下稳定上传。

- **严格的安全白名单与隐私保护**：
  - 基于 Telegram User ID（`ALLOWED_USER_ID`）进行底层硬过滤，非白名单请求直接静默丢弃（不回应、不消耗算力），彻底防止未授权滥用。
  - 默认关闭群组支持，仅作为单人专属知识库助手。

---

## 📁 项目工程结构

```text
nlmpodcastbot/
├── .env                  # 本地私密环境变量（不可提交至版本库）
├── .env.example          # 完整环境变量配置模板
├── .gitignore            # Git 忽略配置规则
├── requirements.txt      # Python 核心依赖清单 (python-telegram-bot, httpx, pillow, python-dotenv)
├── README.md             # 项目使用与部署文档
├── PRD_TELEGRAM_NOTEBOOKLM_BOT.md # 架构设计与技术规格说明书
├── test_runner.py        # 脱离 Telegram 的独立端到端调试脚本
├── config.py             # 配置加载、路径解析与启动环境自检
├── bot.py                # Telegram Bot 主服务与消息调度控制器
├── services/
│   ├── __init__.py
│   ├── converter.py      # 图片多模态 Vision 提取 Markdown 与文本暂存工具
│   └── antigravity_runner.py # Antigravity CLI 子进程调度与产物捕获
└── workspace/            # 运行时动态数据目录
    ├── downloads/        # 暂存 Telegram 下载与预处理后的素材
    └── outputs/          # Antigravity 导出音频与信息图的交付目录
```

---

## 🛠️ 前置准备与环境配置

### 1. 宿主机环境要求

- **Python**：>= 3.10
- **Node.js / uv**：用于运行 Google NotebookLM MCP 客户端工具
- **NotebookLM CLI (`nlm`)**：
  - 确保 `~/.local/bin` 在系统的 PATH 环境变量中。
  - 执行 Google 账号授权（切换到所需目标账号）：
    ```bash
    nlm login --storage protected
    ```
  - 验证登录状态与可用笔记本配额：
    ```bash
    nlm doctor
    nlm usage
    ```
- **Antigravity CLI (`agy` 或 `antigravity`)**：
  - 安装并确保系统命令可用。
  - 将 NotebookLM MCP 工具注册至 Antigravity：
    ```bash
    agy mcp add gemini-notebook-mcp /Users/$(whoami)/.local/bin/notebooklm-mcp
    ```

### 2. 环境变量配置

复制模板并根据实际情况创建 `.env`：

```bash
cp .env.example .env
```

`.env` 核心配置项说明：

```env
# Telegram 配置
TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
ALLOWED_USER_ID=123456789

# Antigravity CLI 配置
ANTIGRAVITY_BIN="antigravity"
ANTIGRAVITY_MODEL="gemini-3.8-flash-medium"
TASK_TIMEOUT_SECONDS=1800

# 多模态 Vision 提取配置 (可选，留空则自动使用 Antigravity CLI 免 Key 提取)
# GEMINI_API_KEY="your_gemini_api_key_here"

# 网络代理 (可选，国内网络访问 TG 和 Google 时必填)
# HTTP_PROXY="http://127.0.0.1:7890"
# HTTPS_PROXY="http://127.0.0.1:7890"
```

---

## 🚀 安装与启动

### 1. 安装 Python 依赖

```bash
# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装核心依赖
pip install -r requirements.txt
```

核心依赖组件清单：
- `python-telegram-bot`：Telegram Bot API 异步框架。
- `httpx`：异步 HTTP 客户端，支撑 Telegram 大文件长连接与可选 Gemini REST 调用。
- `pillow`：图像文件预处理与尺寸/色彩通道检验。
- `python-dotenv`：环境变量管理。

### 2. 独立功能测试（可选）

在不启动 Telegram 机器人的情况下，直接测试 NotebookLM 笔记本创建、双模态合成与下载：

```bash
.venv/bin/python test_runner.py
```

### 3. 启动 Telegram Bot

#### 前台直接运行（调试）：
```bash
.venv/bin/python bot.py
```

#### 后台守护进程运行（推荐生产环境）：

- **使用 `nohup`**：
  ```bash
  nohup .venv/bin/python bot.py > bot.log 2>&1 &
  ```

- **使用 `pm2`**：
  ```bash
  pm2 start .venv/bin/python --name "nlm-podcast-bot" -- bot.py
  ```

---

## 💬 机器人指令与使用指南

| 指令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `/start` | 查看欢迎信息、支持的素材类型与帮助说明 | `/start` |
| `/status` | 查看当前暂存区中的素材清单与数量 | `/status` |
| `/make [标题]` | 触发合成任务，制作中文双人播客与知识信息图 | `/make 具身智能与大模型前沿综述` |
| `/clear` | 清空当前暂存区中的所有素材 | `/clear` |

### 典型使用流程：

1. **持续剪藏**：在日常阅读或调研过程中，将推特/公众号长文链接、技术论文截图、语音备忘录随手转发给机器人。
2. **确认素材**：发送 `/status`，确认素材已被识别（例如：`🔗 2 篇链接、🖼️ 1 张图解提取文档、🎙️ 1 段录音`）。
3. **一键生成**：发送 `/make 2026 AI Agent 架构剖析`。
4. **进度反馈**：机器人在 Telegram 会话中实时更新进度：
   - `1/4 正在创建笔记本与挂载素材...`
   - `2/4 素材已就绪，已触发双人播客与知识信息图合成...`
   - `3/4 云端正在深度合成播客与信息图中，请稍候（已耗时 X分X秒）...`
5. **成品接收**：
   - 🖼️ 优先推送 **📊《标题》知识信息图**（纵向·标准版，可点击放大浏览高清图解）。
   - 🎧 紧接着推送 **🎙️《标题》双人深度播客**（附带时长、大小信息，支持后台播放与倍速收听）。
6. **自动清理**：两者成功推送到 Telegram 后，暂存素材自动清空并清理磁盘临时文件。

---

## ⚠️ 常见问题排查 (FAQ)

1. **机器人对发送的消息无任何反应？**
   - 检查消息发送者的 Telegram User ID 是否严格匹配 `.env` 中的 `ALLOWED_USER_ID`。非白名单用户会被系统直接静默丢弃。
2. **为什么发送的图片要解析为 Markdown 而不是直接转成 PDF？**
   - Google NotebookLM 的 Studio 离线管线（音频概览与信息图合成）目前仅检索与读取可提取的纯文本流。以往通过 Pillow 将图片打包为无文字层的 PDF 时，虽然 NotebookLM UI 能够预览页面，但 Studio 离线模型无法从中提取到任何文字字符，导致截图内容被合成完全忽略。通过多模态 Vision 直接提取为结构化 Markdown（.md）后，NotebookLM 原生识别并纳入离线 Studio 检索，彻底解决截图内容丢失的问题。
3. **信息图渲染字体错位或乱码？**
   - 系统已将详细度调整为“标准（Standard）”，有效降低了字符密度。同时生成提示词强制指定全中文排版与精炼文本。
4. **大音频发送时报错 TimedOut？**
   - 生产环境中双人深度播客（15~25 分钟）体积通常在 30MB~50MB。当前配置已挂载 `HTTPXRequest(read_timeout=300.0, write_timeout=300.0)`，若仍超时请检查服务器本地的上行网络代理稳定性。
