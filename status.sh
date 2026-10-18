#!/usr/bin/env bash
# ==============================================================================
# status.sh - Telegram NotebookLM Bot 运行状态查询脚本
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 📊 Telegram NotebookLM Bot 服务状态概览${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

PID=$(get_bot_pid || true)

# 1. 进程核心状态
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    # 获取运行时间与资源
    ETIME=$(ps -p "$PID" -o etime= 2>/dev/null | tr -d ' ')
    RSS_KB=$(ps -p "$PID" -o rss= 2>/dev/null | tr -d ' ')
    CPU_PCT=$(ps -p "$PID" -o %cpu= 2>/dev/null | tr -d ' ')
    
    MEM_STR="未知"
    if [ -n "$RSS_KB" ] && [ "$RSS_KB" -gt 0 ] 2>/dev/null; then
        MEM_STR=$(awk -v r="$RSS_KB" 'BEGIN { printf "%.1f MB", r / 1024 }')
    fi

    echo -e "  状态:         ${COLOR_GREEN}● 运行中 (Active)${COLOR_NC}"
    echo -e "  进程 PID:     ${COLOR_CYAN}$PID${COLOR_NC}"
    echo -e "  运行时长:     $ETIME"
    echo -e "  内存占用:     $MEM_STR"
    echo -e "  CPU 使用:     ${CPU_PCT}%"
else
    echo -e "  状态:         ${COLOR_RED}○ 未运行 (Stopped)${COLOR_NC}"
fi

# 2. 日志文件状态
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(du -h "$LOG_FILE" 2>/dev/null | awk '{print $1}')
    LOG_MTIME=$(get_file_mtime "$LOG_FILE")
    echo -e "  日志文件:     $LOG_FILE (${LOG_SIZE}, 最后更新: ${LOG_MTIME})"
else
    echo -e "  日志文件:     ${COLOR_YELLOW}尚无日志生成 ($LOG_FILE)${COLOR_NC}"
fi

echo -e "\n${COLOR_BOLD}📁 工作目录状态:${COLOR_NC}"
DL_COUNT=$(find "$DOWNLOADS_DIR" -type f ! -name ".gitkeep" 2>/dev/null | wc -l | tr -d ' ')
DL_SIZE=$(du -sh "$DOWNLOADS_DIR" 2>/dev/null | awk '{print $1}')
OUT_COUNT=$(find "$OUTPUTS_DIR" -type f ! -name ".gitkeep" 2>/dev/null | wc -l | tr -d ' ')
OUT_SIZE=$(du -sh "$OUTPUTS_DIR" 2>/dev/null | awk '{print $1}')

echo -e "  - downloads (下载缓存):  ${COLOR_CYAN}${DL_COUNT}${COLOR_NC} 个文件 (总计: ${DL_SIZE:-0B})"
echo -e "  - outputs   (生成成果):  ${COLOR_CYAN}${OUT_COUNT}${COLOR_NC} 个文件 (总计: ${OUT_SIZE:-0B})"

echo -e "\n${COLOR_BOLD}⚙️  核心配置校验:${COLOR_NC}"
RAW_TOKEN=$(get_env_val "TELEGRAM_BOT_TOKEN")
RAW_USER=$(get_env_val "ALLOWED_USER_ID")
ANTIGRAVITY_BIN=$(get_env_val "ANTIGRAVITY_BIN" "antigravity")
ANTIGRAVITY_MODEL=$(get_env_val "ANTIGRAVITY_MODEL" "gemini-3.8-flash-medium")
PROXY=$(get_env_val "HTTP_PROXY" "$(get_env_val "HTTPS_PROXY")")

if [ -n "$RAW_TOKEN" ]; then
    echo -e "  - BOT_TOKEN:          ${COLOR_GREEN}$(mask_token "$RAW_TOKEN")${COLOR_NC}"
else
    echo -e "  - BOT_TOKEN:          ${COLOR_RED}[未配置]${COLOR_NC}"
fi

if [ -n "$RAW_USER" ]; then
    echo -e "  - 白名单用户 ID:      ${COLOR_CYAN}$RAW_USER${COLOR_NC}"
else
    echo -e "  - 白名单用户 ID:      ${COLOR_RED}[未配置]${COLOR_NC}"
fi

# 检查 Antigravity CLI 路径
CLI_RESOLVED=""
if command -v "$ANTIGRAVITY_BIN" >/dev/null 2>&1; then
    CLI_RESOLVED=$(command -v "$ANTIGRAVITY_BIN")
    echo -e "  - Antigravity CLI:    ${COLOR_GREEN}✅ 可用 ($CLI_RESOLVED)${COLOR_NC}"
elif [ -x "$HOME/.local/bin/$ANTIGRAVITY_BIN" ]; then
    CLI_RESOLVED="$HOME/.local/bin/$ANTIGRAVITY_BIN"
    echo -e "  - Antigravity CLI:    ${COLOR_GREEN}✅ 可用 ($CLI_RESOLVED)${COLOR_NC}"
else
    echo -e "  - Antigravity CLI:    ${COLOR_RED}❌ 未找到 ($ANTIGRAVITY_BIN)${COLOR_NC}"
fi
echo -e "  - 推理调度模型:       $ANTIGRAVITY_MODEL"

if [ -n "$PROXY" ]; then
    echo -e "  - 网络代理:           $PROXY"
else
    echo -e "  - 网络代理:           直连 (未配置代理)"
fi

# 3. 显示最新日志末尾 20 行
if [ -f "$LOG_FILE" ]; then
    echo -e "\n${COLOR_BOLD}📝 最新日志记录 (最近 20 行):${COLOR_NC}"
    echo -e "${COLOR_YELLOW}------------------------------------------------------${COLOR_NC}"
    tail -n 20 "$LOG_FILE"
    echo -e "${COLOR_YELLOW}------------------------------------------------------${COLOR_NC}"
    echo -e "  💡 如需实时跟踪日志，请执行: ${COLOR_CYAN}./logs.sh -f${COLOR_NC}"
fi
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
