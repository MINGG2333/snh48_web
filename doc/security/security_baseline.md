# 网站安全基线

> 更新日期：2026-07-20
>
> 适用范围：代码库中的 `deploy/nginx.conf`、`deploy/nginx-aliyun.conf`、FastAPI 后端、静态前端资源和部署维护流程。
>
> 重要说明：本文件记录的是当前代码库目标安全状态。线上是否已经生效，必须以服务器实际配置、Nginx reload 状态和 `curl` 验证结果为准。

## 已实施措施

| 类别 | 措施 | 主要效果 | 维护注意 |
|------|------|----------|----------|
| Nginx 安全头 | HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy | 降低点击劫持、MIME 嗅探、明文降级、外部脚本注入风险 | 腾讯云和阿里云两份 Nginx 配置必须同步维护 |
| 阿里云 HTTPS 证书续期提醒 | Let's Encrypt / Certbot 自动续期；月度 cron 运行 `script/check_https_certificate.py` 并写入 `/var/log/snh48/https-cert-reminder.log` | 降低证书过期未发现导致 HTTPS 不可用的风险 | 证书仍有效且 `certbot.timer` 存在时不要手动替换；机制细节见 `doc/ops/https_certificate_reminder.md` |
| CSP HLS 兼容 | `connect-src 'self' https:`、`media-src 'self' https: blob:`、`worker-src 'self' blob:` | 保持外部 `.m3u8` 回放和 hls.js worker 可用 | 新增 CDN、外部图片、外部 API 时必须更新 CSP |
| 后端端口收敛 | 生产环境 `HOST=127.0.0.1`，云安全组关闭公网 `8000` | 防止用户绕过 Nginx 安全头和 HTTPS | 临时调试后必须恢复本机监听并关闭安全组 |
| 图片代理端口收敛 | 生产安全组不公网放行 `8899`，公网只经 HTTPS `/image-proxy/` 到 Nginx | 防止外部绕过 Nginx 安全头、限速和缓存策略直接刷图片代理 | `/image-proxy/` 仍是公网入口，需要继续加限速和共享缓存 |
| 图片代理缓存与温和限速 | `/image-proxy/` 使用 Nginx `proxy_cache`、缓存锁、stale 缓存、7 天浏览器缓存、`X-Cache-Status` 和温和 IP 限速 | 降低重复打新浪上游的概率，改善重复访问速度，并削弱刷量影响 | 缓存目录占用磁盘；部署时需确保 `/var/cache/nginx/snh48_image_proxy` 可写 |
| 图片缓存预热 | `script/prewarm_image_proxy.py` 可按 `schedule.csv` 日期倒序预热最新微博图片 | 优先让最新行程图片进入 Nginx 缓存，减少用户首次遇到慢图的概率 | 预热会主动消耗少量带宽，应在数据同步后限量运行 |
| 弹幕远程兜底保护 | `danmu_local_path` 优先；远程 `danmu_url` 成功后写本地 URL 缓存；硬拦截内网/localhost/非 http(s)/非标准端口，并限制响应大小 | 降低 SSRF 和大响应拖垮风险，同时保留历史弹幕可用性 | 域名白名单默认只告警不强制，需盘点历史源后再收紧 |
| 可信代理 IP | 后端只在请求来源命中 `TRUSTED_PROXY_PEERS` 时采信 `X-Real-IP` / `X-Forwarded-For`，默认仅信任本机 | 降低客户端或同内网机器伪造 IP 绕过限速的风险 | Nginx 统一设置 `X-Forwarded-For $remote_addr`；多层反代需显式配置真实代理 IP |
| QA 访问控制 | 提问、异步提问、异步结果轮询均要求 `SITE_PASSWORD`；轮询还绑定 `X-Client-Id` 和一次性 `poll_token` | 防止知道 task_id 的人直接读取异步结果 | 前端自动保存并发送 `poll_token`，用户不需要记忆 |
| 记忆页访问控制 | `/api/memories/*` 普通访问/提交要求 `MEMORIES_VIEW_PASSWORD`；应援会模式和本人模式使用独立密码；普通数据接口不返回平台 ID | 降低小房间、半私密互动和后台身份标识误公开风险 | 真实密码只放服务器 `.env`；两端提交都由腾讯云权威节点串行提交版本 |
| 可写运行状态防覆盖 | 首页背景词、房间忽略、计分业务核实和记忆页只向腾讯云提交操作；使用 `flock`、原子替换、幂等 operation ID、revision、不可变 gzip 快照和持久 outbox | 防止两个节点互相覆盖整份 JSON、网络超时后重复执行或旧 outbox 回滚新版本 | 当前状态、历史和 outbox 都不进 Git；恢复只能在腾讯云执行；巡检见 `doc/shared_runtime_state.md` |
| 可靠待处理箱与来源审计 | 投诉、QA 邮箱请求和处理状态采用一事件一文件，权限 `0600`；每条请求记录腾讯云/阿里云来源，`/ob` 需密码后展示 | 避免并发 JSONL 同步丢请求，同时让管理员区分请求入口 | 事件含邮箱和投诉正文，不得进 Git、静态目录、公开日志或诊断输出；旧 Markdown/JSONL 仅作兼容视图 |
| 成员房间上麦回放访问控制 | `/api/room-voice-replays/*` 要求独立密码或复用房间消息密码；成功后使用 `HttpOnly`、`SameSite=Strict`、API 路径限定 Cookie；元数据、同期消息、兼容版及原始音质版音频都鉴权，M4A 只通过固定文件名和 HTTP Range API 提供 | 避免公开房间/小房间音频与同期消息被公共静态目录或搜索引擎直接获取 | 页面设置 `noindex,nofollow`，但安全边界仍是服务端鉴权；只接受 `segment_000001.m4a` / `segment_000001_original.m4a` 形式，不得把 `ROOM_VOICE_REPLAYS_DIR` 挂到 `/static`，真实密码只放 `.env` |
| 翻牌记录访问控制 | `/api/flip-cards/*` 要求 `FLIP_CARDS_PASSWORD`，未设置时复用 `OB_PASSWORD`；成功后使用 `HttpOnly`、`SameSite=Strict`、API 路径限定 Cookie；HTML、MP3 和 MP4 都鉴权，媒体只通过固定文件名和 HTTP Range API 提供 | 避免个人翻牌内容和本地音视频被公共静态目录、搜索引擎或直链获取 | 页面设置 `noindex,nofollow`，但安全边界仍是服务端鉴权；不得把 `flip_data/` 挂到 `/static`，真实密码只放 `.env` |
| 防滥用限速 | QA、密码尝试、scroller 登录、邮箱提交、追踪事件、投诉、记忆提交、余额查询、OB/礼物回复页/房间消息页/上麦回放页/翻牌页/记忆页模式登录尝试均有限速 | 控制 API 成本和暴力尝试 | 默认阈值在 `website/config.py`，可由 `.env` 覆盖 |
| 余额接口缓存 | `/api/balance` 对成功结果短期缓存 | 减少公开接口对第三方 API 的压力 | 只缓存成功状态，不缓存缺少 API key 等配置错误 |
| 外部资源清单 | `doc/security/external_resources.md` 记录 CDN、地图、图片、HLS、第三方 API、图片代理和服务端出站请求 | 降低新增外链、代理或第三方调用时漏评估 CSP/封禁/SSRF 风险 | 新增或删除外部资源时必须同步更新 |
| 阿里云主动拉取腾讯云运行数据 | 自动任务在阿里云每分钟按 `core` / `dynamic` 分组检查腾讯云源数据指纹；源数据变化时才从腾讯云拉取对应分组，且一次同步内复用同一条 SSH 连接，SSH 设置非交互、连接超时和 keepalive | 降低腾讯云主动对外 SSH/rsync 行为被云厂商风控误判或放大的风险，同时保留只读派生数据 1 分钟内同步延迟 | 不要恢复腾讯云侧 15 秒常驻同步循环；普通同步必须排除四个可写状态，计分目录明确排除 `live_business_fulfillments.json` 和 `.*.lock`；不得把 history、outbox、action inbox 用 `--delete` 整目录覆盖；其他媒体和敏感范围保持原最小同步边界 |
| 前端 XSS 防护 | QA 答案、引用、时光轴文本、URL、图标类名进行转义或白名单校验 | 降低后端数据或第三方数据污染后的脚本执行风险 | 新增 `innerHTML` 前必须先转义或改用 DOM API |
| 管理 Cookie | scroller 管理 Cookie 支持 `SECURE_COOKIES=true` | HTTPS 生产环境下防止 Cookie 经明文连接发送 | IP/http 临时测试时才允许设为 `false` |
| 前端构建 | 生产通过 `USE_OBFUSCATED_JS=true` 使用 `js-dist` / `css-dist` | 降低静态源码直接暴露程度，并压缩资源 | 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs` 并提交 dist |

## 风险解决状态

> 状态口径：代码库已实现不等于线上已生效。Nginx 相关变更必须部署配置、`nginx -t` 通过并 reload；Python 相关变更必须部署代码并重启服务。

| 优先级 | 风险 | 当前解决情况 | 线上验收 |
|--------|------|--------------|----------|
| P0 | `8899` 公网直连图片代理 | 当前安全组口径只开放 `80/443/22`，`8899` 不公网开放；文档和验证清单已固化 | 公网 `curl http://服务器IP:8899/health` 失败或超时 |
| P0 | `/image-proxy/` 经 `443` 被刷 | 代码库已配置 Nginx 共享缓存、缓存锁、stale 缓存、后台更新、7 天浏览器缓存、温和限速和 `X-Cache-Status`；腾讯云缓存上限 `3GB`，阿里云缓存上限 `10GB`；部署工具会创建缓存目录 | 部署后同一图片二次访问出现 `X-Cache-Status: HIT` 或不再重复打上游；正常多图弹窗无 429 |
| P0 | 图片首次加载慢或上游被限流 | 代码库新增 `script/prewarm_image_proxy.py`，可按 `schedule.csv` 日期倒序预热最新微博图片 | 数据同步后限量预热，确认最新行程图片可正常加载 |
| P0 | `danmu_url` SSRF/大响应 | 代码库已加入危险地址拦截、非标准端口拦截、响应大小上限、本地 URL 缓存和白名单灰度告警；默认不强制域名白名单 | 本地弹幕、远程兜底弹幕都能加载；远程失败时视频播放不失败 |
| P1 | DeepSeek QA 被刷 | 已有密码、限速、日配额、并发限制和余额缓存 | 观察日志和额度消耗；暂不加验证码 |
| P1 | 腾讯云到阿里云运行数据同步产生高频出站特征 | 已停用腾讯云侧自动推送；阿里云 cron 每分钟运行 `sync-from-tencent-if-changed.sh`，只有腾讯云源数据变化时调用 `sync-from-tencent.sh` 主动拉取对应分组 | 腾讯云 `crontab -l` 无未注释的 `sync-to-aliyun*` 自动任务，旧推送日志不持续更新；阿里云 cron 有 `sync-from-tencent-if-changed.sh`；同步日志没有 15 秒连续触发。动态小数据持续更新时，每分钟 `source changed groups=dynamic, pulling...` 可以是正常现象，长期 `groups=core,dynamic` 需要排查 |
| P1 | CSV 任意 HTTPS 图片/链接/HLS | 仍处于兼容模式，暂不强制白名单，避免旧内容失败 | 后续先统计历史域名，再告警，最后按字段拦截 |
| P2 | CDN/外部脚本供应链 | 仍使用 CDN，`hls.js@latest` 尚未固定或自托管 | 后续固定版本并自托管，再收窄 CSP |

