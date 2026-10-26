#!/bin/bash
# ============================================================
# QA测试工具平台 - 云服务器一键部署脚本
# 使用方式: chmod +x deploy.sh && ./deploy.sh
# ============================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置变量（请根据实际情况修改）
APP_NAME="web2026"
APP_DIR="/opt/${APP_NAME}"
LOG_DIR="${APP_DIR}/log"
PYTHON_ENV="testenv"
GUNICORN_PORT=2023
NGINX_CONF="/etc/nginx/conf.d/http.conf"

# 打印信息
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ============================================================
# 1. 系统环境检查与安装
# ============================================================
setup_system() {
    info "===== 步骤1: 系统环境检查 ====="
    
    # 检查是否为 root 用户
    if [ "$EUID" -ne 0 ]; then
        error "请使用 root 用户执行此脚本"
    fi
    
    # 更新系统包
    info "更新系统包..."
    if command -v yum &> /dev/null; then
        yum update -y
        yum install -y epel-release
        yum install -y python3 python3-pip python3-devel nginx gcc
    elif command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv python3-dev nginx gcc
    else
        error "不支持的包管理器，请手动安装 Python3、Nginx"
    fi
    
    info "系统环境安装完成"
}

# ============================================================
# 2. 安装 Miniconda（可选，如果服务器没有 conda）
# ============================================================
setup_conda() {
    info "===== 步骤2: 检查 Miniconda ====="
    
    if command -v conda &> /dev/null; then
        info "Miniconda 已安装，跳过"
        return
    fi
    
    info "正在安装 Miniconda..."
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p $HOME/miniconda3
    eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
    conda init
    rm /tmp/miniconda.sh
    
    info "Miniconda 安装完成"
}

# ============================================================
# 3. 创建 Python 虚拟环境并安装依赖
# ============================================================
setup_python_env() {
    info "===== 步骤3: 创建 Python 虚拟环境 ====="
    
    # 如果使用 conda
    if command -v conda &> /dev/null; then
        eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
        if conda env list | grep -q "${PYTHON_ENV}"; then
            warn "虚拟环境 ${PYTHON_ENV} 已存在，删除重建..."
            conda env remove -n ${PYTHON_ENV} -y
        fi
        conda create -n ${PYTHON_ENV} python=3.9 -y
        conda activate ${PYTHON_ENV}
    else
        # 使用 venv
        python3 -m venv /opt/${PYTHON_ENV}
        source /opt/${PYTHON_ENV}/bin/activate
    fi
    
    info "安装 Python 依赖..."
    cd ${APP_DIR}
    pip install --upgrade pip
    pip install -r requirements.txt
    
    info "Python 环境配置完成"
}

# ============================================================
# 4. 部署应用代码
# ============================================================
deploy_code() {
    info "===== 步骤4: 部署应用代码 ====="
    
    # 创建应用目录
    mkdir -p ${APP_DIR}
    mkdir -p ${LOG_DIR}
    
    # 如果是首次部署，提示用户上传代码
    if [ ! -f "${APP_DIR}/app.py" ]; then
        warn "请将项目代码上传到 ${APP_DIR} 目录"
        warn "可以使用 scp、git 或其他方式上传代码"
        warn "示例: git clone <your-repo-url> ${APP_DIR}"
        echo ""
        read -p "代码已上传？按回车继续..."
    fi
    
    # 配置环境变量
    if [ ! -f "${APP_DIR}/.env" ]; then
        warn "未找到 .env 文件，从模板创建..."
        if [ -f "${APP_DIR}/.env.example" ]; then
            cp ${APP_DIR}/.env.example ${APP_DIR}/.env
            warn "请编辑 ${APP_DIR}/.env 配置数据库等连接信息"
            warn "执行: vim ${APP_DIR}/.env"
            echo ""
            read -p ".env 已配置？按回车继续..."
        else
            error "未找到 .env.example 模板文件"
        fi
    fi
    
    info "代码部署完成"
}

