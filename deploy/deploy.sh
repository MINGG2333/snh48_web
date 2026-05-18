#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# SNH48 演艺信息站 - 一键部署脚本
# 适用于腾讯云 OpenCloudOS / CentOS / Rocky Linux
# 运行方式：bash deploy.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e

PROJECT_DIR="/home/snh48_web"
SERVICE_NAME="snh48"
SERVICE_PORT=8000

echo "========================================"
echo "  SNH48 演艺信息站 - 部署脚本"
echo "========================================"

# ── 1. Check environment ───────────────────────────────────────────────────
echo ""
echo "[1/6] 检查环境..."

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 项目目录 $PROJECT_DIR 不存在！请先上传代码。"
    exit 1
fi

cd "$PROJECT_DIR"

# Check Python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ 未找到 Python3，正在安装..."
    yum install -y python3 python3-pip
    PYTHON=python3
fi
echo "✓ 使用 Python: $($PYTHON --version)"

# ── 2. Install system dependencies ─────────────────────────────────────────
echo ""
echo "[2/6] 安装系统依赖..."

# Install pip packages
$PYTHON -m pip install --upgrade pip
$PYTHON -m pip install virtualenv

# ── 3. Setup Python virtual environment ────────────────────────────────────
echo ""
echo "[3/6] 设置 Python 虚拟环境..."

if [ ! -d "venv" ]; then
    $PYTHON -m virtualenv venv
fi
source venv/bin/activate

# Install website dependencies
pip install -r website/requirements.txt

# Install QA dependencies
if [ -f "transcript_analyze/requirements_kb_qa.txt" ]; then
    pip install -r transcript_analyze/requirements_kb_qa.txt
fi

echo "✓ 依赖安装完成"

# ── 4. Create necessary directories ────────────────────────────────────────
echo ""
echo "[4/6] 创建必要的目录..."

mkdir -p /var/log/$SERVICE_NAME
mkdir -p $PROJECT_DIR/transcript_analyze/video_knowledge_db

echo "✓ 目录创建完成"

# ── 5. Setup Supervisor ───────────────────────────────────────────────────
echo ""
echo "[5/6] 配置 Supervisor 进程守护..."

# Create supervisor config
# ⚠️ 注意：supervisor 不会自动读取 .env 文件，密码和 API Key 需额外注入
# 推荐改用 systemd 方式（见 deploy/TODO.md → 方式 C），支持 EnvironmentFile 自动加载 .env
cat > /etc/supervisord.d/${SERVICE_NAME}.ini << EOF
[program:${SERVICE_NAME}]
directory=${PROJECT_DIR}
command=${PROJECT_DIR}/venv/bin/python -m website.main
user=root
autostart=true
autorestart=true
startretries=3
stderr_logfile=/var/log/${SERVICE_NAME}/error.log
stdout_logfile=/var/log/${SERVICE_NAME}/output.log
environment=
    HOST="0.0.0.0",
    PORT="${SERVICE_PORT}",
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}",
    DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}",
EOF

# Reload supervisor
if command -v supervisorctl &> /dev/null; then
    supervisorctl reread
    supervisorctl update
    supervisorctl start ${SERVICE_NAME}
    echo "✓ Supervisor 已启动"
else
    echo "⚠ supervisorctl 未找到，请手动启动服务："
    echo "  source venv/bin/activate && python -m website.main &"
fi

# ── 6. Configure firewall / iptables ──────────────────────────────────────
echo ""
echo "[6/6] 配置防火墙..."

# Open port 8000 for testing (before domain filing complete)
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=${SERVICE_PORT}/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    echo "✓ 防火墙端口 ${SERVICE_PORT} 已开放"
fi

echo ""
echo "========================================"
echo "  ✅ 部署完成！"
echo "========================================"
echo ""
echo "  访问地址: http://<服务器IP>:${SERVICE_PORT}"
echo ""
echo "  查看日志: tail -f /var/log/${SERVICE_NAME}/output.log"
echo "  重启服务: supervisorctl restart ${SERVICE_NAME}"
echo "  停止服务: supervisorctl stop ${SERVICE_NAME}"
echo ""
echo "  如需配置 Nginx 代理和 SSL，请参考 deploy/TODO.md 的「备案完成后」章节"
echo ""
