#!/usr/bin/env bash
# ==============================================================================
# common.sh - Telegram NotebookLM Bot 运维通用函数与环境配置
# ==============================================================================

# 基础目录与文件路径定义
COMMON_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PROJECT_DIR="$COMMON_SCRIPT_DIR"
export PID_FILE="$PROJECT_DIR/.bot.pid"
export LOG_DIR="$PROJECT_DIR/logs"
export LOG_FILE="$LOG_DIR/bot.log"
export ENV_FILE="$PROJECT_DIR/.env"
export VENV_DIR="$PROJECT_DIR/.venv"
export VENV_PYTHON="$VENV_DIR/bin/python3"
export DOWNLOADS_DIR="$PROJECT_DIR/workspace/downloads"
export OUTPUTS_DIR="$PROJECT_DIR/workspace/outputs"

# 终端彩色输出支持（仅在终端交互环境下启用颜色）
if [ -t 1 ]; then
    COLOR_RED="\033[0;31m"
    COLOR_GREEN="\033[0;32m"
    COLOR_YELLOW="\033[0;33m"
    COLOR_BLUE="\033[0;34m"
    COLOR_MAGENTA="\033[0;35m"
    COLOR_CYAN="\033[0;36m"
    COLOR_BOLD="\033[1m"
    COLOR_NC="\033[0m" # No Color
else
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_BLUE=""
    COLOR_MAGENTA=""
    COLOR_CYAN=""
    COLOR_BOLD=""
    COLOR_NC=""
fi

# 日志与状态提示函数
log_info() {
    echo -e "${COLOR_BLUE}[INFO]${COLOR_NC} $*"
}

log_success() {
    echo -e "${COLOR_GREEN}[SUCCESS]${COLOR_NC} $*"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_NC} $*"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_NC} $*"
}

# 确保必要的运行时目录存在
ensure_dirs() {
    mkdir -p "$LOG_DIR" "$DOWNLOADS_DIR" "$OUTPUTS_DIR"
}

# 安全读取 .env 文件中的键值（无需 source，避免执行恶意代码）
get_env_val() {
    local key="$1"
    local default_val="$2"
    if [ ! -f "$ENV_FILE" ]; then
        echo "$default_val"
        return
    fi
    local val
    val=$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | head -n 1 | cut -d '=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
    if [ -n "$val" ]; then
        echo "$val"
    else
        echo "$default_val"
    fi
}

# 获取 Bot 进程 PID（带多层容错检测）
get_bot_pid() {
    local pid=""
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi

    # 兜底检测：根据项目路径匹配运行中的 bot.py 进程
    local matched_pid=""
    matched_pid=$(ps -eo pid,command | grep "[b]ot.py" | awk '{print $1}' | head -n 1)
    if [ -n "$matched_pid" ] && kill -0 "$matched_pid" 2>/dev/null; then
        # 自动同步 PID 到文件
        echo "$matched_pid" > "$PID_FILE"
        echo "$matched_pid"
        return 0
    fi

    return 1
}

# 判断 Bot 服务是否正在运行 (返回 0 表示正在运行，1 表示未运行)
is_bot_running() {
    if get_bot_pid >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 格式化文件修改时间（兼容 macOS 与 Linux）
get_file_mtime() {
    local target="$1"
    if [ ! -e "$target" ]; then
        echo "未生成"
        return
    fi
    # macOS stat
    if stat -f "%Sm" "$target" 2>/dev/null; then
        return
    # Linux stat
    elif stat -c "%y" "$target" 2>/dev/null | cut -d '.' -f1; then
        return
    else
        date -r "$target" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "未知"
    fi
}

# 掩码敏感 Token
mask_token() {
    local token="$1"
    local len=${#token}
    if [ "$len" -le 10 ]; then
        echo "******"
    else
        local prefix="${token:0:5}"
        local suffix="${token: -4}"
        echo "${prefix}******${suffix}"
    fi
}