## 生产环境必需配置

```ini
USE_OBFUSCATED_JS=true
HOST=127.0.0.1
SECURE_COOKIES=true
TRUSTED_PROXY_PEERS=127.0.0.1,::1
DANMU_REMOTE_TIMEOUT_SECONDS=15
DANMU_REMOTE_MAX_BYTES=20971520
DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST=false
MEMORIES_VIEW_PASSWORD=独立记忆页访问密码
MEMORIES_FANCLUB_PASSWORD=独立应援会模式密码
MEMORIES_IDOL_PASSWORD=独立本人模式密码
SHARED_STATE_SYNC_ENABLED=true
SHARED_STATE_NODE_ID=本机 tencent 或 aliyun
SHARED_STATE_IS_PRIMARY=仅腾讯云 true
SHARED_STATE_PEER=root@另一台服务器IP
ROOM_VOICE_REPLAYS_PASSWORD=独立上麦回放密码或留空复用房间消息密码
FLIP_CARDS_PASSWORD=独立翻牌页密码或留空复用 OB_PASSWORD
FLIP_CARDS_HTML_PATH=/home/snh48-fan-hub/flip_chat.html
FLIP_CARDS_DATA_DIR=/home/snh48-fan-hub/flip_data
```

云安全组只应公网放行 `80/443`，以及必要的 SSH `22` 管理入口；`22` 建议限制来源 IP 或配套强认证。不应公网放行后端 `8000` 或图片代理 `8899`。如果备案前或故障排查需要临时暴露 `8000`/`8899`，完成后必须撤销。

