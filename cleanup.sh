#!/usr/bin/env bash
# ==============================================================================
# cleanup.sh - Telegram NotebookLM Bot 缓存与历史文件清理脚本
# 清理策略：
#   - workspace/downloads: 清理超过 24 小时的临时上传/下载文件
#   - workspace/outputs:   清理超过 72 小时 (3天) 的历史播客音频与信息图
#   - logs/:               清理超过 7 天的历史日志归档文件
# 安全保障：
#   - 严格保留所有 .gitkeep 文件
#   - 默认需要人工输入确认 (y/N)
#   - 支持 --dry-run 预览
#   - 支持 --force / -y 用于 cron 定时免交互执行
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

DRY_RUN=0
FORCE=0

show_help() {
    echo -e "${COLOR_BOLD}使用方式:${COLOR_NC}"
    echo "  ./cleanup.sh              # 扫描过期文件并交互提示确认清理"
    echo "  ./cleanup.sh --dry-run    # 仅预览将被清理的文件，不执行任何删除"
    echo "  ./cleanup.sh --force      # 免交互强制清理 (适用于 cron 定时任务)"
    echo "  ./cleanup.sh -h           # 显示本帮助信息"
    exit 0
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -d|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -f|-y|--force)
            FORCE=1
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

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🧹 正在扫描过期缓存与生成物...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

TMP_LIST=$(mktemp /tmp/nlmpodcastbot_cleanup.XXXXXX)
trap 'rm -f "$TMP_LIST"' EXIT

# 1. 扫描 downloads (超过 24 小时 / 1440 分钟)
if [ -d "$DOWNLOADS_DIR" ]; then
    find "$DOWNLOADS_DIR" -type f ! -name ".gitkeep" -mmin +1440 >> "$TMP_LIST" 2>/dev/null || true
fi

# 2. 扫描 outputs (超过 72 小时 / 4320 分钟)
if [ -d "$OUTPUTS_DIR" ]; then
    find "$OUTPUTS_DIR" -type f ! -name ".gitkeep" -mmin +4320 >> "$TMP_LIST" 2>/dev/null || true
fi

# 3. 扫描 logs (超过 7 天 / 10080 分钟的归档日志)
if [ -d "$LOG_DIR" ]; then
    find "$LOG_DIR" -type f ! -name ".gitkeep" ! -name "bot.log" -mmin +10080 >> "$TMP_LIST" 2>/dev/null || true
fi

TOTAL_FILES=$(wc -l < "$TMP_LIST" | tr -d ' ')

if [ "$TOTAL_FILES" -eq 0 ]; then
    echo -e "${COLOR_GREEN}✅ 工作区非常整洁，未发现任何超过保留期的过期文件。${COLOR_NC}"
    exit 0
fi

# 计算待释放空间大小
TOTAL_BYTES=0
if [ -s "$TMP_LIST" ]; then
    TOTAL_BYTES=$(xargs -n 1 du -k < "$TMP_LIST" 2>/dev/null | awk '{sum+=$1} END {print sum}')
fi
TOTAL_HUMAN=$(awk -v k="${TOTAL_BYTES:-0}" 'BEGIN {
    if (k > 1048576) {
        printf "%.2f GB", k / 1048576
    } else if (k > 1024) {
        printf "%.2f MB", k / 1024
    } else {
        printf "%d KB", k
    }
}')

echo -e "  发现待清理文件数:   ${COLOR_YELLOW}${TOTAL_FILES}${COLOR_NC} 个"
echo -e "  预计可释放磁盘空间: ${COLOR_CYAN}${TOTAL_HUMAN}${COLOR_NC}"
echo -e "  保留规则:           downloads > 24h, outputs > 72h, logs > 7d"
echo ""

# 如果是 Dry-run 模式
if [ "$DRY_RUN" -eq 1 ]; then
    echo -e "${COLOR_BLUE}[Dry-Run 预览列表] 将被清理的文件如下：${COLOR_NC}"
    cat "$TMP_LIST" | sed 's/^/  - /'
    echo ""
    echo -e "${COLOR_GREEN}Dry-run 模式已结束，实际未删除任何文件。${COLOR_NC}"
    exit 0
fi

# 交互确认检查
if [ "$FORCE" -ne 1 ]; then
    echo -e "${COLOR_YELLOW}⚠️  警告: 即将永久删除以上过期文件，此操作不可逆！${COLOR_NC}"
    read -r -p "是否确认清理这些文件? [y/N]: " CONFIRM
    case "$CONFIRM" in
        [yY][eE][sS]|[yY])
            ;;
        *)
            echo -e "${COLOR_BLUE}已取消清理操作。${COLOR_NC}"
            exit 0
            ;;
    esac
fi

# 开始删除
log_info "正在清理过期文件..."
DELETED_COUNT=0
while IFS= read -r file; do
    if [ -f "$file" ]; then
        rm -f "$file"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < "$TMP_LIST"

echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
echo -e "${COLOR_GREEN} ✅ 清理完成！${COLOR_NC}"
echo -e "  成功删除文件:   ${DELETED_COUNT} 个"
echo -e "  释放磁盘空间:   ${TOTAL_HUMAN}"
echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
