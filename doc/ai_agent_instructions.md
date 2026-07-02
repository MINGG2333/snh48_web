# 🤖 AI Agent 网站管理指令手册

> 本文档为 AI Agent 自动化管理网站提供指引，将操作分为两类：
> - **🟢 可直接执行** — 得到你的想法后即可直接运行，无需额外确认
> - **🟡 必须经过同意** — 必须先向你说明方案并获得确认才能执行

---

## 🟢 可直接执行（安全只读操作，无需再次确认）

以下操作为**只读或安全增量下载**，不会修改任何文件，可直接执行。

### 1. 从服务器安全下载数据

| 操作 | 安全命令 | 安全保证 |
|------|---------|---------|
| **下载阿里云通知数据到本地** | `rsync -avz root@8.210.188.184:/home/snh48_web/website/data/interaction_logs/ website/data/interaction_logs/` | 增量更新，只新增远程新文件，不会删除/覆盖/改动已有本地文件 |
| **下载腾讯云通知数据到本地** | 同上，改 IP 为 124.222.72.203 | 同上 |

### 2. 查看服务器状态（只读）

| 操作 | 命令 |
|------|------|
| **查看阿里云服务状态** | `systemctl status snh48-aliyun`（远程执行） |
| **检查进程是否运行** | `ps aux \| grep 'python -m website.main'` |
| **检查 Nginx 配置语法** | `nginx -t`（远程执行） |
| **查看磁盘空间** | `df -h`（远程执行） |
| **查看服务运行时间** | 阿里云：`systemctl status snh48-aliyun`；腾讯云：`ps -eo pid,lstart,cmd \| grep website.main` |

### 3. 查看日志与通知（只读）

| 操作 | 说明 |
|------|------|
| **查看通知中心** | 读取本地的 `_all_notifications.md` 或各 session 下的 `notification_center.md` |
| **查看用户事件记录** | 读取 `user_{client_id}_events.md` |
| **查看阿里云服务器日志** | `journalctl -u snh48-aliyun --no-pager -n 50`（远程执行） |
| **查看腾讯云服务器日志** | `tail -50 /var/log/snh48/snh48_screen.log`（远程执行） |

---

## 🟡 必须经过同意才能执行

**所有涉及直接编辑文件的操作**必须先向你说明方案并获得确认。包括但不限于：

### 安全修复协作约定

当一次推进多项安全修复或防滥用策略时，必须先列出每一项的：
- 预期效果
- 可能坏处或兼容性代价
- 是否建议实施

默认等待你逐项确认后再实施。只有当你明确表示“一次确认全部实施”或“按推荐全部推进”时，才可以在一次确认后批量执行。

### 1. 代码修改（任何文件）

| 操作 | 说明 |
|------|------|
| **修改前端样式/布局** | CSS、JS、HTML 模板等所有前端文件 |
| **修改后端逻辑** | 任何 `.py` 文件 |
| **添加新页面路由** | 在 `main.py` 中添加路由 + 创建模板 |
| **添加新 API 路由** | 创建或修改 router 文件 |
| **修改时光轴页面** | `timeline.js`、`timeline.html`、`timeline_api/router.py` |
| **修改回放页面** | `replay.html`（弹幕、全屏、控制条等） |
| **修改观察页** | `ob.html`、`ob_api/router.py` |
| **修改礼物回复页** | `gift_replies.html`、`gift_replies_api.py` |
| **修改房间消息页** | `room_messages.html`、`room_messages_api.py` |
| **修改首页飘动文字** | `scroller_api/router.py`、`scroller_admin.html` |
| **修改 QA 页面** | `qa.html`、`qa.js`、`qa_api/router.py` |
| **添加 CSS 样式** | `static/css/` 或模板中的 `<style>` |

### 2. Git 操作与部署

