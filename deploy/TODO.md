# 🚀 备案完成前部署步骤

## 同步策略

| 内容 | 方式 | 大小 |
|---|---|---|
| 网站代码 `website/` + `deploy/` | GitHub（`git clone snh48_web`） | ~200KB |
| 问答系统 `transcript_analyze/` | GitHub（`git clone transcript_analyze`） | ~300KB |
| 源数据 `download_records.json` | SCP 上传 | 114KB |
| 字幕文件 `firered_output_batch/` | SCP 上传 | 124MB |
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
scp /tmp/snh48_data.tar.gz root@124.222.72.203:/home/snh48_web/
rm /tmp/snh48_data.tar.gz

# 上传 huggingface 模型缓存
cd /home/mingg/.cache/huggingface
tar czf /tmp/hf_model.tar.gz hub/models--shibing624--text2vec-base-chinese
scp /tmp/hf_model.tar.gz root@124.222.72.203:/home/
rm /tmp/hf_model.tar.gz
```

**然后在 SSH 终端：**

```bash
# 解压源数据（已在 /home/snh48_web 目录下）
cd /home/snh48_web
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
cd /home/snh48_web
source venv/bin/activate
python transcript_analyze/run_kb_qa.py build
```

---

## 第7步：设置 API Key 并启动

```bash
cd /home/snh48_web
source venv/bin/activate

# 前台测试
export DEEPSEEK_API_KEY="你的真实Key"
python -m website.main
```

看到 `Uvicorn running on http://0.0.0.0:8000` 说明成功。`Ctrl+C` 停止后，后台运行：

### 方式 A：使用 screen（推荐，简单）
```bash
# 安装 screen
yum install -y screen

# 创建新会话
screen -S snh48

# 在 screen 中启动
cd /home/snh48_web
source venv/bin/activate
export DEEPSEEK_API_KEY="your_real_api_key_here"
python -m website.main
```

按 `Ctrl+A` 然后按 `D` 断开（服务后台继续运行）
重新连接：`screen -r snh48`

### 方式 B：使用 nohup（最简单）
```bash
cd /home/snh48_web
source venv/bin/activate
# 设置 API Key 并启动
export DEEPSEEK_API_KEY="你的真实Key"
nohup python -m website.main > /var/log/snh48.log 2>&1 &
echo "服务已启动，PID: $!"

# 查看日志
tail -f /var/log/snh48.log
```

---

## 第8步：验证

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
cd /home/snh48_web && git pull                    # 更新 website/ + deploy/
cd /home/snh48_web/transcript_analyze && git pull  # 更新问答系统

# 重启服务
pkill -f "website.main"
cd /home/snh48_web
source venv/bin/activate
export DEEPSEEK_API_KEY="你的Key"
nohup python -m website.main > /var/log/snh48.log 2>&1 &
```

---

## 备案完成后

1. 腾讯云 DNS 解析添加 A 记录：`www.xxx.com` → `124.222.72.203`
2. 用 `deploy/deploy.sh` 配置 Nginx + SSL（详见 `deploy/README.md`）
3. 添加备案号到页面底部

---

## ⚠️ 注意事项
- **安全组**必须放行 TCP:8000 才能从浏览器访问
- **API Key** 每次 SSH 断开后需要重新设置（或在 `.bashrc` 中永久保存）
- 建议服务器至少有 **2GB 内存**
