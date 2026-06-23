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
| 数据生成工程 | `/mnt/zhitainew/snh48/snh48-fan-hub`（本地），`/home/snh48-fan-hub`（服务器） |
| 数据对接文档 | `snh48-fan-hub/schedule_record/网站开发对接说明.md` |
| 安全文档 | `doc/security/security_baseline.md` |
| 部署手册 | `deploy/TODO.md` |

## 环境

| 环境 | 域名 | IP | 服务管理 | Nginx 配置 |
|------|------|----|----------|------------|
| 腾讯云 | `cjy.plus` | `124.222.72.203` | screen 会话 | `/etc/nginx/conf.d/snh48.conf`，来源 `deploy/nginx.conf` |
| 阿里云香港 | `cjy.我爱你` / `cjy.xn--6qq986b3xl` | `8.210.188.184` | `systemd` 服务 `snh48-aliyun` | `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`，来源 `deploy/nginx-aliyun.conf` |

## 数据生成工程依赖

本网站运行时读取 `snh48-fan-hub` 生成的数据。修改 `/timeline`、直播回放、图片代理、`SCHEDULE_CSV_PATH`、`LIVE_PUSH_REPLAY_ROOT` 或相关展示逻辑前，先确认这份数据契约。

| 环境 | `snh48-fan-hub` 角色 | 同步策略 |
|------|----------------------|----------|
| 本地 | 功能验证副本，路径 `/mnt/zhitainew/snh48/snh48-fan-hub` | 与腾讯云全量工程通过 GitHub 同步，主要用于验证脚本和对接逻辑 |
| 腾讯云 | 全量代码和数据生成服务器，路径 `/home/snh48-fan-hub` | 常驻采集、监控、生成网站数据，供内地版暨测试版网站使用 |
| 阿里云香港 | 网站必要数据副本，路径 `/home/snh48-fan-hub` | 从腾讯云直接同步最小数据集，供香港版暨对外公开版网站使用 |

网站必要数据集：

- `schedule_record/schedule.csv`
- `live_push_replays/陈嘉仪_161808449/`
- `room_record/陈嘉仪_161808449/live_covers/`
- `room_record/陈嘉仪_161808449/gift_replies/`
- 图片通过网站 `/image-proxy/` 访问，不把 `schedule_record/images/` 作为阿里云常规同步项。

数据同步脚本：

```bash
python3 deploy/deploy.py sync-data tencent aliyun
bash deploy/sync-to-aliyun.sh
```

`deploy.py sync-data` 是本地推荐入口；`deploy/sync-to-aliyun.sh` 是兼容脚本，应在腾讯云网站工程 `/home/snh48_web` 上执行。两者都是把必要数据从腾讯云同步到阿里云。只改 Codex 文档、网站代码或部署说明时，不需要执行数据同步。

数据同步后如需预热图片代理缓存：

```bash
python3 deploy/deploy.py sync-data tencent aliyun --prewarm
python3 deploy/deploy.py prewarm-image-cache aliyun
```

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

## 功能维护备注

### 时光轴地图打开

入口和文档：

- 页面入口：`/timeline`
- 源文件：`website/static/js/timeline.js`
- 生产产物：`website/static/js-dist/timeline.js`
- 详细行为文档：`doc/timeline_badges.md`、`doc/admin_guide.md`、`doc/ai_agent_instructions.md`

维护边界：

- 地址文本负责展开或隐藏地图选择；点击高德/百度按钮后不要自动隐藏。
- App 调起逻辑已验证可用，不要为了网页兜底问题顺手改动 App scheme。
- 百度 App 和百度网页兜底已验证可用，除非用户明确指出百度回归，否则不要改动。
- 高德桌面网页兜底已验证可用；当前只对手机浏览器网页兜底做终端区分。
- 高德手机网页兜底使用 `https://uri.amap.com/search`，并使用 `src=xinshangzhenzangji`；不要使用工程名、目录名或内部部署名作为公开地图来源参数。
- 高德手机 H5 在香港流量等境外网络下可能受高德侧网络、CDN、定位或地区策略影响，排查时先区分网络问题和代码回归。
- 当前不强制传城市参数；App 搜索城市/排序由地图 App 根据关键词、定位、历史城市和网络环境决定。

## GitHub 同步部署命令

推荐使用多服务器部署工具：

```bash
python3 deploy/deploy.py deploy tencent
python3 deploy/deploy.py deploy aliyun
python3 deploy/deploy.py deploy all
```

仅文档、Codex 规则、部署说明、已构建静态资源等不需要 Python 服务重启的更新：

```bash
python3 deploy/deploy.py deploy tencent --no-restart
python3 deploy/deploy.py deploy aliyun --no-restart
python3 deploy/deploy.py deploy all --no-restart
```

是否重启按本次变更范围判断：

| 变更范围 | 推荐命令 |
|---|---|
| Python 代码、依赖、`.env`、服务入口 | `python3 deploy/deploy.py deploy all` |
| 仅文档、Codex 文件、部署说明 | `python3 deploy/deploy.py deploy all --no-restart` |
| 仅静态 JS/CSS 产物、图片、模板 HTML | `python3 deploy/deploy.py deploy all --no-restart`，并验证目标页面 |
| Nginx 配置、证书、CSP | `python3 deploy/deploy.py deploy all --nginx --no-restart`，只 reload Nginx |

腾讯云：

```bash
python3 deploy/deploy.py deploy tencent
```

腾讯云 Nginx 变更：

```bash
python3 deploy/deploy.py deploy tencent --nginx --no-restart
```

阿里云：

```bash
python3 deploy/deploy.py deploy aliyun
```

阿里云 Nginx 变更：

```bash
python3 deploy/deploy.py deploy aliyun --nginx --no-restart
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

部署前可只检查远端 `.env` 键名，不输出真实值：

```bash
python3 deploy/deploy.py check-env all
python3 deploy/deploy.py deploy all --check-env
```

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

安全、Nginx、环境变量或网络边界相关任务按 `doc/security/security_baseline.md` 选择额外验证命令，例如外网端口、代理健康和安全头：

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
