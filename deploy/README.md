# SNH48 演艺信息站 - 部署指南

## 📦 项目结构

```
snh48_web/
├── website/                    # FastAPI 网站应用
│   ├── main.py                 # 主入口
│   ├── config.py               # 配置
│   ├── requirements.txt        # Python 依赖
│   ├── templates/              # Jinja2 网页模板
│   │   ├── base.html
│   │   ├── index.html          # 首页（全屏背景 + 滚动文本）
│   │   ├── about.html          # 关于页面
│   │   └── qa.html             # AI 问答页面
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/main.js, scroller.js, qa.js
│   └── qa_api/                 # 问答 API
│       └── router.py
├── transcript_analyze/         # 已有的问答引擎
│   ├── run_kb_qa.py
│   ├── kb_qa/
│   ├── requirements_kb_qa.txt
│   ├── download_records.json   # 视频下载记录（需要您自己准备）
│   ├── firered_output_batch/   # 字幕文件目录
│   └── video_knowledge_db/     # 知识库持久化目录
├── deploy/
│   ├── deploy.sh               # 一键部署脚本
│   ├── nginx.conf              # Nginx 配置
│   ├── supervisord.conf        # 进程守护配置
│   └── docker-compose.yml      # Docker 部署（可选）
```

## 🚀 部署步骤

### 第一步：在腾讯云服务器上准备环境

```bash
# 1. SSH 登录到服务器
ssh root@124.222.72.203

# 2. 安装必要的系统依赖
yum install -y python3 python3-pip git nginx supervisor
# 如果是 Debian/Ubuntu: apt install -y python3 python3-pip git nginx supervisor

# 3. 安装 Python 虚拟环境
pip3 install virtualenv
```

### 第二步：上传代码到服务器

```bash
# 在您的本地电脑上
cd /mnt/zhitainew/snh48_web

# 将整个项目上传到服务器（在本地执行）
scp -r ./* root@124.222.72.203:/home/snh48_web/
# 或者使用 rsync（推荐）
rsync -avz --exclude 'deploy' ./ root@124.222.72.203:/home/snh48_web/
```

### 第三步：在服务器上运行部署脚本

```bash
# 在服务器上执行
cd /home/snh48_web/deploy
bash deploy.sh
```

### 第四步：配置 API Key

```bash
# 编辑 /etc/environment 或 /home/snh48_web/.env
echo 'DEEPSEEK_API_KEY=your_api_key_here' >> /home/snh48_web/.env
echo 'DEEPSEEK_BASE_URL=https://api.deepseek.com' >> /home/snh48_web/.env

# 重启服务
supervisorctl restart snh48
```

### 第五步：构建知识库

```bash
cd /home/snh48_web
# 确保 download_records.json 和字幕文件已经上传
# 运行知识库构建
python transcript_analyze/run_kb_qa.py build
```

### 第六步：访问网站

- **备案完成前**：访问 `http://124.222.72.203:8000`（使用非标准端口）
- **备案完成后**：配置域名和 SSL（见下文）

## 🌐 域名与 SSL 配置（域名：cjy.plus）

### 1. 修改 Nginx 配置

`deploy/nginx.conf` 已配置好域名 `cjy.plus`。在服务器上执行：

```bash
# 将 nginx 配置复制到 nginx 目录
sudo cp deploy/nginx.conf /etc/nginx/conf.d/snh48.conf

# 测试配置
sudo nginx -t

# 重载 nginx
sudo systemctl reload nginx
```

### 2. 配置腾讯云 SSL 证书

> ⚠️ 你购买的是腾讯云包年 SSL 证书，需手动下载上传。

**2.1 下载证书**
1. 登录 [腾讯云 SSL 证书控制台](https://console.cloud.tencent.com/ssl)
2. 找到你的 `cjy.plus` 证书 → 点击**下载**
3. 选择 **Nginx** 版 → 保存到本地

**2.2 上传到服务器（在本地电脑执行）**
```bash
scp /本地路径/cjy.plus_nginx.zip root@124.222.72.203:/home/
```

**2.3 在服务器上解压并安装（在 SSH 终端执行）**
```bash
# 创建证书目录
mkdir -p /etc/nginx/ssl/cjy.plus

# 解压证书
cd /home
unzip cjy.plus_nginx.zip -d /etc/nginx/ssl/cjy.plus/
# 或者手动上传 cert.pem 和 cert.key 到 /etc/nginx/ssl/cjy.plus/

# 确认文件存在
ls -l /etc/nginx/ssl/cjy.plus/

# 重启 nginx
sudo nginx -t
sudo systemctl reload nginx
```

### 3. 验证

浏览器访问 https://cjy.plus 查看是否显示绿色小锁 🔒

## 🔧 开发环境本地运行

```bash
cd /mnt/zhitainew/snh48_web

# 安装依赖
pip install -r website/requirements.txt
pip install -r transcript_analyze/requirements_kb_qa.txt

# 启动开发服务器
python -m website.main

# 访问 http://localhost:8000
```

## 📝 关于腾讯云安全组

需要登录腾讯云控制台，在安全组中添加规则：
- **目的**：允许测试访问
- **来源**：0.0.0.0/0（或您的 IP）
- **协议端口**：TCP:8000
- **策略**：允许

## ⚠️ 注意事项

1. **云服务器安全组**：在腾讯云控制台 → 实例 → 安全组，添加入站规则允许 8000 端口
2. **域名解析**：备案完成后，添加 A 记录指向 `124.222.72.203`
3. **API Key**：确保设置 `DEEPSEEK_API_KEY` 环境变量
4. **存储空间**：向量数据库约需要数百 MB ~ 数 GB 空间
5. **内存**：建议服务器至少有 2GB 可用内存

## ❓ 常见问题

**Q: 备案完成前可以测试网站吗？**
A: 可以！使用非标准端口 8000，访问 `http://124.222.72.203:8000`。

**Q: 如何检查服务是否在运行？**
A: `supervisorctl status snh48` 或 `curl http://localhost:8000/`

**Q: 如何查看日志？**
A: `tail -f /var/log/snh48/error.log`
