#!/bin/bash
# ============================================================
# QA测试工具平台 - 一键更新脚本
# 作用：拉取最新代码 -> 依赖变更则安装 -> 重启 systemd 服务 -> 健康检查
# 使用：./update.sh            正常更新（无变更则自动跳过重启）
#       ./update.sh -f         强制重启（即使代码没变）
#       ./update.sh -n         只拉代码，不重启
#       ./update.sh -r         回滚到上一次更新的提交并重启
#       ./update.sh -r <hash>  回滚到指定提交并重启
# ============================================================

set -uo pipefail

# ---------------- 配置 ----------------
SERVICE_NAME="web2026"                       # systemd 服务名
HEALTH_URL="http://127.0.0.1:9090/web2026/"  # 本机健康检查地址
HEALTH_RETRY=10                              # 健康检查重试次数（每秒一次）
# 这台机器到 GitHub 会抖：常见「连 130 秒后超时，下一次就通」。
# 给单次探测加硬性超时并重试，避免一次抖动就判定断网。
REMOTE_PROBE_TIMEOUT=30                      # 单次探测远端的最长等待（秒）
REMOTE_PROBE_TRIES=3                         # 探测重试次数
REMOTE_PROBE_DELAY=5                         # 每次重试间隔（秒）
PULL_TRIES=3                                 # git pull 重试次数

# ---------------- 颜色 ----------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------------- 参数解析 ----------------
FORCE=0; NO_RESTART=0; ROLLBACK=0; ROLLBACK_TARGET=""
while [ $# -gt 0 ]; do
    case "$1" in
        -f|--force)      FORCE=1 ;;
        -n|--no-restart) NO_RESTART=1 ;;
        -r|--rollback)
            ROLLBACK=1
            # 仅当下一个参数不是选项时，才把它当作回滚目标
            if [ $# -ge 2 ] && [ "${2#-}" = "$2" ]; then
                ROLLBACK_TARGET="$2"
                shift
            fi
            ;;
        -h|--help)
            sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) error "未知参数: $1（用 -h 查看用法）" ;;
    esac
    shift
done

# ---------------- 定位项目目录 ----------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
[ -f "$APP_DIR/app.py" ] || error "未在 $APP_DIR 找到 app.py，请把本脚本放在 webTool 目录下"
cd "$APP_DIR" || error "无法进入目录 $APP_DIR"

command -v git >/dev/null 2>&1 || error "未找到 git"
GIT_DIR_TMP="$(git rev-parse --git-dir 2>/dev/null)" || error "$APP_DIR 不是 git 仓库"
LAST_COMMIT_FILE="$(cd "$GIT_DIR_TMP" && pwd)/last_update_commit"

CURRENT_COMMIT="$(git rev-parse --short HEAD)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
info "项目目录: $APP_DIR"
info "当前分支: $CURRENT_BRANCH    当前提交: $CURRENT_COMMIT"

# ---------------- 远端探测 ----------------
TIMEOUT_BIN="$(command -v timeout 2>/dev/null || true)"

# 单次 ls-remote（带上限）；timeout 不可用时不限制
probe_once() {
    if [ -n "$TIMEOUT_BIN" ]; then
        "$TIMEOUT_BIN" "$REMOTE_PROBE_TIMEOUT" git ls-remote origin "refs/heads/$CURRENT_BRANCH" 2>/dev/null
    else
        git ls-remote origin "refs/heads/$CURRENT_BRANCH" 2>/dev/null
    fi
}

# 多次探测，成功时把短 sha 打到 stdout；warn 一律走 stderr，不能被命令替换捕获
probe_remote() {
    local i result
    for i in $(seq 1 "$REMOTE_PROBE_TRIES"); do
        result="$(probe_once | awk '{print substr($1,1,7)}')"
        if [ -n "$result" ]; then
            echo "$result"
            return 0
        fi
        if [ "$i" -lt "$REMOTE_PROBE_TRIES" ]; then
            warn "远端无响应，${REMOTE_PROBE_DELAY} 秒后重试（第 $i/$REMOTE_PROBE_TRIES 次）" >&2
            sleep "$REMOTE_PROBE_DELAY"
        fi
    done
    return 1
}