# ============================================================
# 5. 配置 Nginx
# ============================================================
setup_nginx() {
    info "===== 步骤5: 配置 Nginx ====="
    
    # 备份原配置
    if [ -f "${NGINX_CONF}" ]; then
        cp ${NGINX_CONF} ${NGINX_CONF}.bak.$(date +%Y%m%d%H%M%S)
        info "已备份原 Nginx 配置"
    fi
    
    # 检查是否已存在配置
    if grep -q "location /${APP_NAME}/" ${NGINX_CONF} 2>/dev/null; then
        warn "Nginx 中已存在 /${APP_NAME}/ 配置，跳过"
    else
        # 添加反向代理配置
        cat >> ${NGINX_CONF} << EOF

# ===== QA测试工具平台 =====
location /${APP_NAME}/ {
    proxy_pass http://127.0.0.1:${GUNICORN_PORT}/${APP_NAME}/;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_connect_timeout 60s;
    proxy_read_timeout 120s;
}
EOF
        info "Nginx 配置已添加"
    fi
    
    # 检查配置
    nginx -t || error "Nginx 配置检查失败"
    
    # 重启 Nginx
    systemctl restart nginx
    systemctl enable nginx
    
    info "Nginx 配置完成"
}

# ============================================================
# 6. 配置 Systemd 服务（开机自启、进程守护）
# ============================================================
setup_systemd() {
    info "===== 步骤6: 配置 Systemd 服务 ====="
    
    # 获取 Python 和 gunicorn 路径
    if command -v conda &> /dev/null; then
        PYTHON_PATH="$HOME/miniconda3/envs/${PYTHON_ENV}/bin/python"
        GUNICORN_PATH="$HOME/miniconda3/envs/${PYTHON_ENV}/bin/gunicorn"
    else
        PYTHON_PATH="/opt/${PYTHON_ENV}/bin/python"
        GUNICORN_PATH="/opt/${PYTHON_ENV}/bin/gunicorn"
    fi
    
    # 创建 systemd 服务文件
    cat > /etc/systemd/system/${APP_NAME}.service << EOF
[Unit]
Description=QA Test Tool Platform - Gunicorn
After=network.target

[Service]
Type=notify
User=root
Group=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${GUNICORN_PATH} -c gunicorn_config.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=10
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    
    # 重新加载 systemd
    systemctl daemon-reload
    systemctl enable ${APP_NAME}
    systemctl start ${APP_NAME}
    
    info "Systemd 服务配置完成，服务名: ${APP_NAME}"
}

# ============================================================
# 7. 启动检查
# ============================================================
health_check() {
    info "===== 步骤7: 健康检查 ====="
    
    sleep 3
    
    # 检查 gunicorn 进程
    if ps -ef | grep -v grep | grep gunicorn > /dev/null; then
        info "✓ Gunicorn 进程运行正常"
        ps -ef | grep -v grep | grep gunicorn | head -3
    else
        error "✗ Gunicorn 未启动，请检查日志: ${LOG_DIR}/debug.log"
    fi
    
    # 检查端口监听
    if ss -tlnp | grep -q ":${GUNICORN_PORT}"; then
        info "✓ 端口 ${GUNICORN_PORT} 监听正常"
    else
        warn "✗ 端口 ${GUNICORN_PORT} 未监听"
    fi
    
    # 检查 Nginx
    if systemctl is-active --quiet nginx; then
        info "✓ Nginx 运行正常"
    else
        warn "✗ Nginx 未运行"
    fi
    
    echo ""
    info "=========================================="
    info "  部署完成！"
    info "  访问地址: http://<你的服务器IP>/${APP_NAME}/"
    info "=========================================="
    echo ""
    info "常用命令:"
    echo "  查看状态: systemctl status ${APP_NAME}"
    echo "  重启服务: systemctl restart ${APP_NAME}"
    echo "  停止服务: systemctl stop ${APP_NAME}"
    echo "  查看日志: journalctl -u ${APP_NAME} -f"
    echo "  Gunicorn日志: tail -f ${LOG_DIR}/debug.log"
}

# ============================================================
# 主流程
# ============================================================
main() {
    echo ""
    echo "=========================================="
    echo "  QA测试工具平台 - 云服务器部署脚本"
    echo "=========================================="
    echo ""
    
    setup_system
    deploy_code
    setup_python_env
    setup_nginx
    setup_systemd
    health_check
}

# 执行主流程
main