| 操作 | 说明 |
|------|------|
| **Git 提交与推送** | `git add -A && git commit -m "..." && git push` |
| **同步代码到阿里云** | 推荐 `python3 deploy/deploy.py deploy aliyun` |
| **同步代码到腾讯云** | 推荐 `python3 deploy/deploy.py deploy tencent` |
| **多服务器发布顺序** | 网站页面、API、运行行为或用户可见功能默认先部署腾讯云并让用户手动验证；用户明确确认后才部署阿里云，不要默认 `deploy all` |
| **同步但不重启** | 文档、Codex 规则、部署说明、静态资源或模板更新可用 `--no-restart`；用户可见更新仍按腾讯云先验、阿里云后同步 |
| **同步 Nginx 配置** | 使用 `--nginx --no-restart`，会先运行远端 `nginx -t`；用户可见更新仍按腾讯云先验、阿里云后同步 |
| **检查远端 .env 键** | `python3 deploy/deploy.py check-env all`，只输出键名不输出真实值 |
| **查看运行数据同步状态** | 只读检查：在阿里云查看 `crontab -l`、`tail -n 80 /var/log/snh48/sync-from-tencent.log`；在腾讯云确认旧 `sync-to-aliyun*` cron/进程未恢复。每分钟 `source changed groups=dynamic, pulling...` 可能是动态小数据持续更新，不要直接当作异常 |
| **同步网站必要数据** | 自动同步：阿里云 cron 每分钟运行 `deploy/sync-from-tencent-if-changed.sh`，分组检查腾讯云源数据指纹，有变化才从腾讯云拉取对应分组；手动兜底优先在阿里云运行 `bash deploy/sync-from-tencent.sh`，也可只传 `core` 或 `dynamic`。腾讯云 `sync-to-aliyun*` 只可作为临时兜底，不得恢复为生产 cron 或 15 秒常驻循环 |
| **重启服务** | Python 代码、依赖、`.env` 或服务入口变更才需要；普通 `deploy` 会自动处理 |

### 3. 配置修改（.env 文件）

| 操作 | 影响 |
|------|------|
| **修改网站密码** | 影响用户访问 QA 功能 |
| **修改观察页密码** | 影响管理员访问 |
| **修改礼物回复页密码** | 影响管理员访问 |
| **修改背景词管理密码** | 影响管理员访问 |
| **调整限流配额** | 影响 API 成本和用户体验 |
| **修改网站标题/域名** | 影响页面显示 |
| **修改 DeepSeek API Key** | 导致 QA 功能不可用直到确认 |

### 4. Nginx 与服务器配置

| 操作 | 风险 |
|------|------|
| **修改 Nginx 配置** | 可能影响网站可用性 |
| **重载 Nginx** | 配置错误会导致服务中断 |
| **修改防火墙/安全组规则** | 安全风险 |
| **更换 SSL 证书** | 影响 HTTPS 访问 |
| **修改系统配置** | 影响稳定性 |
| **安装新软件** | 可能引入兼容性问题 |

### 5. 数据管理

| 操作 | 风险 |
|------|------|
| **删除/清理交互日志** | 数据不可恢复 |
| **删除/修改用户事件记录** | 审计需要 |
| **重建知识库** | 耗时较长（小时级），影响 QA |
| **修改知识库配置** | 影响 AI 回答质量 |
| **删除或移动服务器文件** | 可能导致服务异常 |

### 6. 安全与第三方集成

| 操作 | 风险 |
|------|------|
| **添加密码保护页面** | 需要设计密码策略 |
| **修改防滥用策略** | 影响用户体验 |
| **添加验证码/人机验证** | 影响用户体验 |
| **修改 IP 封禁策略** | 可能误伤正常用户 |
| **更换 LLM 模型** | 影响 QA 质量和费用 |
| **接入新 API 服务** | 需要配置和费用评估 |

---

## 🏗 项目架构速查

### 服务器信息

| 服务器 | IP | 域名 | 部署方式 | 服务管理 |
|--------|-----|------|---------|---------|
| 腾讯云 | 124.222.72.203 | cjy.plus | screen 会话 | `screen -S snh48 -X quit` / 重启 |
| 阿里云 | 8.210.188.184 | cjy.我爱你 | systemd 服务 | `systemctl restart snh48-aliyun` |

### .env 配置项

