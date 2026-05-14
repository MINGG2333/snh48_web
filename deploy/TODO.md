# 🚀 备案完成前部署步骤

## 同步策略

| 内容 | 方式 | 大小 |
|---|---|---|
| 网站代码 `website/` + `deploy/` | GitHub（`git clone snh48_web`） | ~200KB |
| 问答系统 `transcript_analyze/` | GitHub（`git clone transcript_analyze`） | ~300KB |
| 源数据 `transcript_analyze/download_records.json` | SCP 上传 | 114KB |
| 字幕文件 `transcript_analyze/firered_output_batch/` | SCP 上传 | 124MB |
| HuggingFace 模型缓存 | SCP 上传 | 391MB |

---

## 第1步：腾讯云安全组放行端口 8000

登录腾讯云控制台 → **云服务器 → 安全组** → 添加入站规则：
- 来源：`0.0.0.0/0`，协议端口：`TCP:8000`，策略：允许

---

## 第2步：SSH 登录，安装基础软件，配置 GitHub

```bash
ssh root@124.222.72.203

# 安装基础软件
yum install -y python3 python3-pip git
python3 -m pip install virtualenv

# 配置 GitHub SSH key（选 HTTPS 密码方式需在下面改 clone 地址）
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
复制输出的公钥 → 打开 [github.com/settings/keys](https://github.com/settings/keys) → 添加 New SSH Key

---

## 第3步：从 GitHub 拉取代码

```bash
# clone snh48_web（含 website/ + deploy/）
git clone git@github.com:MINGG2333/snh48_web.git /home/snh48_web

# clone transcript_analyze 到 snh48_web 子目录
cd /home/snh48_web
git clone git@github.com:MINGG2333/transcript_analyze.git

# 确认结构
ls -F
# deploy/  transcript_analyze/  website/
```

---

## 第4步：虚拟环境 + 安装依赖

```bash
cd /home/snh48_web
python3 -m virtualenv venv
source venv/bin/activate

pip install -r website/requirements.txt
pip install -r transcript_analyze/requirements_kb_qa.txt
```

---

## 第5步：上传数据文件和模型缓存

**在您的本地电脑执行：**

```bash
# 上传源数据（download_records.json + 字幕文件）
cd /mnt/zhitainew/snh48
tar czf /tmp/snh48_data.tar.gz download_records.json firered_output_batch
scp /tmp/snh48_data.tar.gz root@124.222.72.203:/home/snh48_web/transcript_analyze/
rm /tmp/snh48_data.tar.gz

# 上传 huggingface 模型缓存
cd /home/mingg/.cache/huggingface
tar czf /tmp/hf_model.tar.gz hub/models--shibing624--text2vec-base-chinese
scp /tmp/hf_model.tar.gz root@124.222.72.203:/home/
rm /tmp/hf_model.tar.gz
```

**然后在 SSH 终端：**

```bash
# 解压源数据到 transcript_analyze/ 目录下
cd /home/snh48_web/transcript_analyze
tar xzf snh48_data.tar.gz
rm snh48_data.tar.gz
# 确认
ls -la download_records.json
ls -d firered_output_batch

# 解压 huggingface 模型到缓存目录
mkdir -p /root/.cache/huggingface
tar xzf /home/hf_model.tar.gz -C /root/.cache/huggingface
rm /home/hf_model.tar.gz
# 确认
ls /root/.cache/huggingface/hub/models--shibing624--text2vec-base-chinese/snapshots/
```

---

## 第6步：构建知识库

```bash
git config core.filemode false
chmod +x ./script/run_kb_qa_build.sh
nohup ./script/run_kb_qa_build.sh & echo "下载任务已启动，PID: $!"
tail -20 kb_qa.log
```

---

## 第7步：创建 .env 配置文件

> **⚠️ 不要把密码写在代码里！** 代码里的密码会进入 Git 历史，谁都能查到。
> 正确做法是把密码写在 `.env` 文件中（`.gitignore` 已排除 `.env`，不会进 Git）。

```bash
cd /home/snh48_web

