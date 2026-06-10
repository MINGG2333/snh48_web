# 项目 Profile：SNH48 Web

本文件放本项目特有信息。可复用流程不要直接写死服务器细节，应从这里读取。

## 基本信息

| 项目 | 值 |
|------|----|
| 项目根目录 | `/mnt/zhitainew/snh48_web` |
| 主应用 | FastAPI，入口 `python -m website.main` |
| 前端资源 | `website/static/js/`、`website/static/css/` |
| 生产前端产物 | `website/static/js-dist/`、`website/static/css-dist/` |
| 知识库子项目 | `transcript_analyze/` |
| 安全文档 | `doc/security/security_baseline.md` |
| 部署手册 | `deploy/TODO.md` |

## 环境

| 环境 | 域名 | IP | 服务管理 | Nginx 配置 |
|------|------|----|----------|------------|
| 腾讯云 | `cjy.plus` | `124.222.72.203` | screen 会话 | `/etc/nginx/conf.d/snh48.conf`，来源 `deploy/nginx.conf` |
| 阿里云香港 | `cjy.我爱你` / `cjy.xn--6qq986b3xl` | `8.210.188.184` | `systemd` 服务 `snh48-aliyun` | `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`，来源 `deploy/nginx-aliyun.conf` |

## 本地验证命令

```bash
python3 -m compileall -q website
for f in website/static/js/*.js website/static/js-dist/*.js; do node --check "$f" || exit 1; done
python3 -m py_compile deploy/deploy.py
for f in deploy/deploy.sh deploy/sync-to-aliyun.sh; do bash -n "$f" || exit 1; done
git diff --check
```

修改源 JS/CSS 后还必须运行：

```bash
node script/obfuscate_js.cjs
```

## GitHub 同步部署命令

推荐使用多服务器部署工具：

```bash
python3 deploy/deploy.py deploy tencent
python3 deploy/deploy.py deploy aliyun
python3 deploy/deploy.py deploy all
```

腾讯云：

```bash
python3 deploy/deploy.py deploy tencent
```

腾讯云 Nginx 变更：

```bash
python3 deploy/deploy.py deploy tencent --nginx
```

阿里云：

```bash
python3 deploy/deploy.py deploy aliyun
```

阿里云 Nginx 变更：

```bash
python3 deploy/deploy.py deploy aliyun --nginx
```

## 生产 `.env` 安全基线

真实密码只在服务器 `.env` 中维护，不提交到 Git。

```ini
HOST=127.0.0.1
SECURE_COOKIES=true
USE_OBFUSCATED_JS=true
TRUSTED_PROXY_PEERS=127.0.0.1,::1
```

如需新增或修改 `.env` 项，先更新根目录 `.env.example`，再提醒用户同步服务器真实 `.env`。

## 线上烟测命令

腾讯云：

```bash
curl -sS -D - -o /dev/null https://cjy.plus/
curl -sS -D - -o /dev/null https://cjy.plus/timeline
curl -sS -D - -o /dev/null https://cjy.plus/api/qa/status
curl -sS -D - -o /dev/null https://cjy.plus/api/timeline/schedule
curl -sS -D - -o /dev/null https://cjy.plus/static/js/main.js
curl -sS -D - -o /dev/null https://cjy.plus/static/js/timeline.js
curl -sS -D - -o /dev/null https://cjy.plus/image-proxy/health
```

阿里云：

```bash
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/timeline
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/api/qa/status
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/api/timeline/schedule
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/static/js/main.js
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/static/js/timeline.js
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/image-proxy/health
```

公网 `8000` 不可访问是本项目当前安全基线之一，但不是所有功能部署的通用完成标准。安全任务、Nginx/env/网络变更或用户要求时再验证：

```bash
curl -I --connect-timeout 5 http://124.222.72.203:8000
curl -I --connect-timeout 5 http://8.210.188.184:8000
```

## 远端运行时文件

这些文件可能出现在服务器 `git status --short` 中，通常是运行期数据，不要作为代码冲突处理：

- `nohup.out`
- `website/data/balance_log.csv`
- `website/data/ip_clients.json`
- `website/data/ip_daily_quota.json`
- `website/data/read_notifications.json`
- `website/static/js/timeline.js.bak`
