# 🚀 部署步骤清单

> 本文件按时间线组织部署步骤。请按顺序执行。

---

## 一、ICP 备案完成前（使用 IP:8000 测试）

### 1. 腾讯云安全组放行端口 8000

登录腾讯云控制台 → **云服务器 → 安全组** → 添加入站规则：
- 来源：`0.0.0.0/0`，协议端口：`TCP:8000`，策略：允许

> 80/443 端口在 ICP 备案完成后才需要放行。

### 2. SSH 登录，安装基础软件，配置 GitHub

```bash
ssh root@124.222.72.203

# 安装基础软件
yum install -y python3 python3-pip git
python3 -m pip install virtualenv

# 配置 GitHub SSH key
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```
复制输出的公钥 → 打开 [github.com/settings/keys](https://github.com/settings/keys) → 添加 New SSH Key

### 3. 从 GitHub 拉取代码

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

### 4. 虚拟环境 + 安装依赖

```bash
cd /home/snh48_web
python3 -m virtualenv venv
source venv/bin/activate

pip install -r website/requirements.txt
pip install -r transcript_analyze/requirements_kb_qa.txt
```

### 5. 上传数据文件和模型缓存

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

### 6. 构建知识库

```bash
git config core.filemode false
chmod +x ./script/run_kb_qa_build.sh
nohup ./script/run_kb_qa_build.sh & echo "下载任务已启动，PID: $!"
tail -20 kb_qa.log
```

### 7. 创建 .env 配置文件

> **⚠️ 不要把密码写在代码里！** 代码里的密码会进入 Git 历史。正确做法是把密码写在 `.env` 文件中（`.gitignore` 已排除 `.env`，不会进 Git）。

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

### 8. 启动服务

```bash
cd /home/snh48_web
source venv/bin/activate

# 后端测试
python transcript_analyze/run_kb_qa.py --debug ask --question "陈嘉仪和北舞的关联是什么？"

# 前台测试
python -m website.main
```

看到 `Uvicorn running on http://0.0.0.0:8000` 说明成功。`Ctrl+C` 停止后，以**后台方式**运行。

#### 日志保存说明

启动服务时，日志默认打印到终端。要让日志持久保存到文件，请从以下三种方式中选择一种。

**方式 A：nohup（⭐ 推荐，最简单）**

```bash
mkdir -p /var/log/snh48
chmod 755 /var/log/snh48

cd /home/snh48_web
source venv/bin/activate
nohup python -m website.main > /var/log/snh48/snh48.log 2>&1 &
echo "服务已启动，PID: $!"

# 查看实时日志
tail -f /var/log/snh48/snh48.log

# 停止服务
pkill -f "website.main"
```

**方式 B：screen（适合需要交互操作的场景）**

```bash
yum install -y screen
mkdir -p /var/log/snh48
chmod 755 /var/log/snh48

# 创建新会话（自动保存日志到文件）
screen -S snh48 -dm bash -c "cd /home/snh48_web && source venv/bin/activate && python -m website.main 2>&1 | tee /var/log/snh48/snh48_screen.log"

# 常用操作
screen -r snh48              # 重新连接
screen -ls                    # 列出所有会话
screen -S snh48 -X quit       # 结束会话

# 查看实时日志
tail -f /var/log/snh48/snh48_screen.log
```

**方式 C：systemd 服务（最专业，支持开机自启 + 自动日志轮转）**

```bash
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
StandardOutput=append:/var/log/snh48/snh48.log
StandardError=append:/var/log/snh48/snh48.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable snh48
systemctl start snh48

# 常用管理命令
systemctl status snh48              # 查看服务状态
journalctl -u snh48 -f              # 查看实时日志
systemctl restart snh48             # 重启服务
systemctl stop snh48                # 停止服务
```

> **systemd 优势**：自动重启崩溃的服务、开机自启、日志自动轮转不会撑爆磁盘。

**日志管理速查：**

| 启动方式 | 日志位置 | 自动重启 | 开机自启 | 推荐场景 |
|---|---|---|---|---|
| **nohup** (推荐) | `/var/log/snh48/snh48.log` | ❌ | ❌ | 快速启动、临时运行 |
| **screen** | `/var/log/snh48/snh48_screen.log` | ❌ | ❌ | 调试、手动维护 |
| **systemd** | `/var/log/snh48/snh48.log` + `journalctl` | ✅ | ✅ | 生产环境长期运行 |

**日志轮转（可选）：** 如果使用 nohup 或 screen 长期运行，建议配置 logrotate：

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

### 9. 验证

浏览器打开 **http://124.222.72.203:8000**
- 首页：星空背景 + 彩色滚动文字
- `/qa`：AI 问答
- `/api/qa/status`：知识库状态

---

## 二、ICP 备案完成后（配置域名 + HTTPS）

### 1. 配置域名解析

在腾讯云 DNS 解析控制台添加以下 A 记录：

| 记录类型 | 主机记录 | 记录值 | 说明 |
|---------|---------|--------|------|
| A | @ | `124.222.72.203` | 根域名 |
| A | www | `124.222.72.203` | www 子域名 |

**验证：** `dig cjy.plus +short` 应返回 `124.222.72.203`

### 2. 腾讯云安全组放行 80/443 端口

登录腾讯云控制台 → **云服务器 → 安全组** → 添加入站规则：

| 协议端口 | 来源 | 策略 | 说明 |
|---------|------|------|------|
| TCP:80 | `0.0.0.0/0` | 允许 | HTTP |
| TCP:443 | `0.0.0.0/0` | 允许 | HTTPS |

**验证（在本地电脑终端执行）：**
```bash
curl -I https://cjy.plus       # 能通即代表安全组 443 已放行
curl -I http://cjy.plus         # 应返回 301 重定向到 https（代表 80 已放行）
```

### 3. 安装 nginx

```bash
yum install -y nginx
systemctl start nginx
systemctl enable nginx
```

**验证：** `systemctl status nginx` 应显示 `active (running)`

### 4. 配置 Nginx 反向代理

Nginx 配置说明：

| 项目 | 说明 |
|------|------|
| 配置文件 | `deploy/nginx.conf` |
| 部署位置 | `/etc/nginx/conf.d/snh48.conf` |
| server_name | `cjy.plus www.cjy.plus` |
| 重定向 | HTTP (80) → HTTPS (443) 自动重定向 |
| 反向代理 | HTTPS → Python 服务 (127.0.0.1:8000) |

```bash
mkdir -p /etc/nginx/conf.d
cp deploy/nginx.conf /etc/nginx/conf.d/snh48.conf
nginx -t
systemctl reload nginx
```

**调试（如果 nginx 启动失败）：**
```bash
nginx -t                                    # 先检查语法
journalctl -xeu nginx.service -n 30 --no-pager  # 查看详细失败原因
systemctl status nginx.service              # 查看服务状态
```

### 5. 安装腾讯云 SSL 证书

| 项目 | 说明 |
|------|------|
| 证书类型 | 腾讯云包年 SSL 证书 |
| 证书路径 | `/etc/nginx/ssl/cjy.plus/cert.pem` |
| 密钥路径 | `/etc/nginx/ssl/cjy.plus/cert.key` |
| 下载方式 | 腾讯云控制台 → SSL 证书 → 下载 Nginx 版 → SCP 上传到服务器 |

从 [腾讯云 SSL 证书控制台](https://console.cloud.tencent.com/ssl) 下载 Nginx 版证书，然后：

```bash
# 在本地电脑执行
scp /下载路径/cjy.plus_nginx.zip root@124.222.72.203:/home/

# SSH 到服务器执行
mkdir -p /etc/nginx/ssl/cjy.plus
cd /home
unzip cjy.plus_nginx.zip -d /etc/nginx/ssl/cjy.plus/
nginx -t && systemctl reload nginx
```

**验证：**
```bash
ls -l /etc/nginx/ssl/cjy.plus/            # 确认 cert.pem + cert.key 都存在
openssl x509 -in /etc/nginx/ssl/cjy.plus/cert.pem -text -noout | grep "Not Before"
openssl x509 -in /etc/nginx/ssl/cjy.plus/cert.pem -text -noout | grep "Not After"
```

### 6. 添加 ICP 备案号到页面底部

在服务器上的 `.env` 中添加：
```
SITE_ICP=京ICP备2026026973号
```
重启 Python 服务后即可在页面底部看到备案号链接。

**验证：**
```bash
curl -I http://127.0.0.1:8000   # 应返回 HTTP/1.1 405
curl -s http://127.0.0.1:8000 | head -5  # 应包含 <title>心上珍藏集</title>
ps aux | grep "website.main"    # 确认进程存在
```

### 7. 切换访问方式并验证完整链路

浏览器可直接访问 **https://cjy.plus**（原 `http://124.222.72.203:8000` 仍可用作备用）。

```bash
curl -I https://cjy.plus         # 应返回 HTTP/2 405，server: nginx/1.26.3
curl -s https://cjy.plus | head -5  # 应包含 <title>心上珍藏集</title>
```

---

## 三、公安联网备案

### 备案状态

| 项目 | 状态 | 编号 |
|------|------|------|
| ICP 备案（工信部） | ✅ 已通过 | 京ICP备2026026973号 |
| ICP 备案号悬挂 | ✅ 已完成 | `.env` 中配置：`SITE_ICP=京ICP备2026026973号` |
| 安全自评估 | 🚧 材料已准备，待提交平台 | 见 `doc/security/security_assessment_qa.txt` |
| 公安联网备案 | ✅ 已通过 | 京公网安备11010602202601号 |

### 安全评估填报指南

> ⚠️ **本网站因含有 AI 问答功能（生成式人工智能服务），被系统判定具有舆论属性，需要进行安全评估。**

1. 登录 **全国互联网安全管理服务平台**
2. 找到您的网站申请 → 找到"安全评估"入口
3. 选择 **自评估**
4. 逐项填写（参考 `doc/security/security_assessment_qa.txt`）：

| 表单问题 | 答案参考文件 | 对应章节 |
|----------|-------------|---------|
| 开展评估情况 | `doc/security/security_assessment_qa.txt` | 一 |
| 评估方法 | `doc/security/security_assessment_qa.txt` | 二 |
| 安全管理负责人 | `doc/security/security_assessment_qa.txt` | 三（需填写您本人信息） |
| 用户真实身份核验及注册信息留存 | `doc/security/security_assessment_qa.txt` | 四 |
| 日志信息留存措施 | `doc/security/security_assessment_qa.txt` | 五 |
| 违法有害信息防范处置 | `doc/security/security_assessment_qa.txt` | 六 |
| 个人信息保护及技术措施 | `doc/security/security_assessment_qa.txt` | 七 |
| 投诉举报机制 → **选择"是"** | `doc/security/security_assessment_qa.txt` | 八 |
| 为监管部门提供技术协助的机制 | `doc/security/security_assessment_qa.txt` | 九 |

**注意事项：**
- 安全管理负责人的信息请填写您本人的真实信息
- 建议先在文本编辑器中填好后再复制到平台
- 填写完成后先保存草稿，核对无误再提交
- 如有附件上传入口，可上传 `doc/security/security_assessment_report.md` 作为补充材料

### 公安联网备案号悬挂（✅ 已完成）

公安联网备案已审核通过，备案号：**京公网安备11010602202601号**。

已在 `.env` 中配置：
```
SITE_POLICE_ICP=京公网安备11010602202601号
SITE_POLICE_ICP_CODE=11010602202601
```

页面底部已显示公安备案图标 + 备案号，链接到公安部查询网站 `https://beian.mps.gov.cn/`。

---

## 四、后续代码更新

本地修改后 push → SSH 中 git pull + 重启：

```bash
# 本地
cd /mnt/zhitainew/snh48_web && git add . && git commit -m "xxx" && git push
cd /mnt/zhitainew/snh48_web/transcript_analyze && git add . && git commit -m "xxx" && git push
```

然后在 SSH 终端 pull 并重启：

```bash
cd /home/snh48_web && git pull
cd /home/snh48_web/transcript_analyze && git pull

pkill -f "website.main"
cd /home/snh48_web
source venv/bin/activate
nohup python -m website.main > /var/log/snh48/snh48.log 2>&1 &
```

---

## 五、长期维护清单

### 每月
- [ ] 检查服务器安全更新：`sudo apt update && sudo apt upgrade`
- [ ] 检查 nginx 错误日志：`tail -f /var/log/nginx/snh48_error.log`
- [ ] 检查交互日志是否正常记录
- [ ] 检查 AI 问答功能是否正常运行

### 每季度
- [ ] 更新知识库（如有新直播/新内容）
- [ ] 检查投诉举报记录并处理积压
- [ ] 审查服务条款是否需要更新

### 每年
- [ ] 更新 ICP 备案信息（如网站内容、主办方信息有变更）
- [ ] 更新公安联网备案信息
- [ ] 重新审视安全评估报告
- [ ] 检查 SSL 证书是否在有效期内

---

## 六、法律义务提示

根据现行法规，请务必注意：

1. **配合监管义务：** 如收到网信办/公安部门的通知，需在要求时限内配合调查和处置
2. **日志留存义务：** 交互日志至少保留 6 个月（本网站已实现日志轮转备份）
3. **投诉处理义务：** 投诉举报需在 24 小时内受理，7 个工作日内反馈
4. **违法信息处置义务：** 发现违法信息需立即停止传输并报告

---

## 七、免责标识

本网站已在使用 AI 问答功能的页面添加以下标识：

> **AI 问答页面：** "本服务使用生成式人工智能技术，生成内容仅供参考，不代表陈嘉仪本人立场，请理性看待。"
>
> **AI 回答底部：** "以上内容由人工智能（AI）生成，仅供参考，不代表陈嘉仪本人立场。请结合其他信息源自行判断。"

这些标识已内嵌在 `qa.html` 模板和 LLM Prompt 中。

---

## 八、防滥用策略说明

系统内置了**多层级速率限制**来保护服务器算力和 API 费用，所有阈值均可通过 `.env` 配置：

| 层级 | 针对 | 默认值 | 限制类型 |
|---|---|---|---|
| **IP 级频率** | 每个 IP 地址 | 每 60 秒最多 5 次 | 滑动窗口 |
| **用户冷却** | 每个浏览器 | 两次提问至少间隔 30 秒 | 时间戳对比 |
| **日配额** | 每个浏览器 | 每天最多 50 次 | 日历日计数 |
| **并发限制** | 每个浏览器 | 最多同时处理 2 个任务 | 任务注册表 |
| **密码暴力破解** | 每个 IP 地址 | 每 300 秒最多 10 次 | 滑动窗口 |

修改默认值（在 `.env` 中添加）：
```ini
QA_RATE_LIMIT_PER_WINDOW=10          # 每个 IP 每 60 秒最多 10 次
QA_RATE_LIMIT_WINDOW_SECONDS=120     # 时间窗口改为 120 秒
QA_USER_COOLDOWN_SECONDS=15          # 冷却改为 15 秒
QA_DAILY_QUOTA_PER_USER=100          # 每日配额改为 100 次
QA_MAX_CONCURRENT_PER_USER=3         # 并发最多 3 个
PASSWORD_RATE_LIMIT_PER_WINDOW=5     # 密码尝试更严格
PASSWORD_RATE_LIMIT_WINDOW_SECONDS=600 # 时间窗口 10 分钟
```

用户超限时返回 **HTTP 429**，前端显示中文提示。

---

## 九、参考链接

- https://cloud.tencent.com/document/product/243/61412（备案号悬挂要求）
- https://cloud.tencent.com/document/product/243/19616（公安联网备案指南）
- https://beian.miit.gov.cn/（工信部备案查询）
- https://www.beian.gov.cn/（全国互联网安全管理服务平台）