```ini
# 必须
SITE_PASSWORD=xxx              # AI 问答密码
DEEPSEEK_API_KEY=xxx           # DeepSeek API Key
OB_PASSWORD=xxx                # 观察页密码（可选）
GIFT_REPLIES_PASSWORD=xxx      # 礼物回复页密码（可选，独立于观察页）

# 可选
SCROLLER_PASSWORD=xxx          # 背景词管理密码
GIFT_REPLIES_DIR=/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies
ROOM_MESSAGES_PASSWORD=xxx     # 房间消息页密码（可选，默认复用礼物回复页密码）
ROOM_MESSAGES_CSV_PATH=/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages.csv
ROOM_MESSAGES_IGNORE_PATH=/home/snh48_web/website/data/room_messages_ignored_batches.json
ROOM_MESSAGES_IGNORE_DIRECT_SYNC=true
ROOM_MESSAGES_IGNORE_DIRECT_PEER=root@另一台服务器IP
ROOM_MESSAGES_IGNORE_DIRECT_PATH=/home/snh48_web/website/data/room_messages_ignored_batches.json
ROOM_MESSAGES_IGNORE_GIT_SYNC=false
SCORE_GIFTS_PASSWORD=xxx       # 计分礼物页密码（可选，默认复用礼物回复页密码）
SCORE_GIFTS_DATA_PATH=/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/score_gifts.json
SITE_TITLE=心上珍藏集           # 网站标题
SITE_DOMAIN=cjy.plus           # 网站域名
QA_DAILY_QUOTA_PER_USER=20     # 用户日配额
QA_DAILY_IP_QUOTA=20           # IP 日配额
USE_OBFUSCATED_JS=true         # 生产环境使用 js-dist/css-dist
HOST=127.0.0.1                 # 生产环境仅监听本机，由 Nginx 反代
SECURE_COOKIES=true            # HTTPS 生产环境启用安全 Cookie
BALANCE_CACHE_SECONDS=300      # 余额成功结果缓存
BALANCE_MAX_PER_WINDOW=10      # 余额查询 IP 限速
BALANCE_WINDOW_SECONDS=60
OB_LOGIN_MAX_PER_WINDOW=10     # 观察页密码失败尝试限速
OB_LOGIN_WINDOW_SECONDS=300
TRUSTED_PROXY_PEERS=127.0.0.1,::1 # 默认仅信任本机 Nginx 的代理头
```

### Git 工作流

```
本地开发 → git commit → git push
  → 需要重启: 先 python3 deploy/deploy.py deploy tencent；用户确认腾讯云通过后，再 python3 deploy/deploy.py deploy aliyun
  → 不需要重启: 先 python3 deploy/deploy.py deploy tencent --no-restart；用户确认腾讯云通过后，再 python3 deploy/deploy.py deploy aliyun --no-restart
  → Python 代码、依赖、.env、服务入口需要重启
  → 文档、Codex 规则、部署说明、静态资源、模板 HTML 通常不需要重启
  → deploy all 只在用户明确要求一次性同步，或本次确认没有用户可见影响时使用
  → 修改源 .js/.css 文件必须先运行 node script/obfuscate_js.cjs，并提交 js-dist/css-dist
```

### API 端点汇总