# 创建 .env 文件，写入密码和 API Key
cat > .env << 'EOF'
# 网站密码：访问者必须输入此密码才能使用 AI 问答
SITE_PASSWORD=xxxxxxxxx

# DeepSeek API Key（问答系统必须）
DEEPSEEK_API_KEY=你的真实DeepSeekKey
EOF

# 重要：限制权限，防止其他用户读取
chmod 600 .env

# 确认
ls -la .env
```

> **安全性说明**：
> - 密码写在 `.env` 中，此文件已被 `.gitignore` 排除，**不会进入 Git 仓库**
> - `.env` 可同时存放 `SITE_PASSWORD` 和 `DEEPSEEK_API_KEY`，一劳永逸
> - 即使 SSH 断开、重启服务器，只要 `.env` 文件还在，密码就不会丢失
> - `chmod 600` 确保只有 root 能读取该文件
> - 前端 Q&A 页面会自动弹出密码输入框，输入正确前无法提问

## 第8步：启动服务

```bash
cd /home/snh48_web
source venv/bin/activate

# 后端测试（默认路径已指向 transcript_analyze/ 下，可省略不传参数）
python transcript_analyze/run_kb_qa.py --debug ask --question "陈嘉仪和北舞的关联是什么？"
# 也可显式指定（等价）：
python transcript_analyze/run_kb_qa.py \
  --records transcript_analyze/download_records.json \
  --subtitle-root transcript_analyze/firered_output_batch \
  --kb-dir transcript_analyze/video_knowledge_db \
  --debug \
  ask \
  --question "陈嘉仪和北舞的关联是什么？"

# 前台测试
python -m website.main
```

看到 `Uvicorn running on http://0.0.0.0:8000` 说明成功。`Ctrl+C` 停止后，以**后台方式**运行并**保存日志到文件**（见下方说明）。

---

### 📋 日志保存说明

启动服务时，日志默认打印到终端。要让日志持久保存到文件，请从以下三种方式中选择一种。

---

### 方式 A：使用 nohup（⭐ 推荐，最简单）

日志自动保存到 `/var/log/snh48/snh48.log`，会**同时记录标准输出和错误输出**：

```bash
# 确保日志目录存在
mkdir -p /var/log/snh48
chmod 755 /var/log/snh48

# 后台启动，日志写入文件
cd /home/snh48_web
source venv/bin/activate
nohup python -m website.main > /var/log/snh48/snh48.log 2>&1 &
echo "服务已启动，PID: $!"

# ── 查看实时日志 ──
tail -f /var/log/snh48/snh48.log

# ── 查看最近 50 行 ──
tail -50 /var/log/snh48/snh48.log

# ── 查看日志文件大小 ──
ls -lh /var/log/snh48/snh48.log

# ── 清空日志文件（不重启服务） ──
> /var/log/snh48/snh48.log

# ── 停止服务 ──
pkill -f "website.main"
```

---

### 方式 B：使用 screen（适合需要交互操作的场景）

screen 会在断开 SSH 后继续运行，适合需要偶尔手动操作或调试的场景。

```bash
# 1. 安装 screen（首次只需一次）
yum install -y screen

# 2. 确保日志目录存在
mkdir -p /var/log/snh48
chmod 755 /var/log/snh48

# 3. 创建新会话（自动保存日志到文件）
screen -S snh48 -dm bash -c "cd /home/snh48_web && source venv/bin/activate && python -m website.main 2>&1 | tee /var/log/snh48/snh48_screen.log"

# 或者手动启动（二选一）：
# 创建新会话
screen -S snh48
# 在 screen 中启动
cd /home/snh48_web
source venv/bin/activate
python -m website.main 2>&1 | tee /var/log/snh48/snh48_screen.log

# 4. 查看实时日志
tail -f /var/log/snh48/snh48_screen.log
```

**screen 相关操作：**