# ---------------- 健康检查 ----------------
health_check() {
    local code
    if ! command -v curl >/dev/null 2>&1; then
        warn "未找到 curl，跳过健康检查（请手动确认 systemctl status $SERVICE_NAME）"
        return 0
    fi
    for i in $(seq 1 "$HEALTH_RETRY"); do
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" || echo 000)"
        if [ "$code" = "200" ]; then
            info "健康检查通过: $HEALTH_URL -> 200"
            return 0
        fi
        sleep 1
    done
    warn "健康检查失败: $HEALTH_URL 最后返回 $code"
    echo "----- 最近 30 行服务日志 -----"
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager 2>/dev/null || true
    return 1
}

# 进程是否落后于磁盘上的代码/配置（true = 不重启就不会生效）。
# 只比提交号是不够的：手工 git pull 过、或改了 .env 之后再跑本脚本，
# 提交号可能已经等于远端，旧逻辑会直接「无需重启」退出，新代码永远不生效。
STALE_REASON=""
service_needs_start() {
    local start_raw start_ts head_ts env_ts env_file
    systemctl is-active --quiet "$SERVICE_NAME" || return 0   # 没在运行，当然要起
    start_raw="$(systemctl show -p ActiveEnterTimestamp --value "$SERVICE_NAME" 2>/dev/null)"
    [ -n "$start_raw" ] || return 1                          # 拿不到就不自作主张
    start_ts="$(date -d "$start_raw" +%s 2>/dev/null)" || return 1

    head_ts="$(git log -1 --format=%ct 2>/dev/null)"
    if [ -n "$head_ts" ] && [ "$start_ts" -lt "$head_ts" ]; then
        STALE_REASON="服务启动时间早于当前提交 $CURRENT_COMMIT，内存里还是旧代码"
        return 0
    fi

    env_file="$APP_DIR/.env"
    if [ -f "$env_file" ]; then
        env_ts="$(stat -c %Y "$env_file" 2>/dev/null)"
        if [ -n "$env_ts" ] && [ "$env_ts" -gt "$start_ts" ]; then
            STALE_REASON=".env 在上次启动之后被修改过，进程里还是旧配置"
            return 0
        fi
    fi
    return 1
}

# ---------------- 重启服务 ----------------
restart_service() {
    command -v systemctl >/dev/null 2>&1 || error "未找到 systemctl，本脚本仅适用于 systemd 环境"
    info "重启服务: $SERVICE_NAME ..."
    systemctl restart "$SERVICE_NAME" || {
        warn "service 重启失败，尝试用 daemon-reload 后再次重启"
        systemctl daemon-reload
        systemctl restart "$SERVICE_NAME" || error "服务启动失败，请查看: journalctl -u $SERVICE_NAME -n 50 --no-pager"
    }
    if health_check; then
        systemctl is-active --quiet "$SERVICE_NAME" && info "服务状态: active (running)"
        return 0
    fi
    error "服务已重启但健康检查未通过，可执行 ./update.sh -r 回滚"
}

# ---------------- 回滚模式 ----------------
if [ "$ROLLBACK" -eq 1 ]; then
    TARGET="$ROLLBACK_TARGET"
    if [ -z "$TARGET" ]; then
        [ -s "$LAST_COMMIT_FILE" ] || error "没有上一次更新的提交记录，请显式指定回滚目标: ./update.sh -r <commit>"
        TARGET="$(cat "$LAST_COMMIT_FILE")"
    fi
    git cat-file -e "${TARGET}^{commit}" 2>/dev/null || error "无效的提交: $TARGET"
    warn "回滚 $CURRENT_COMMIT -> $TARGET"
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        warn "注意：回滚会丢弃已跟踪文件的未提交改动（git reset --hard）"
    fi
    git reset --hard "$TARGET" || error "回滚失败"
    info "已回滚，当前提交: $(git rev-parse --short HEAD)"
    restart_service
    info "回滚完成"
    exit 0
fi

# ---------------- 拉取代码 ----------------
# 只拦截已跟踪文件的改动（未跟踪文件不会阻塞 pull，仅提示）
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    warn "已跟踪文件存在未提交的本地改动："
    git status --porcelain --untracked-files=no | sed 's/^/    /'
    warn "这些改动会被 git pull 拒绝或覆盖，请先确认（git stash / git checkout -- <文件>）"
    error "已中止更新，未做任何改动"
fi
if [ -n "$(git status --porcelain --untracked-files=normal | grep '^??')" ]; then
    warn "存在未跟踪文件（不影响更新，仅提示）："
    git status --porcelain --untracked-files=normal | grep '^??' | sed 's/^/    /'
fi

