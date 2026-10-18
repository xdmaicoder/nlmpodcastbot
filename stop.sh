#!/usr/bin/env bash
# ==============================================================================
# stop.sh - Telegram NotebookLM Bot 停止服务脚本
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🛑 正在停止 Telegram NotebookLM Bot 服务...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

PID=$(get_bot_pid || true)

if [ -z "$PID" ]; then
    log_info "服务当前未在运行。"
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        log_info "已清理残留的 PID 锁文件: $PID_FILE"
    fi
    exit 0
fi

log_info "找到目标运行进程 PID: ${COLOR_CYAN}$PID${COLOR_NC}"
log_info "正在发送优雅退出信号 (SIGTERM)..."
kill -15 "$PID" 2>/dev/null || true

# 优雅等待最多 10 秒
TIMEOUT=10
WAITED=0
while [ $WAITED -lt $TIMEOUT ]; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo -e "${COLOR_GREEN}✅ 服务已优雅停止 (耗时 ${WAITED}s)。${COLOR_NC}"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
    WAITED=$((WAITED + 1))
    echo -n "."
done
echo ""

# 超时处理：强制杀死
log_warn "服务未在 ${TIMEOUT} 秒内退出，正在发送强制终止信号 (SIGKILL)..."
kill -9 "$PID" 2>/dev/null || true
sleep 1

if ! kill -0 "$PID" 2>/dev/null; then
    echo -e "${COLOR_GREEN}✅ 服务已被强制终止 (PID: $PID)。${COLOR_NC}"
    rm -f "$PID_FILE"
    exit 0
else
    log_error "进程终止失败！无法杀死 PID $PID，请检查系统权限。"
    exit 1
fi