## 上线验证清单

在服务器上：

```bash
nginx -t
curl -I http://127.0.0.1:8000
curl -s http://127.0.0.1:8000 | head -5
```

在本地或任意公网环境：

```bash
curl -sS -D - -o /dev/null https://cjy.plus/
curl -sS -D - -o /dev/null https://cjy.plus/api/qa/status
curl -sS -D - -o /dev/null https://cjy.plus/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.plus/api/room-voice-replays/sessions
curl -sS -D - -o /dev/null https://cjy.plus/flip-cards
curl -sS -D - -o /dev/null https://cjy.plus/api/flip-cards/status
curl -sS -D - -o /dev/null https://cjy.plus/image-proxy/health
curl -sS -D - -o /dev/null https://cjy.plus/static/js/main.js
curl -I --connect-timeout 5 http://124.222.72.203:8000
curl -I --connect-timeout 5 http://124.222.72.203:8899/health
python3 script/prewarm_image_proxy.py --base-url https://cjy.plus --limit 10 --dry-run
```

预期结果：

- HTTPS 响应包含 HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy。
- `http://cjy.plus` 跳转到 HTTPS。
- `/static/` 和 `/image-proxy/` 响应也包含安全头。
- `/image-proxy/` 响应包含 `X-Cache-Status`；同一图片第二次访问应优先看到 `HIT` 或至少不再重复打上游。
- 公网访问 `http://124.222.72.203:8000` 和 `http://124.222.72.203:8899/health` 失败或超时；服务器本机访问 `127.0.0.1:8000` 正常。
- `/replay/{live_id}` 的外部 HLS 回放在 Chrome/Firefox 中可播放。
- `/room-voice-replays` 页面返回 200；未登录访问 `/api/room-voice-replays/sessions` 返回 401；使用真实密码后列表、详情和音频 Range 请求正常，响应不暴露服务器文件路径或流 URL。
- `/flip-cards` 页面返回 200；未登录访问 `/api/flip-cards/status` 返回 401；使用真实密码后 HTML、MP3/MP4 Range 请求正常，响应不暴露服务器文件路径或口袋48 Token。
- 腾讯云和阿里云云安全组均已删除公网 `TCP:8000` 和 `TCP:8899` 入站规则；公网只保留 `80/443` 和必要 SSH `22`；这是云控制台操作，不能只靠代码库变更完成。