if ! REMOTE_COMMIT="$(probe_remote)"; then
    warn "无法访问远端仓库（已探测 $REMOTE_PROBE_TRIES 次，均无响应）"
    warn "常见原因：服务器到 GitHub 的网络不通、需要代理，或凭据失效——不是分支分叉"
    warn "自查：curl -I --max-time 8 https://github.com ；git config --global --get http.proxy"
    warn "换条链路（本机能出网时，推荐）：在本机执行"
    warn "    python webTool/tools/make_patch.py --from $(git rev-parse --short HEAD)"
    warn "  再把生成的 dist/patch-*.sh 整段粘贴到本终端（不访问 GitHub，详见部署文档第九章）"
    warn "手工 bundle：本机 git bundle create 打包 -> scp 到服务器 -> git pull /tmp/xxx.bundle $CURRENT_BRANCH"
    error "已中止更新，未改动任何代码（服务仍在运行旧版本）"
fi
info "远端 $CURRENT_BRANCH: $REMOTE_COMMIT"

# 优先用已跟踪的上游分支，未配置上游时显式指定 origin + 当前分支
if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    PULL_CMD=(git pull --ff-only)
else
    PULL_CMD=(git pull --ff-only origin "$CURRENT_BRANCH")
fi
PULL_OK=0
for i in $(seq 1 "$PULL_TRIES"); do
    info "拉取代码: ${PULL_CMD[*]} ...（第 $i/$PULL_TRIES 次）"
    if "${PULL_CMD[@]}"; then
        PULL_OK=1
        break
    fi
    if [ "$i" -lt "$PULL_TRIES" ]; then
        warn "本次拉取失败，${REMOTE_PROBE_DELAY} 秒后重试"
        sleep "$REMOTE_PROBE_DELAY"
    fi
done
if [ "$PULL_OK" -ne 1 ]; then
    if ! probe_remote >/dev/null; then
        error "git pull 失败：当前无法连接远端仓库（网络/代理问题，已重试 $PULL_TRIES 次），请先确认连通性"
    fi
    error "git pull 失败：远端可访问，本地与远端可能已分叉。请手动确认（git status / git log --oneline -5）后再处理；不要直接 git reset --hard"
fi

NEW_COMMIT="$(git rev-parse --short HEAD)"
echo "$CURRENT_COMMIT" > "$LAST_COMMIT_FILE"

NEED_RESTART=0
[ "$NEW_COMMIT" != "$CURRENT_COMMIT" ] && NEED_RESTART=1
[ "$FORCE" -eq 1 ] && NEED_RESTART=1

if [ "$NEED_RESTART" -eq 0 ] && service_needs_start; then
    warn "代码提交号未变，但$STALE_REASON"
    warn "继续重启，否则这次的改动不会生效"
    NEED_RESTART=1
fi

if [ "$NEED_RESTART" -eq 0 ]; then
    info "代码已是最新（$NEW_COMMIT），无需重启"
    info "如需强制重启: ./update.sh -f"
    exit 0
fi

if [ "$NEW_COMMIT" != "$CURRENT_COMMIT" ]; then
    info "代码已更新: $CURRENT_COMMIT -> $NEW_COMMIT"
    git log --oneline "$CURRENT_COMMIT..$NEW_COMMIT" | sed 's/^/    /'
elif [ "$FORCE" -eq 1 ] && [ -z "$STALE_REASON" ]; then
    warn "代码无变更，按 -f 要求仍将重启服务"
fi

# ---------------- 依赖变更检查 ----------------
if git diff --name-only "$CURRENT_COMMIT" "$NEW_COMMIT" | grep -qx "requirements.txt"; then
    VENV_PIP="$APP_DIR/venv/bin/pip"
    if [ -x "$VENV_PIP" ]; then
        info "检测到 requirements.txt 变更，安装依赖 ..."
        "$VENV_PIP" install -r requirements.txt || error "依赖安装失败，已中止（服务未重启）"
    else
        warn "requirements.txt 有变更，但未找到 $VENV_PIP，请手动安装依赖"
    fi
else
    info "requirements.txt 无变更，跳过依赖安装"
fi

# ---------------- 重启 ----------------
if [ "$NO_RESTART" -eq 1 ]; then
    warn "按 -n 要求跳过重启，代码已更新但未生效"
    info "手动生效: systemctl restart $SERVICE_NAME"
    exit 0
fi

restart_service

echo ""
info "=========================================="
info "  更新完成: $CURRENT_COMMIT -> $NEW_COMMIT"
info "  访问地址: https://114.55.3.96/web2026/"
info "  回滚命令: ./update.sh -r        （回到 $CURRENT_COMMIT）"
info "=========================================="
echo ""
