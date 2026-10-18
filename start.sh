#!/usr/bin/env bash
# ==============================================================================
# start.sh - Telegram NotebookLM Bot 启动脚本
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🚀 正在启动 Telegram NotebookLM Bot 服务...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

# 1. 环境检查：.env 配置文件
if [ ! -f "$ENV_FILE" ]; then
    log_error "未找到配置文件 .env！"
    echo "  请先复制模板并配置 Token 与白名单："
    echo "  cp .env.example .env"
    echo "  vim .env"
    exit 1
fi

BOT_TOKEN=$(get_env_val "TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID=$(get_env_val "ALLOWED_USER_ID")

if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
    log_error ".env 中的 TELEGRAM_BOT_TOKEN 未配置或仍为默认占位符！"
    exit 1
fi

if [ -z "$ALLOWED_USER_ID" ] || [ "$ALLOWED_USER_ID" = "0" ] || [ "$ALLOWED_USER_ID" = "123456789" ]; then
    log_error ".env 中的 ALLOWED_USER_ID 未配置或仍为默认占位符！"
    exit 1
fi

# 2. 环境检查：Python 虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
    log_error "未检测到 Python 虚拟环境 (.venv) 或解释器不可用！"
    echo "  正在排查路径: $VENV_PYTHON"
    echo "  请先初始化虚拟环境并安装依赖："
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# 3. 运行状态检查：防止重复启动
if PID=$(get_bot_pid); then
    log_warn "服务已在运行中 (PID: ${COLOR_CYAN}$PID${COLOR_NC})，无需重复启动。"
    echo -e "  - 查看服务状态: ${COLOR_GREEN}./status.sh${COLOR_NC}"
    echo -e "  - 实时查看日志: ${COLOR_GREEN}./logs.sh -f${COLOR_NC}"
    echo -e "  - 如需重新启动: ${COLOR_GREEN}./restart.sh${COLOR_NC}"
    exit 0
fi

# 4. 确保工作目录存在
ensure_dirs

# 5. 启动后台守护进程
log_info "正在通过后台守护进程启动服务 (nohup)..."
nohup "$VENV_PYTHON" -u "$PROJECT_DIR/bot.py" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# 6. 等待并验证进程存活状态（防止因语法错误或 Token 无效瞬间闪退）
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
    echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
    echo -e "${COLOR_GREEN} ✅ Telegram Bot 服务已成功启动！${COLOR_NC}"
    echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
    echo -e "  ${COLOR_BOLD}进程 PID:${COLOR_NC}       $NEW_PID"
    echo -e "  ${COLOR_BOLD}运行环境:${COLOR_NC}       $($VENV_PYTHON --version)"
    echo -e "  ${COLOR_BOLD}PID 锁文件:${COLOR_NC}     $PID_FILE"
    echo -e "  ${COLOR_BOLD}日志文件:${COLOR_NC}       $LOG_FILE"
    echo ""
    echo -e "  💡 常用运维命令："
    echo -e "    - 查看运行状态:   ${COLOR_CYAN}./status.sh${COLOR_NC}"
    echo -e "    - 跟踪实时日志:   ${COLOR_CYAN}./logs.sh -f${COLOR_NC}"
    echo -e "    - 停止后台服务:   ${COLOR_CYAN}./stop.sh${COLOR_NC}"
    echo -e "    - 重启后台服务:   ${COLOR_CYAN}./restart.sh${COLOR_NC}"
    echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
    exit 0
else
    log_error "服务启动失败！进程启动后立即退出了。"
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
    fi
    echo -e "\n${COLOR_YELLOW}--- 最新日志片段 ($LOG_FILE) ---${COLOR_NC}"
    if [ -f "$LOG_FILE" ]; then
        tail -n 25 "$LOG_FILE"
    fi
    echo -e "${COLOR_YELLOW}--------------------------------------${COLOR_NC}"
    echo -e "  请根据上述报错排查，常见原因："
    echo "  1. TELEGRAM_BOT_TOKEN 错误或无网络访问能力 (需配置 HTTP_PROXY)"
    echo "  2. 依赖库缺失或版本冲突，可尝试 pip install -r requirements.txt"
    exit 1
fi
