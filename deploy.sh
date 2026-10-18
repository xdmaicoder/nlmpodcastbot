#!/usr/bin/env bash
# ==============================================================================
# deploy.sh - Telegram NotebookLM Bot 自动化部署与热更新脚本
# 流程：
#   1. Git 状态检查与当前版本记录 (用于回滚)
#   2. 拉取最新代码 (git pull)
#   3. 更新虚拟环境依赖 (pip install -r requirements.txt)
#   4. 校验配置文件与语法合法性
#   5. 重启服务 (restart.sh)
#   6. 自动化健康检查 (health-check.sh)
#   7. 失败自动安全回滚至上一版本
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"
echo -e "${COLOR_BOLD} 🚀 正在开始部署 / 更新 Telegram NotebookLM Bot...${COLOR_NC}"
echo -e "${COLOR_BOLD}======================================================${COLOR_NC}"

# 1. 检查 Git 仓库
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    log_error "当前目录不是有效的 Git 仓库，无法执行 git pull 部署！"
    exit 1
fi

PREV_COMMIT=$(git rev-parse HEAD)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
log_info "当前分支: ${COLOR_CYAN}${CURRENT_BRANCH}${COLOR_NC} | 当前版本: ${COLOR_YELLOW}${PREV_COMMIT:0:8}${COLOR_NC}"

# 检查是否有未提交的代码修改（忽略未跟踪文件）
if [ -n "$(git status --porcelain -uno)" ]; then
    log_warn "工作区检测到未提交的代码变更："
    git status --short -uno
    echo ""
    read -r -p "是否暂存现有修改并继续更新? (git stash) [y/N]: " STASH_CONFIRM
    case "$STASH_CONFIRM" in
        [yY][eE][sS]|[yY])
            git stash
            log_info "本地未提交修改已保存至 git stash。"
            ;;
        *)
            log_error "部署已中止，请先处理工作区未提交修改。"
            exit 1
            ;;
    esac
fi

# 2. 拉取最新远端代码
log_info "正在从远端拉取最新代码 (git pull)..."
if ! git pull origin "$CURRENT_BRANCH"; then
    log_error "代码拉取失败！已保留当前运行状态不变。"
    exit 1
fi

NEW_COMMIT=$(git rev-parse HEAD)
if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
    log_info "代码已是最新版本 (${NEW_COMMIT:0:8})，无需重新合并。"
else
    log_success "代码成功更新至版本: ${COLOR_GREEN}${NEW_COMMIT:0:8}${COLOR_NC}"
fi

# 定义回滚处理函数
rollback() {
    log_error "部署校验未通过，正在启动安全回滚机制..."
    git reset --hard "$PREV_COMMIT"
    log_info "代码已回滚至: ${PREV_COMMIT:0:8}"
    
    log_info "正在恢复依赖..."
    "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt" >/dev/null 2>&1 || true
    
    log_info "正在重启旧版本服务..."
    "$SCRIPT_DIR/restart.sh"
    
    log_warn "服务已回滚并恢复为更新前的版本。"
    exit 1
}

# 3. 更新依赖库
log_info "正在检查并更新 Python 依赖库..."
if ! "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"; then
    log_error "依赖库安装失败！"
    rollback
fi

# 4. 验证配置文件与核心加载
log_info "正在验证核心配置与环境..."
if ! "$VENV_PYTHON" -c "import config; config.validate_config()"; then
    log_error "配置验证失败！请检查 .env 配置。"
    rollback
fi

# 5. 重启服务
log_info "正在重新启动 Bot 服务..."
if ! "$SCRIPT_DIR/restart.sh"; then
    log_error "服务重启失败！"
    rollback
fi

# 6. 运行健康检查 (等待 3 秒后巡检)
sleep 3
log_info "正在执行部署后健康检查验证..."
if ! "$SCRIPT_DIR/health-check.sh"; then
    log_error "健康检查未通过！"
    rollback
fi

echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
echo -e "${COLOR_GREEN} 🎉 部署更新全部完成，Bot 服务运行健康！${COLOR_NC}"
echo -e "  部署前版本:   ${PREV_COMMIT:0:8}"
echo -e "  当前运行版本: ${NEW_COMMIT:0:8}"
echo -e "  分支:         $CURRENT_BRANCH"
echo -e "${COLOR_GREEN}======================================================${COLOR_NC}"