涉及图片代理、URL 白名单、CSP 或弹幕抓取的安全加固时，还必须做用户体验验收：

- 图片：验证时光轴首屏封面、弹窗多图和至少一个新的 `/image-proxy/` 图片首次加载正常；如果启用缓存，应同时验证第二次访问命中缓存后更快或至少不变慢。
- 限速：`/image-proxy/` 限速不得使用过低全局阈值；应按 IP 设置合理 `burst`，并用正常用户一次打开多个图片的场景验证不被误伤。
- 弹幕：验证至少一个只有本地 `danmu_local_path` 的回放、一个需要远程 `danmu_url` 兜底的历史回放；远程失败时视频播放不能失败，接口应返回可解析 JSON。
- 白名单和 CSP：先用日志或报告模式盘点真实域名，再强制拦截；强制前必须确认历史图片、回放 HLS 和弹幕源不会被误伤。

## 后续开发规则

新增或修改 API：

- 明确是否需要密码、Cookie、`X-Client-Id` 或验证码。
- 公开可写或会产生费用的端点必须加 IP 限速。
- 获取客户端 IP 必须使用 `website.rate_limiter.get_client_ip()`，不要直接信任客户端传入的 `X-Forwarded-For`。
- 如果引入 Docker、CLB、CDN 或多层 Nginx，必须把实际连接后端的代理 IP/CIDR 配到 `TRUSTED_PROXY_PEERS`，不要宽泛信任整个内网。
- 不在响应中暴露 API key、内部路径、完整异常堆栈或管理密码。

