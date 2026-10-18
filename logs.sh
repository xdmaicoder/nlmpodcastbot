#!/usr/bin/env bash
# ==============================================================================
# logs.sh - Telegram NotebookLM Bot 日志查看与实时追踪脚本
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

FOLLOW=0
LINES=50
ERROR_ONLY=0

show_help() {
    echo -e "${COLOR_BOLD}使用方式:${COLOR_NC}"
    echo "  ./logs.sh              # 默认查看最后 50 行"
    echo "  ./logs.sh -f           # 实时跟踪日志 (tail -f)"
    echo "  ./logs.sh -n 100       # 查看最后 100 行"
    echo "  ./logs.sh -e           # 仅显示包含 ERROR / WARNING 的日志"
    echo "  ./logs.sh -f -e        # 实时跟踪并仅过滤错误日志"
    echo "  ./logs.sh -h           # 显示本帮助信息"
    exit 0
}

# 参数解析
while [ "$#" -gt 0 ]; do
    case "$1" in
        -f|--follow)
            FOLLOW=1
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -e|--error)
            ERROR_ONLY=1
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo -e "${COLOR_RED}未知参数: $1${COLOR_NC}"
            show_help
            ;;
    esac
done

if [ ! -f "$LOG_FILE" ]; then
    log_warn "暂无日志文件 ($LOG_FILE)。"
    echo "  当服务启动并产生第一条输出时，日志文件将自动创建。"
    exit 0
fi

echo -e "${COLOR_CYAN}--- 查看日志: $LOG_FILE (默认行数: $LINES, 跟踪: $FOLLOW, 仅错误: $ERROR_ONLY) ---${COLOR_NC}"

# 构建 tail 命令
TAIL_CMD="tail -n $LINES"
if [ "$FOLLOW" -eq 1 ]; then
    TAIL_CMD="tail -f -n $LINES"
fi

if [ "$ERROR_ONLY" -eq 1 ]; then
    if [ "$FOLLOW" -eq 1 ]; then
        $TAIL_CMD "$LOG_FILE" | grep --line-buffered -E "ERROR|CRITICAL|Exception|Traceback|WARNING" | awk '{
            if ($0 ~ /ERROR|CRITICAL|Exception|Traceback/) {
                print "\033[0;31m" $0 "\033[0m"
            } else {
                print "\033[0;33m" $0 "\033[0m"
            }
            fflush()
        }'
    else
        $TAIL_CMD "$LOG_FILE" | grep -E "ERROR|CRITICAL|Exception|Traceback|WARNING" | awk '{
            if ($0 ~ /ERROR|CRITICAL|Exception|Traceback/) {
                print "\033[0;31m" $0 "\033[0m"
            } else {
                print "\033[0;33m" $0 "\033[0m"
            }
        }' || echo "未检索到近期错误或警告日志。"
    fi
else
    # 全量日志输出（带颜色高亮）
    $TAIL_CMD "$LOG_FILE" | awk '{
        if ($0 ~ /ERROR|CRITICAL|Exception|Traceback/) {
            print "\033[0;31m" $0 "\033[0m"
        } else if ($0 ~ /WARNING|WARN/) {
            print "\033[0;33m" $0 "\033[0m"
        } else if ($0 ~ /INFO/) {
            print "\033[0;36m" $0 "\033[0m"
        } else {
            print $0
        }
        fflush()
    }'
fi
