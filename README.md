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

- **智能标题自动生成**：
  - **可选自定义或智能提炼**：执行 `/make [标题]` 时，用户可自定义指定标题（例如 `/make 具身智能前沿剖析`）；若留空仅发送 `/make`，系统会自动分析素材内容并调用 Antigravity 智能提炼 8-15 字精炼中文标题。
  - **全链路标题联动**：自动提炼的标题会在 Telegram 状态消息中实时同步反馈（`✨ NotebookLM 自动生成标题：《...》`），并无缝赋名至生成的双人播客音频播放卡片、下载文件与知识信息图。

- **双产物协同生成与交付**：
  - 🎙️ **双人播客音频（Deep Dive）**：基于所有聚合素材，生成全程使用**中文（普通话）**进行的深度、自然、生动的主持人对谈剖析。
  - 📊 **知识信息图（Infographic）**：在同一笔记本中同步生成知识信息图，严格规范为**纵向（Portrait）**、**标准详细度（Standard，精简字数、降低渲染变形）**与**中文呈现**。
  - 交付顺序：机器人优先推送高清信息图预览，随后推送原生防超时的 40MB+ 大音频播放卡片。

- **健壮的缓存管理与延迟释放机制**：
  - **交付成功后释放**：只有在信息图与播客音频均成功推送到 Telegram 后，才安全清空暂存区，并物理清理本地 `workspace/downloads` 产生的临时文件（包括提取产生的 `.md` 及其原始下载图片）。
  - **失败全量保留重试**：任一环节（CLI 报错、超时、网络中断、Telegram 上传中断等）失败时，暂存素材与本地转换文件均**完整保留**，用户只需在 Telegram 回复 `/make` 即可立即重试，无需重新上传素材。
  - **多重候选目录扫描策略**：子进程执行完成后，系统自动跨 `workspace/outputs/`、`workspace/` 及 `~/Downloads/gemini-notebook` 目录智能扫描捕获最新生成物并规整落盘，避免因底层工具默认下载路径差异造成产物遗失。

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
│   └── antigravity_runner.py # Antigravity CLI 子进程调度、标题生成与产物捕获
├── workspace/            # 运行时动态数据目录
│   ├── downloads/        # 暂存 Telegram 下载与预处理后的素材
│   └── outputs/          # Antigravity 导出音频与信息图的交付目录
├── logs/                 # 运行时服务日志存储目录
│   └── bot.log           # 机器人标准输出与运行日志
├── nlmpodcastbot.service # Systemd 生产环境系统级守护进程配置模板
├── common.sh             # 运维脚本公共函数库与环境配置
├── start.sh              # 启动服务脚本（环境预检 + 防重复启动 + 存活验证）
├── stop.sh               # 停止服务脚本（安全优雅终止 SIGTERM + 超时 SIGKILL）
├── restart.sh            # 重启服务脚本
├── status.sh             # 服务与工作区状态全景查询脚本（进程/资源/缓存/配置）
├── logs.sh               # 日志实时追踪与关键词过滤脚本
├── cleanup.sh            # 缓存与过期素材清理脚本（支持 dry-run 与 force）
├── health-check.sh       # 自动化健康体检与报警脚本（退出码 0/1/2）
└── deploy.sh             # 一键自动化部署、依赖更新与失败自动回滚脚本
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

## 🚀 安装与部署指南

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

### 3. 服务启动与生产部署方案

针对不同运行场景，系统提供了三种部署方式：

#### 方案 A：运维脚本管理（推荐日常使用）

项目自带完善的 Shell 运维工具链，已内置配置自检、进程锁防重与存活验证：

```bash
# 启动后台服务
./start.sh

# 检查运行状态
./status.sh

# 查看实时日志
./logs.sh -f

# 停止或重启
./stop.sh
./restart.sh
```

#### 方案 B：Systemd 系统级服务（推荐 Linux 生产服务器）

适用于 Ubuntu / Debian / CentOS / Rocky Linux 等云服务器，具备系统开机自启、崩溃秒级自动拉起（`Restart=always`）与标准 Journal 日志集成：

1. **配置服务文件**：根据服务器的实际用户与项目绝对路径，调整项目根目录下的 `nlmpodcastbot.service`。
2. **安装并启用服务**：
   ```bash
   # 复制服务文件至系统目录
   sudo cp nlmpodcastbot.service /etc/systemd/system/

   # 重新加载 systemd 配置
   sudo systemctl daemon-reload

   # 设置开机自启并立即启动
   sudo systemctl enable --now nlmpodcastbot
   ```
3. **日常管理命令**：
   ```bash
   sudo systemctl status nlmpodcastbot     # 查看运行状态
   sudo systemctl restart nlmpodcastbot    # 重启服务
   sudo systemctl stop nlmpodcastbot       # 停止服务
   journalctl -u nlmpodcastbot -f          # 实时查看 systemd 日志
   ```

#### 方案 C：前台调试与轻量后台

- **前台调试（本地开发）**：
  ```bash
  .venv/bin/python bot.py
  ```
- **PM2 管理**：
  ```bash
  pm2 start .venv/bin/python --name "nlm-podcast-bot" -- bot.py
  ```

---

## 🛠️ 运维工具链指南

项目在根目录提供了一套企业级 Bash 运维工具链，基于 `common.sh` 公共基座构建，统一支持 ANSI 彩色高亮终端输出、配置解析与错误处理：

### 运维工具矩阵