新增或修改前端动态 HTML：

- 优先使用 `textContent`、`setAttribute`、DOM API。
- 必须使用 `innerHTML` 时，所有来自后端、CSV、第三方 API、URL 参数或用户输入的数据都要先转义。
- URL 只允许 `http:`、`https:` 或同源相对路径；拒绝 `javascript:`、`data:`、协议相对 URL。
- 图标类名等 class 片段必须做白名单或格式校验。

新增外部资源：

- 先查阅并更新 `doc/security/external_resources.md`，区分浏览器侧外链和服务端出站请求。
- 同时更新 `deploy/nginx.conf` 和 `deploy/nginx-aliyun.conf`。
- 按资源类型更新 CSP：脚本用 `script-src`，样式用 `style-src`，字体用 `font-src`，图片用 `img-src`，XHR/HLS playlist/segment 用 `connect-src`，媒体播放用 `media-src`。
- 修改后必须运行 `nginx -t`，并在测试环境确认对应页面不被 CSP 阻断。

修改 JS/CSS：

```bash
node script/obfuscate_js.cjs
git add website/static/js-dist/ website/static/css-dist/
```

服务器不要求安装 Node.js；构建产物必须随代码提交。

## 已知取舍

- 当前 CSP 仍保留 `'unsafe-inline'`，用于兼容现有模板内联脚本和样式。长期更严格方案是迁移到 nonce/hash CSP。
- `connect-src https:` 较宽，主要为兼容外部 HLS playlist 和分片。若后续回放来源固定，可收窄为指定 CDN 域名。
- `8899` 当前不公网开放不代表图片代理没有滥用风险；`/image-proxy/` 仍通过 `443` 对公网开放。当前已补 Nginx 共享缓存、缓存锁、stale 缓存、图片预热脚本和温和限速，后续仍需观察缓存命中率和 429。
- `danmu_url` 白名单不能直接一刀切上线；当前默认只对危险地址硬拦截、对域名白名单告警不强制。必须先盘点历史域名并补齐本地或历史缓存，再开启强制白名单。
- HSTS 使用 `includeSubDomains`。如果未来新增子域名，该子域名也必须支持 HTTPS，否则浏览器会拒绝明文访问。
- Nginx 安全头目前在 server 块和多个 location 中重复声明，以规避 `add_header` 继承问题；修改 CSP/安全头时必须同步所有重复位置，长期可改为 Nginx include 片段降低维护风险。
- 如果未来接入 CDN、CLB 或 Docker 反向代理，必须重新确认真实连接后端的代理 IP，并只把这些 IP/CIDR 加到 `TRUSTED_PROXY_PEERS`。
- 多数滑动窗口限速为进程内存状态，服务重启会重置；IP 日配额为持久化 JSON。
- 双服务器复制复用现有 root SSH 信任和 IP 白名单；应用层入口只允许受限的 state/inbox 子命令，但 SSH key 本身仍有较高权限。后续若调整服务器权限，应迁移到专用低权限账号和 forced-command，而不是扩大 root key 分发。
- 状态历史使用完整 gzip 快照而不是增量 diff，恢复更直接但会持续占用磁盘；日常检查需要观察目录大小，归档或保留策略必须先确认不能破坏当前 revision 和审计需求。
- 前端混淆不是访问控制，真正的保护仍依赖后端鉴权、限速和不泄露敏感数据。
- 本文件不能证明线上已部署，线上状态必须按验证清单复核。