| 路径 | 功能 | 需要密码 |
|------|------|---------|
| `/api/qa/ask` | AI 问答 | `SITE_PASSWORD` |
| `/api/qa/ask-async` | 异步问答 | `SITE_PASSWORD` |
| `/api/qa/ask-async/{task_id}` | 异步结果轮询 | `SITE_PASSWORD` + 匹配的 `X-Client-Id` + `X-Poll-Token` |
| `/api/qa/verify-password` | 验证密码 | 无（IP 限速） |
| `/api/qa/status` | QA 状态 | 无 |
| `/api/qa/build` | 重建知识库 | `SITE_PASSWORD` |
| `/api/track/event` | 用户行为追踪 | 无（IP 限速） |
| `/api/scroller/texts` | 背景词管理 | `SCROLLER_PASSWORD` |
| `/api/complaint/submit` | 投诉提交 | 无（验证码 + IP 限速） |
| `/api/timeline/live-pushes` | 时间轴直播数据 | 无 |
| `/api/timeline/schedule` | 时间轴行程数据 | 无 |
| `/api/timeline/danmu` | 弹幕数据 | 无 |
| `/api/balance` | 余额查询 | 无（IP 限速 + 成功结果缓存） |
| `/api/ob/data` | 观察页数据 | `OB_PASSWORD`（失败尝试 IP 限速） |
| `/api/ob/mark-read` | 标记已读 | `OB_PASSWORD`（失败尝试 IP 限速） |
| `/api/gift-replies/data` | 礼物回复分页列表 | `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |
| `/api/gift-replies/summary` | 礼物回复统计和礼物种类 | `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |
| `/api/room-messages/data` | 房间消息聊天式加载 | `ROOM_MESSAGES_PASSWORD` 或 `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |
| `/api/room-messages/summary` | 房间消息统计和类型列表 | `ROOM_MESSAGES_PASSWORD` 或 `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |
| `/api/score-gifts/data` | 计分礼物统计和明细 | `SCORE_GIFTS_PASSWORD` 或 `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |
| `/api/score-gifts/summary` | 计分礼物汇总 | `SCORE_GIFTS_PASSWORD` 或 `GIFT_REPLIES_PASSWORD`（失败尝试 IP 限速） |

### 安全维护规则

| 场景 | 必须检查 |
|------|----------|
| **新增 API** | 是否需要密码/Cookie/`X-Client-Id`，公开可写或产生费用的端点是否有限速 |
| **读取客户端 IP** | 必须使用 `website.rate_limiter.get_client_ip()`，不要直接信任客户端传入的 `X-Forwarded-For`；多层反代只把实际代理 IP 加到 `TRUSTED_PROXY_PEERS` |
| **新增动态 HTML** | 优先使用 DOM API；如使用 `innerHTML`，所有后端/CSV/第三方/用户数据必须先转义 |
| **新增外部资源** | 同步更新 `deploy/nginx.conf` 和 `deploy/nginx-aliyun.conf` 的 CSP，并运行 `nginx -t` |
| **修改 Nginx** | 说明优缺点并确认后执行；先 `deploy tencent --nginx --no-restart` 且 `nginx -t` 通过，用户确认腾讯云后再同步阿里云；部署后检查首页、`/static/`、`/image-proxy/` 是否都有安全头 |
| **生产部署** | `HOST=127.0.0.1`、`SECURE_COOKIES=true`，云安全组不得公网放行 `8000` |

### 前端页面

完整页面登记见 `doc/website_pages.md`；新增、删除、改名页面或新增短入口时必须同步更新。

| 路径 | 说明 | 是否可导航 |
|------|------|-----------|
| `/` | 首页 | ✅ 导航栏 |
| `/about` | 关于 | ✅ 导航栏 |
| `/qa` | AI 问答 | ✅ 导航栏 |
| `/timeline` | 时光轴 | ✅ 导航栏 |
| `/replay/{live_id}` | 直播回放 | ✅ 链接跳转 |
| `/complaint` | 投诉举报 | ✅ 导航栏 |
| `/privacy` | 隐私政策 | ✅ 页脚 |
| `/terms` | 服务条款 | ✅ 页脚 |
| `/scroller-admin` | 背景词管理 | ❌ 仅 URL 访问（需密码） |
| `/ob` | 观察页 | ❌ 仅 URL 访问（需密码） |
| `/gift-replies` / `/gr` | 礼物回复管理页 | ❌ 仅 URL 访问（需密码） |
| `/room-messages` / `/room` | 房间消息管理页 | ❌ 仅 URL 访问（需密码） |
| `/score-gifts` / `/sg` | 计分礼物管理页 | ❌ 仅 URL 访问（需密码） |

### 时光轴地图功能

| 项目 | 当前规则 |
|------|----------|
| 地址入口 | 弹窗中点击 `location` 地址展开/隐藏地图选择 |
| 地图按钮 | 高德/百度按钮点击后保持展开，不自动隐藏 |
| 隐藏规则 | 只通过再次点击地址隐藏；隐藏时移除“没有打开 App？打开网页版地图”提示 |
| 高德 App | `iosamap://poi` / `androidamap://poi`，已验证可打开 App 并搜索 |
| 百度 App | `baidumap://map/place/search` / `bdapp://map/place/search`，已验证可打开 App 并搜索 |
| 高德网页 | `uri.amap.com/search`；手机端 `src=xinshangzhenzangji`，桌面端使用站点域名 |
| 百度网页 | `map.baidu.com/search/` |
| 已知限制 | 高德手机 H5 在香港流量等境外网络下可能不稳定；内地网络通常更稳定 |

维护要求：

- 不要把 App 调起和网页兜底逻辑混在一起改；移动端高德网页不稳定时，先区分是高德 H5 网络/地区问题还是代码回归。
- 不要重新使用工程名作为地图 `src` 或第三方来源参数。
- 修改 `timeline.js` 后必须运行 `node script/obfuscate_js.cjs`，并提交对应 `website/static/js-dist/timeline.js`。