| 操作 | 快捷键 / 命令 |
|---|---|
| 启用日志写入文件 | `Ctrl+A` → 然后按 `H`（大写），screen 开始将输出写入 `screenlog.0` |
| 停止日志写入文件 | 再次按 `Ctrl+A` → `H`，关闭日志写入 |
| 进入滚动/复制模式 | `Ctrl+A` → `[`，用方向键/PageUp/PageDown 翻看历史输出，`Esc` 退出 |
| 断开（detach）会话 | `Ctrl+A` → `D`，服务在后台继续运行 |
| 重新连接会话 | `screen -r snh48` |
| 列出所有会话 | `screen -ls` |
| 查看保存的日志 | `tail -f /var/log/snh48/snh48_screen.log` |
| 停止服务 | 重新连接后 `Ctrl+C`；或 `pkill -f "website.main"`（在 screen 外执行） |
| **退出/关闭 screen 会话** | 先在 screen 内按 `Ctrl+C` 停止服务，然后输入 `exit` 或按 `Ctrl+D`，会话即被彻底关闭，自动回到主终端 |
| 结束 screen 会话（外部） | `screen -S snh48 -X quit`（在 screen 外执行，直接杀掉会话） |
| 强制结束 screen 会话（外部） | `screen -X -S snh48 kill`（在 screen 外执行，直接杀掉会话） |
| 清除已死的 screen 会话 | `screen -wipe`（清理已断开或已结束的僵死会话） |

> **💡 实战场景提示：**
> - **不想让服务继续运行？** → 进入 screen，`Ctrl+C` 停止服务 → `exit` 关闭会话
> - **想让服务在后台继续运行？** → `Ctrl+A` → `D` detach，断开但不停止
> - **重新回来查看？** → `screen -r snh48`

### ⚠️ Screen 常见问题：退出后 bash 提示符未正常显示

如果 `Ctrl+C` 返回主终端后，出现以下错误：
```
bash: __vsc_prompt_cmd_original: command not found
```

**原因：**
- `__vsc_prompt_cmd_original` 是 VS Code 的 Shell Integration 功能设置的钩子，在普通 SSH 终端中没有这个命令

**解决方法：**
- 按一次 **回车键** → 提示符恢复
- 或输入 `reset` 回车 → 彻底重置终端

---

### 方式 C：使用 systemd 服务（最专业，支持开机自启 + 自动日志轮转）

创建一个 systemd 服务文件，由系统管理服务生命周期和日志：

```bash
# 1. 创建服务文件
cat > /etc/systemd/system/snh48.service << 'EOF'
[Unit]
Description=SNH48 Website Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/snh48_web
EnvironmentFile=/home/snh48_web/.env
ExecStart=/home/snh48_web/venv/bin/python -m website.main
Restart=always
RestartSec=10

# 日志配置（自动轮转，保留 7 天）
StandardOutput=append:/var/log/snh48/snh48.log
StandardError=append:/var/log/snh48/snh48.log

[Install]
WantedBy=multi-user.target
EOF

# 2. 重载配置并启动
systemctl daemon-reload
systemctl enable snh48    # 设置开机自启
systemctl start snh48     # 启动服务

# 3. 常用管理命令
systemctl status snh48              # 查看服务状态
journalctl -u snh48 -f              # 查看实时日志（journal 方式）
tail -f /var/log/snh48/snh48.log         # 查看文件日志
systemctl restart snh48             # 重启服务
systemctl stop snh48                # 停止服务
systemctl disable snh48             # 取消开机自启
```

> **systemd 优势**：自动重启崩溃的服务、开机自启、日志自动轮转不会撑爆磁盘。

---

### 📊 日志管理速查

| 启动方式 | 日志位置 | 自动重启 | 开机自启 | 推荐场景 |
|---|---|---|---|---|
| **nohup** (推荐) | `/var/log/snh48/snh48.log` | ❌ | ❌ | 快速启动、临时运行 |
| **screen** | `/var/log/snh48/snh48_screen.log` | ❌ | ❌ | 调试、手动维护 |
| **systemd** | `/var/log/snh48/snh48.log` + `journalctl` | ✅ | ✅ | 生产环境长期运行 |

**日志轮转（可选）：** 如果使用 nohup 或 screen 长期运行，建议配置 logrotate 防止日志文件过大：

