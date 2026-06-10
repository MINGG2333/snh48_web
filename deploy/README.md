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
│   ├── deploy.py               # 多服务器部署工具（推荐入口）
│   ├── DEPLOY_TOOL.md          # 多服务器部署工具说明
│   ├── deploy.sh               # 旧版 CentOS 初始化脚本（非日常部署入口）
│   ├── nginx.conf              # Nginx 配置（域名：cjy.plus）
│   ├── TODO.md                 # **部署步骤清单（请按此操作）**
│   └── docker-compose.yml      # Docker 部署（可选）
```

## 🚀 部署步骤

日常代码部署请使用 **[deploy/deploy.py](DEPLOY_TOOL.md)**：

```bash
python3 deploy/deploy.py deploy tencent
python3 deploy/deploy.py deploy aliyun
python3 deploy/deploy.py deploy all
```

仅更新文档、Codex 规则、部署说明、静态资源或模板时，通常不需要重启 Python 服务：

```bash
python3 deploy/deploy.py deploy all --no-restart
```

完整的首次部署/迁移步骤仍请参照 **[deploy/TODO.md](TODO.md)**，按顺序执行。

主要流程：
1. 云服务器安全组放行 80/443，后端 8000 只监听本机
2. SSH 登录 → 安装基础软件 → 配置 GitHub
3. 拉取代码 → 安装依赖
4. 上传数据文件和模型缓存
5. 创建远端 `.env` 配置文件
6. 配置 systemd/screen、Nginx、SSL
7. 启动服务 → 验证

---

## 🐳 Docker 部署（可选）

如果使用 Docker，参考 `docker-compose.yml` 中的配置。

---

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

---

## 🔒 关于 nginx 配置

`deploy/nginx.conf` 已内置域名 `cjy.plus`，相关配置说明：

| 项目 | 说明 |
|------|------|
| 配置文件 | `deploy/nginx.conf` |
| 部署位置 | `/etc/nginx/conf.d/snh48.conf` |
| 证书来源 | 腾讯云 SSL 证书（Nginx 版） |
| 证书路径 | `/etc/nginx/ssl/cjy.plus/cert.pem` + `cert.key` |

ICP 备案完成后，参照 `TODO.md` 中的"二、ICP 备案完成后"章节完成 nginx 和 SSL 配置。

---

## ℹ️ 其他信息

- **FAQ、注意事项、防滥用配置** → 见 [TODO.md](TODO.md) 末尾章节
- **备案状态、备案号悬挂、安全评估填报、法律义务、长期维护** → 见 [TODO.md](TODO.md) 的"备案状态"及后续章节
- **安全基线、上线验证、后续开发安全规则** → 见 [doc/security/security_baseline.md](../doc/security/security_baseline.md)
