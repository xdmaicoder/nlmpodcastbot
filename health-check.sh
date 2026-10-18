#!/usr/bin/env bash
# ==============================================================================
# health-check.sh - Telegram NotebookLM Bot 自动化健康体检脚本
# 退出状态码说明:
#   0 = 健康 (Healthy)
#   1 = 警告 (Warning)
#   2 = 异常 (Critical)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

STATUS_CODE=0
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🩺 正在执行 Telegram NotebookLM Bot 全面健康巡检...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

# 1. 检查主进程是否存活
PID=$(get_bot_pid || true)
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo -e "  [1/5] 进程存活检查:     ${COLOR_GREEN}✅ 正常 (PID: $PID)${COLOR_NC}"
else
    echo -e "  [1/5] 进程存活检查:     ${COLOR_RED}❌ 异常 (Bot 进程未运行)${COLOR_NC}"
    STATUS_CODE=2
fi

# 2. 检查 Antigravity CLI 工具可执行性
ANTIGRAVITY_BIN=$(get_env_val "ANTIGRAVITY_BIN" "antigravity")
CLI_PATH=""
if command -v "$ANTIGRAVITY_BIN" >/dev/null 2>&1; then
    CLI_PATH=$(command -v "$ANTIGRAVITY_BIN")
elif [ -x "$HOME/.local/bin/$ANTIGRAVITY_BIN" ]; then
    CLI_PATH="$HOME/.local/bin/$ANTIGRAVITY_BIN"
fi

if [ -n "$CLI_PATH" ]; then
    echo -e "  [2/5] Antigravity CLI:  ${COLOR_GREEN}✅ 正常 ($CLI_PATH)${COLOR_NC}"
else
    echo -e "  [2/5] Antigravity CLI:  ${COLOR_YELLOW}⚠️  警告 (未找到可执行文件: $ANTIGRAVITY_BIN)${COLOR_NC}"
    if [ "$STATUS_CODE" -lt 1 ]; then STATUS_CODE=1; fi
fi

# 3. 检查 Telegram API 网络连通性
echo -n "  [3/5] Telegram API:     "
CHECK_TG_RESULT=$("$VENV_PYTHON" -c "
import urllib.request, json, sys
from config import BOT_TOKEN, HTTP_PROXY
url = f'https://api.telegram.org/bot{BOT_TOKEN}/getMe'
proxies = {'https': HTTP_PROXY, 'http': HTTP_PROXY} if HTTP_PROXY else None
opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies)) if proxies else urllib.request.build_opener()
try:
    resp = opener.open(url, timeout=6)
    data = json.loads(resp.read().decode())
    if data.get('ok'):
        print(f'OK:{data.get(\"result\", {}).get(\"username\", \"unknown\")}')
    else:
        print(f'FAIL:{data.get(\"description\", \"API returned ok=false\")}')
except Exception as e:
    print(f'ERR:{str(e)[:100]}')
" 2>/dev/null || echo "ERR:Python runtime error")

if [[ "$CHECK_TG_RESULT" == OK:* ]]; then
    TG_USERNAME="${CHECK_TG_RESULT#OK:}"
    echo -e "${COLOR_GREEN}✅ 连通成功 (@${TG_USERNAME})${COLOR_NC}"
else
    echo -e "${COLOR_RED}❌ 连接失败 (${CHECK_TG_RESULT})${COLOR_NC}"
    STATUS_CODE=2
fi

# 4. 检查日志中的近期异常 (最近 100 行内是否有未恢复错误)
if [ -f "$LOG_FILE" ]; then
    RECENT_ERRORS=$(tail -n 100 "$LOG_FILE" 2>/dev/null | grep -E "ERROR|CRITICAL|Traceback" | tail -n 3 || true)
    if [ -n "$RECENT_ERRORS" ]; then
        echo -e "  [4/5] 错误日志检测:     ${COLOR_YELLOW}⚠️  警告 (日志尾部发现异常记录)${COLOR_NC}"
        if [ "$STATUS_CODE" -lt 1 ]; then STATUS_CODE=1; fi
    else
        echo -e "  [4/5] 错误日志检测:     ${COLOR_GREEN}✅ 正常 (无未解决的近期严重异常)${COLOR_NC}"
    fi
else
    echo -e "  [4/5] 错误日志检测:     ${COLOR_GREEN}✅ 正常 (暂无日志文件)${COLOR_NC}"
fi

# 5. 检查磁盘剩余空间 (工作区至少保留 1GB)
AVAIL_KB=$(df -k "$PROJECT_DIR" 2>/dev/null | tail -n 1 | awk '{print $4}' | tr -d ' ')
MIN_REQ_KB=1048576 # 1GB
if [ -n "$AVAIL_KB" ] && [ "$AVAIL_KB" -gt "$MIN_REQ_KB" ]; then
    AVAIL_GB=$(awk -v k="$AVAIL_KB" 'BEGIN { printf "%.1f GB", k / 1048576 }')
    echo -e "  [5/5] 磁盘可用空间:     ${COLOR_GREEN}✅ 充裕 (剩余可用 ${AVAIL_GB})${COLOR_NC}"
else
    echo -e "  [5/5] 磁盘可用空间:     ${COLOR_YELLOW}⚠️  警告 (磁盘空间不足 1GB，请尽快清理)${COLOR_NC}"
    if [ "$STATUS_CODE" -lt 1 ]; then STATUS_CODE=1; fi
fi

# 总结巡检结果
echo -e "${COLOR_BOLD}------------------------------------------------------${COLOR_NC}"
if [ "$STATUS_CODE" -eq 0 ]; then
    echo -e "  ${COLOR_GREEN}🎉 健康体检完成：所有检查项全部正常 (Exit Code: 0)${COLOR_NC}"
elif [ "$STATUS_CODE" -eq 1 ]; then
    echo -e "  ${COLOR_YELLOW}⚠️  健康体检完成：存在警告项，服务可能仍可部分工作 (Exit Code: 1)${COLOR_NC}"
else
    echo -e "  ${COLOR_RED}💥 健康体检完成：存在严重异常项，请立即处理！(Exit Code: 2)${COLOR_NC}"
fi
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

exit "$STATUS_CODE"