```bash
cat > /etc/logrotate.d/snh48 << 'EOF'
/var/log/snh48/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

logrotate 配置完成后会自动每天轮转，保留 7 天日志，自动压缩旧日志。

---

## 第9步：验证

浏览器打开 **http://124.222.72.203:8000**
- 首页：星空背景 + 彩色滚动文字
- `/qa`：AI 问答
- `/api/qa/status`：知识库状态

---

## 后续代码更新

本地修改后 push → SSH 中 git pull + 重启：

```bash
# 本地
cd /mnt/zhitainew/snh48_web && git add . && git commit -m "xxx" && git push
cd /mnt/zhitainew/snh48_web/transcript_analyze && git add . && git commit -m "xxx" && git push
```

然后在 SSH 终端 **pull 并重启**：

```bash
# SSH
# 更新 website/ + deploy/
cd /home/snh48_web && git pull
# 更新问答系统
cd /home/snh48_web/transcript_analyze && git pull

# 重启服务（密码和 API Key 已存在 .env 中，无需再 export）
pkill -f "website.main"
cd /home/snh48_web
source venv/bin/activate
nohup python -m website.main > /var/log/snh48/snh48.log 2>&1 &
```

---

## 备案完成后

- [x] 腾讯云 DNS 解析添加 A 记录：`www.xxx.com` → `124.222.72.203`
- [x] 用 `deploy/deploy.sh` 配置 Nginx + SSL（详见 `deploy/README.md`）
- [x] 添加备案号到页面底部（配置 `SITE_ICP` 环境变量即可显示）

---

## ⚠️ 注意事项
- **安全组**必须放行 TCP:8000 才能从浏览器访问
- **密码和 API Key** 写在 `.env` 文件中，重启服务器也不会丢失（无需每次 SSH 都重新设置）
- 建议服务器至少有 **2GB 内存**

---

## 🛡️ 防滥用策略说明

系统内置了**多层级速率限制**来保护服务器算力和 API 费用，所有阈值均可通过 `.env` 配置：

### 限制层级

| 层级 | 针对 | 默认值 | 限制类型 |
|---|---|---|---|
| **IP 级频率** | 每个 IP 地址 | 每 60 秒最多 5 次 | 滑动窗口 |
| **用户冷却** | 每个浏览器 | 两次提问至少间隔 30 秒 | 时间戳对比 |
| **日配额** | 每个浏览器 | 每天最多 50 次 | 日历日计数 |
| **并发限制** | 每个浏览器 | 最多同时处理 2 个任务 | 任务注册表 |
| **密码暴力破解** | 每个 IP 地址 | 每 300 秒最多 10 次 | 滑动窗口 |

### 修改默认值

在 `.env` 文件中添加以下任意变量即可覆盖：
```ini
QA_RATE_LIMIT_PER_WINDOW=10          # 每个 IP 每 60 秒最多 10 次
QA_RATE_LIMIT_WINDOW_SECONDS=120     # 时间窗口改为 120 秒
QA_USER_COOLDOWN_SECONDS=15          # 冷却改为 15 秒
QA_DAILY_QUOTA_PER_USER=100          # 每日配额改为 100 次
QA_MAX_CONCURRENT_PER_USER=3         # 并发最多 3 个
PASSWORD_RATE_LIMIT_PER_WINDOW=5     # 密码尝试更严格
PASSWORD_RATE_LIMIT_WINDOW_SECONDS=600 # 时间窗口 10 分钟
```

### 用户超限时的表现

当用户触及任何限制时，服务器会返回 **HTTP 429 (Too Many Requests)**，前端页面会显示对应的中文提示，例如：
- "请求过于频繁，请稍后再试"（IP 级限制）
- "提问过于频繁，请 15 秒后再试"（用户冷却）
- "今日提问次数已达上限（50 次），请明天再试"（日配额）
- "您有正在处理中的问题，请等待完成后再提问"（并发限制）
- "密码验证尝试过于频繁，请稍后再试"（密码暴力破解）

