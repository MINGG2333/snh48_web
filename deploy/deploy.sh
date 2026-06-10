#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# SNH48 演艺信息站 - 旧版 CentOS 初始化脚本
# 适用于已有 /home/snh48_web 的腾讯云 OpenCloudOS / CentOS / Rocky Linux。
#
# 这个脚本不是当前日常部署入口，也不是完整迁移工具。
# 日常多服务器部署请使用：
#   python3 deploy/deploy.py deploy tencent
#   python3 deploy/deploy.py deploy tencent aliyun
#
# 如确需运行这个旧初始化脚本，显式设置：
#   RUN_LEGACY_BOOTSTRAP=1 bash deploy/deploy.sh
# ═══════════════════════════════════════════════════════════════════════════

set -e

if [ "${RUN_LEGACY_BOOTSTRAP:-}" != "1" ]; then
    echo "此脚本已标记为旧版 CentOS 初始化脚本，不再作为日常部署入口。"
    echo "日常部署请运行: python3 deploy/deploy.py deploy tencent"
    echo "确认要运行旧脚本时，请使用: RUN_LEGACY_BOOTSTRAP=1 bash deploy/deploy.sh"
    exit 2
fi

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
    HOST="127.0.0.1",
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

# Do not expose the backend service publicly by default.
# Public traffic should enter via Nginx on 80/443 and be proxied to 127.0.0.1:8000.
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --remove-port=${SERVICE_PORT}/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    echo "✓ 防火墙端口 ${SERVICE_PORT} 未对公网开放"
fi

echo ""
echo "========================================"
echo "  ✅ 部署完成！"
echo "========================================"
echo ""
echo "  本机验证: curl http://127.0.0.1:${SERVICE_PORT}"
echo "  公网访问: 请通过 Nginx 的 80/443 域名入口访问"
echo ""
echo "  查看日志: tail -f /var/log/${SERVICE_NAME}/output.log"
echo "  重启服务: supervisorctl restart ${SERVICE_NAME}"
echo "  停止服务: supervisorctl stop ${SERVICE_NAME}"
echo ""
echo "  如需配置 Nginx 代理和 SSL，请参考 deploy/TODO.md 的「备案完成后」章节"
echo ""