| 脚本名称 | 核心功能 | 典型使用示例 | 适用场景 |
| :--- | :--- | :--- | :--- |
| `start.sh` | 启动后台服务 | `./start.sh` | 检查配置、防重启动并后台启动 Bot |
| `stop.sh` | 停止后台服务 | `./stop.sh` | 优雅终止进程（SIGTERM 10s 超时升级 SIGKILL） |
| `restart.sh` | 快速平滑重启 | `./restart.sh` | 修改配置或代码后一键重启 |
| `status.sh` | 服务全景状态巡检 | `./status.sh` | 查看进程 PID、运行时长、CPU/内存、缓存统计与配置校验 |
| `logs.sh` | 跟踪与分析日志 | `./logs.sh -f`<br>`./logs.sh -n 50 -e` | 实时日志流跟随、按行截取、高亮错误、日志清空 |
| `health-check.sh` | 自动化健康体检 | `./health-check.sh` | 检查进程存活、CLI 可用性、TG API 连通性与磁盘（退出码 0/1/2） |
| `cleanup.sh` | 缓存与过期文件清理 | `./cleanup.sh --dry-run`<br>`./cleanup.sh --force` | 清理过期下载素材（>24h）、产物（>72h）与日志（>7d） |
| `deploy.sh` | 自动化部署与热更新 | `./deploy.sh` | Git 自动拉取、Stash 保护、依赖更新、重启、健康检查与自动回滚 |

### 常用运维场景说明

#### 1. 监控服务与资源消耗
```bash
./status.sh
```
输出包含：
- **进程核心指标**：Active 状态、PID、运行时间、物理内存占用（MB）、CPU 使用率。
- **工作区容量状态**：`workspace/downloads/` 和 `workspace/outputs/` 文件数量与总大小。
- **核心配置校验**：Telegram Token、白名单 User ID、Antigravity 模型及代理设定。

#### 2. 日志追踪与异常排查
```bash
./logs.sh -f            # 实时跟随日志输出 (tail -f)
./logs.sh -n 100        # 查看最近 100 行日志
./logs.sh -e            # 筛选包含 ERROR / WARNING / Exception 的异常记录
./logs.sh --clear       # 安全清空当前日志文件
```

#### 3. 自动化健康体检与监控告警
```bash
./health-check.sh
echo $?  # 退出状态码：0=健康, 1=警告(如CLI不可用/磁盘偏高), 2=致命异常(进程挂掉/TG不通)
```
可直接配置进监控脚本或 Crontab：若退出码为 2 则通过邮件或 Webhook 触发自动报警。

#### 4. 定时清理磁盘缓存
```bash
# 模拟执行，仅预览即将清理的文件清单，不产生实际删除
./cleanup.sh --dry-run

# 免交互强制清理，适合写入 crontab 定时运行 (如每日凌晨执行)
./cleanup.sh --force
```

#### 5. 生产代码热更新与安全回滚
```bash
./deploy.sh
```
执行完整 CI/CD 闭环：
1. 检查 Git 工作区干净度（未提交改动自动询问是否 `git stash`）；
2. 拉取当前分支最新代码（`git pull`）；
3. 自动同步虚拟环境依赖（`pip install -r requirements.txt`）；
4. 调用 `./restart.sh` 平滑重启服务；
5. 调用 `./health-check.sh` 验证新版本健康状态；
6. **自动回滚保障**：若启动失败或健康检查未通过，脚本自动执行 `git reset --hard` 回滚到更新前 Commit 并恢复原服务。

---

## 💬 机器人指令与使用指南

| 指令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `/start` | 查看欢迎信息、支持的素材类型与帮助说明 | `/start` |
| `/status` | 查看当前暂存区中的素材清单与数量 | `/status` |
| `/make [标题]` | 触发合成任务，制作中文双人播客与知识信息图（**标题为可选参数**；若留空，系统将基于素材智能提炼 8-15 字精炼中文标题） | `/make`<br>`/make 具身智能与大模型前沿综述` |
| `/clear` | 清空当前暂存区中的所有素材 | `/clear` |

### 典型使用流程：

1. **持续剪藏**：在日常阅读或调研过程中，将推特/公众号长文链接、技术论文截图、语音备忘录随手转发给机器人。
2. **确认素材**：发送 `/status`，确认素材已被识别（例如：`🔗 2 篇链接、🖼️ 1 张图解提取文档、🎙️ 1 段录音`）。
3. **一键生成**：
   - **方式一（指定标题）**：发送 `/make 2026 AI Agent 架构剖析`；
   - **方式二（智能自动生成标题）**：直接发送 `/make`，系统将自动分析聚合素材的核心内容并生成恰当的中文标题。
4. **进度反馈**：机器人在 Telegram 会话中实时更新进度：
   - `1/4 正在创建笔记本与挂载素材...`
   - `2/4 素材已就绪，已触发双人播客与知识信息图合成...`
   - `3/4 云端正在深度合成播客与信息图中，请稍候（已耗时 X分X秒）...`
   - 若为自动生成标题，会在标题解析完成后展示：`✨ NotebookLM 自动生成标题：《...》`
5. **成品接收**：
   - 🖼️ 优先推送 **📊《标题》知识信息图**（纵向·标准版，可点击放大浏览高清图解）。
   - 🎧 紧接着推送 **🎙️《标题》双人深度播客**（附带时长、大小信息，支持后台播放与倍速收听）。
6. **自动清理**：两者成功推送到 Telegram 后，暂存素材自动清空，并物理清理磁盘临时提取产生的 Markdown 及原始图片。

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
5. **服务启动后瞬间退出？**
   - 运行 `./logs.sh -n 30` 或 `./status.sh` 排查。常见原因包括 `.env` 未配置、Token/白名单依然是占位符、网络代理无法连接 Telegram API，或 Python 依赖未完整安装。

