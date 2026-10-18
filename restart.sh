#!/usr/bin/env bash
# ==============================================================================
# restart.sh - Telegram NotebookLM Bot 重启服务脚本
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🔄 正在重启 Telegram NotebookLM Bot 服务...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

# 1. 执行停止
"$SCRIPT_DIR/stop.sh"

# 2. 间隔缓冲
sleep 1

# 3. 执行启动
"$SCRIPT_DIR/start.sh"
