# 网站安全基线

> 更新日期：2026-08-25
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
| FastAPI 运行隔离 | 腾讯云 `snh48-web.service` 和阿里云 `snh48-aliyun.service` 都使用专用不可登录 `snh48-web` 账号、systemd 沙箱和 `UMask=0077`；腾讯云敏感账号操作由两个独立 root 服务通过 UID 校验的 Unix Socket 接收固定命令，网页进程无 sudo、fan-hub 写权限和额外 capability；阿里云跨云密钥只能调用固定 shared-state peer 命令 | 降低网站被攻破后读取/修改整台服务器和运行数据的影响面 | 修改服务运行目录或桥接命令时必须同步 unit、权限脚本和远端 `authorized_keys` 强制命令 |
| SSH 强认证 | 腾讯云和阿里云均使用 `AuthenticationMethods publickey`；root 只允许公钥，密码、keyboard-interactive、GSSAPI 和 X11 转发关闭 | 阻断公网密码爆破直接变成账号入侵 | 先分别验证笔记本、台式机和自动化密钥；保留云控制台终端作为带外恢复入口 |
| 公开投诉验证码 | 投诉页使用服务端保存、10 分钟过期、一次性消费的验证码挑战；答案不写入 HTML/JS | 降低公开投诉接口被脚本批量提交的风险 | 当前挑战状态是单进程内存；扩展多 worker 前需迁移到共享存储 |
| 可信 Host 与 API 文档 | `TrustedHostMiddleware` 限制域名；OpenAPI/Swagger 默认关闭，需显式 `ENABLE_API_DOCS=true` 开启 | 减少 Host 头滥用和接口结构暴露 | 新域名必须加入 `TRUSTED_HOSTS`，调试完成后恢复关闭文档 |
| 依赖与外部脚本固定 | FastAPI/Starlette/Jinja2/python-multipart/OpenAI 版本已锁定兼容范围；回放使用 `hls.js@1.7.1` + SRI | 降低供应链漂移和 CDN 被替换的风险 | 定期升级时必须重新跑回归测试并更新 SRI |
| 运行时文件权限 | 网站可写数据、投诉和交互日志由 `snh48-web` 管理，目录 `0700`、文件 `0600`；阿里云只读 fan-hub 副本由 root 同步为 `root:snh48-web`、目录 `0750`、文件 `0640`；`.env` 和主机运维日志保持 root `0600` | 降低同机普通账号读取投诉、会话、管理数据或运维细节的风险，同时允许非 root 网站进程只读派生数据 | 腾讯云使用 `deploy/harden_runtime_permissions.sh`，阿里云使用 `deploy/harden_aliyun_runtime_permissions.sh`；拉取和手动推送脚本必须保留 `--chown=root:snh48-web --chmod=D750,F640`，不要手工放宽到全局可读 |
| 图片代理端口收敛 | 生产安全组不公网放行 `8899`，公网只经 HTTPS `/image-proxy/` 到 Nginx；阿里云代理还以 systemd `DynamicUser` 只监听 `127.0.0.1:8899` | 防止外部绕过 Nginx 安全头、限速和缓存策略直接刷图片代理 | `/image-proxy/` 仍是公网入口，需要继续保留限速和共享缓存 |
| 图片代理缓存与温和限速 | `/image-proxy/` 使用 Nginx `proxy_cache`、缓存锁、stale 缓存、7 天浏览器缓存、`X-Cache-Status` 和温和 IP 限速 | 降低重复打新浪上游的概率，改善重复访问速度，并削弱刷量影响 | 缓存目录占用磁盘；部署时需确保 `/var/cache/nginx/snh48_image_proxy` 可写 |
| 图片缓存预热 | `script/prewarm_image_proxy.py` 可按 `schedule.csv` 日期倒序预热最新微博图片 | 优先让最新行程图片进入 Nginx 缓存，减少用户首次遇到慢图的概率 | 预热会主动消耗少量带宽，应在数据同步后限量运行 |
| 弹幕远程兜底保护 | `danmu_local_path` 优先；远程 `danmu_url` 成功后写本地 URL 缓存；硬拦截内网/localhost/非 http(s)/非标准端口，并限制响应大小 | 降低 SSRF 和大响应拖垮风险，同时保留历史弹幕可用性 | 域名白名单默认只告警不强制，需盘点历史源后再收紧 |
| 可信代理 IP | 后端只在请求来源命中 `TRUSTED_PROXY_PEERS` 时采信 `X-Real-IP` / `X-Forwarded-For`，默认仅信任本机 | 降低客户端或同内网机器伪造 IP 绕过限速的风险 | Nginx 统一设置 `X-Forwarded-For $remote_addr`；多层反代需显式配置真实代理 IP |
| QA 访问控制 | 只有 `QA_ENABLED=true` 的节点注册 QA API；提问、异步提问、异步结果轮询均要求 `SITE_PASSWORD`，轮询还绑定 `X-Client-Id` 和一次性 `poll_token` | 腾讯云可彻底停止 QA 加载；启用节点可防止知道 task_id 的人直接读取异步结果 | 腾讯云关闭 QA 后 `/qa` 本机返回 503、API 返回 404，不跨站跳转；阿里云继续执行原有密码和轮询保护 |
| 记忆页访问控制 | `/api/memories/*` 普通访问/提交要求 `MEMORIES_VIEW_PASSWORD`；应援会模式和本人模式使用独立密码；普通数据接口不返回平台 ID | 降低小房间、半私密互动和后台身份标识误公开风险 | 真实密码只放服务器 `.env`；两端提交都由腾讯云权威节点串行提交版本 |
| 可写运行状态防覆盖 | 首页背景词、房间忽略、计分业务核实和记忆页只向腾讯云提交操作；使用 `flock`、原子替换、幂等 operation ID、revision、不可变 gzip 快照和持久 outbox | 防止两个节点互相覆盖整份 JSON、网络超时后重复执行或旧 outbox 回滚新版本 | 当前状态、历史和 outbox 都不进 Git；恢复只能在腾讯云执行；巡检见 `doc/shared_runtime_state.md` |
| 可靠待处理箱与客服聊天来源审计 | 投诉、QA 邮箱请求、客服聊天消息和处理状态采用一事件一文件，权限 `0600`；每条事件记录腾讯云/阿里云来源，客服识别码计算 SHA-256 内部会话编号，并在受保护事件中保存用户自定义识别码；`/ob` 需密码后展示和回复 | 避免并发 JSONL 同步丢请求，同时让管理员区分请求入口并支持双向客服消息 | 事件含邮箱、投诉、聊天正文和用户自定义识别码，不得进 Git、静态目录、公开日志或诊断输出；公开客服接口按 IP 限速，识别码是访问凭据，用户需自行保管 |
| 观察页访客估算最小化 | tracker 保留 QA 的 `sessionStorage` 会话 ID，但不再自行生成 `visitor_id`；服务器仅在 `page_view` 时签发带 HMAC 校验的 `HttpOnly` 第一方 `ob_device_profile` Cookie，并把页面、请求 IP 和粗粒度设备标签写入本机 `interaction_logs/session_*/visitor_page_views.jsonl`；`/ob` 密码验证后才返回逐次 IP；API 返回只用于展示整理的 `association_groups` 和 `ip_network_graph`，后者按 IP 节点共同档案/旧会话的集合交集生成边权；经鉴权读取 OB 数据时可用本机 DB-IP Lite MMDB 临时生成 IP 的粗略国家、省级地区或城市标签 | 同一浏览器跨标签页和 IP 变化仍归为一个估算访客；IP 关联组和 3D 图可减少管理页首层条目并帮助查看共用网络环境的档案，但不改变访客/会话估计，不把共享 IP 解释为同一自然人；地区标签可用于筛选网络出口的大致区域 | Cookie 只是浏览器档案，不等于实名自然人、物理设备或硬件指纹；共享 IP 关联可能包含多个自然人，组内必须保留成员和连接 IP；地区库必须本地读取，不得逐 IP 调用外部查询服务，不得把地区、经纬度写入逐次访问日志或生成地区时间线；不得加入完整 User-Agent、Canvas、字体、GPU、音频等主动指纹；地区只代表网络出口且可能不准确；该日志保持节点本地，不进入 Git 或双服务器业务状态复制；旧记录无法可靠倒推逐次设备/IP，历史关联不得伪造成逐次访问 |
| 成员房间上麦回放访问控制 | `/api/room-voice-replays/*` 要求独立密码或复用房间消息密码；成功后使用 `HttpOnly`、`SameSite=Strict`、API 路径限定 Cookie；跨云检查另用独立只读 Token；元数据、同期消息、兼容版及原始音质版音频都鉴权，M4A 只通过固定文件名和 HTTP Range API 提供 | 避免公开房间/小房间音频与同期消息被公共静态目录或搜索引擎直接获取，同时避免两台服务器复用用户密码 | Token 只允许 GET 和 Range，不能调用 `/login` 或签发 Cookie；页面仍设置 `noindex,nofollow`，不得把 `ROOM_VOICE_REPLAYS_DIR` 挂到 `/static`；真实密码和 Token 只放 root `0600` 配置 |
| 翻牌记录与账号管理访问控制 | `/api/flip-cards/*` 要求 `FLIP_CARDS_PASSWORD` 和路径限定的 `HttpOnly`、`SameSite=Strict` Cookie；账号管理 POST 还校验同源，仅腾讯云权威节点启用。手机号和验证码经本机 Socket 请求体交给独立受限服务，手机号只写腾讯云本机短期 `0600` 会话，验证码不落盘，Token 只写私有账号库；短信有冷却/小时限额，验证码最多尝试 5 次 | 避免个人翻牌、媒体和口袋48登录凭据被公开、跨站触发或同步到阿里云 | 两端页面和代码一致；阿里云同一弹窗只返回当前节点不开放操作且无跳转。网页进程无 sudo 和 fan-hub 写权限；翻牌桥的系统 `/tmp` 保持只读，只将短信限速、翻牌更新、转录串行化和账号清单提交四个预创建锁文件以 `root:root 0600` 放行，PyTorch 临时文件仅写 `notifications/flip_web_admin/tmp` 私有目录，部署脚本不得改为放行整个 `/tmp`；本地 Whisper 以 Hugging Face 离线模式运行，不向外部上传音频或下载模型；媒体按清单允许的账号 ID、固定文件名和 Range API 提供；不得把 `flip_data/` 挂到 `/static` |
| 社交 Cookie 隐藏管理 | `/api/social-credentials/*` 要求独立密码或迁移期复用 `OB_PASSWORD`，使用 30 分钟、路径限定的 `HttpOnly`、`SameSite=Strict` Cookie；更新 POST 校验同源并受 `SHARED_STATE_IS_PRIMARY` 硬门禁；固定命令由独立受限服务执行 | 避免微博/抖音/B站 Cookie 被公开、跨站替换或进入阿里云，同时避免网页进程直接获得 root 或凭据目录写权限 | Cookie 只经 HTTPS、Unix Socket 请求体和 stdin-only 短进程传递；响应、状态、命令行和日志不得回显；严格桥先验证再原子保存，失败保留旧配置；页面不进导航并设置 `noindex,nofollow` |
| 防滥用限速 | QA、密码尝试、scroller 登录、邮箱提交、追踪事件、投诉、记忆提交、余额查询、OB/礼物回复页/房间消息页/上麦回放页/翻牌页/记忆页模式登录尝试均有限速 | 控制 API 成本和暴力尝试 | 默认阈值在 `website/config.py`，可由 `.env` 覆盖 |
| 余额接口缓存 | `/api/balance` 对成功结果短期缓存 | 减少公开接口对第三方 API 的压力 | 只缓存成功状态，不缓存缺少 API key 等配置错误 |
| 外部资源清单 | `doc/security/external_resources.md` 记录 CDN、地图、图片、HLS、第三方 API、图片代理和服务端出站请求 | 降低新增外链、代理或第三方调用时漏评估 CSP/封禁/SSRF 风险 | 新增或删除外部资源时必须同步更新 |
| 阿里云主动拉取腾讯云运行数据 | 自动任务在阿里云每分钟按 `core` / `dynamic` 分组检查腾讯云源数据指纹；源数据变化时才拉取。上麦回放以 manifest 原子提交；翻牌多账号先同步脱敏账号 JSON 和媒体，再原子提交 `web/accounts.json`；所有接收文件强制为网站组只读 | 保留只读派生数据约 1 分钟同步延迟，同时避免读到半个发布包或因原子替换丢失网站读取权限 | 不要恢复腾讯云侧常驻推送；翻牌同步只允许 `web/`、`audio/`、`video/`，不得加入 `metadata/`、`transcripts/`、手机号、Token、登录会话或任务日志；不得移除同步脚本的接收端属组和权限参数；其他既有排除规则不变 |
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
| P2 | CDN/外部脚本供应链 | 回放已固定 `hls.js@1.7.1` 并启用 SRI；其他历史 CDN 仍按外部资源清单维护 | 后续可继续自托管并收窄 CSP |
| P1 | 网站进程以 root 运行 | 两个生产节点均已切换为专用 `snh48-web` 非 root 账号和 systemd 沙箱；阿里云跨云密钥另有强制命令 | 线上已生效；维护 ACL、unit 和专用 SSH key，改运行方式时重做文档影响检查 |
| P1 | SSH 公网密码登录 | 腾讯云和阿里云均已改为仅公钥认证；笔记本、台式机和必要自动化链路先验证 | 密码专用回归均被拒绝；云控制台终端作为恢复入口 |
| P1 | 投诉接口可被脚本批量写入 | 已增加服务端一次性验证码挑战，仍保留 IP 限速 | 线上已生效；多 worker 部署时需共享挑战存储，继续观察 400/429 比例 |

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
ROOM_VOICE_REPLAYS_MONITOR_TOKEN=仅被检查目标设置的高熵只读监控 Token
FLIP_CARDS_PASSWORD=独立翻牌页密码或留空复用 OB_PASSWORD
FLIP_CARDS_DATASET_PATH=/home/snh48-fan-hub/flip_data/web/flip_cards.json
FLIP_CARDS_ACCOUNTS_PATH=/home/snh48-fan-hub/flip_data/web/accounts.json
FLIP_CARDS_DATA_DIR=/home/snh48-fan-hub/flip_data
FLIP_CARDS_ACCOUNT_ADMIN_ENABLED=腾讯云 true；阿里云 false
SOCIAL_CREDENTIALS_ADMIN_PASSWORD=独立社交凭据管理密码
SOCIAL_CREDENTIALS_ADMIN_ENABLED=腾讯云 true；阿里云 false
SOCIAL_CREDENTIALS_ADMIN_PYTHON=/home/snh48-fan-hub/venv/bin/python3
SOCIAL_CREDENTIALS_ADMIN_SCRIPT=/home/snh48-fan-hub/scripts/web/social_credentials_admin.py
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
test "$(curl -sS -o /dev/null -w '%{http_code}' https://cjy.plus/api/qa/status)" = 404
curl -sS -D - -o /dev/null https://cjy.plus/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.plus/api/room-voice-replays/sessions
curl -sS -D - -o /dev/null https://cjy.plus/flip-cards
curl -sS -D - -o /dev/null https://cjy.plus/api/flip-cards/status
curl -sS -D - -o /dev/null https://cjy.plus/social-credentials-admin
curl -sS -D - -o /dev/null https://cjy.plus/api/social-credentials/status
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
- `/flip-cards` 页面返回 200；未登录访问 `/api/flip-cards/status` 返回 401；使用真实密码后应用 JSON、MP3/MP4 Range 请求正常，响应不暴露服务器文件路径或口袋48 Token。
- `/social-credentials-admin` 页面返回 200 且带 `X-Robots-Tag: noindex, nofollow`；腾讯云未登录访问 status 返回 401，登录后只返回各槽位是否配置和最近验证时间，不含 Cookie。阿里云 API 返回 403，即使误设 enable 也不能写入。
- 腾讯云和阿里云云安全组均已删除公网 `TCP:8000` 和 `TCP:8899` 入站规则；公网只保留 `80/443` 和必要 SSH `22`；这是云控制台操作，不能只靠代码库变更完成。

涉及图片代理、URL 白名单、CSP 或弹幕抓取的安全加固时，还必须做用户体验验收：

- 图片：验证时光轴首屏封面、弹窗多图和至少一个新的 `/image-proxy/` 图片首次加载正常；如果启用缓存，应同时验证第二次访问命中缓存后更快或至少不变慢。
- 限速：`/image-proxy/` 限速不得使用过低全局阈值；应按 IP 设置合理 `burst`，并用正常用户一次打开多个图片的场景验证不被误伤。
- 弹幕：验证至少一个只有本地 `danmu_local_path` 的回放、一个需要远程 `danmu_url` 兜底的历史回放；远程失败时视频播放不能失败，接口应返回可解析 JSON。
- 白名单和 CSP：先用日志或报告模式盘点真实域名，再强制拦截；强制前必须确认历史图片、回放 HLS 和弹幕源不会被误伤。

## 2026-08-24 修复记录

- 腾讯云网站已从 root `screen` 进程切换为 `snh48-web.service`：专用不可登录账号、systemd 沙箱、受限写目录和 `UMask=0077` 均已生效；服务监听 `127.0.0.1:8000`，公网流量只经 Nginx。
- 网站到阿里云的共享状态连接改用 `snh48-web` 专用 ED25519 密钥；root 侧只允许社交凭据状态/更新和翻牌账号固定子命令，未把网站 `.env`、Cookie、Token 或私钥写入 Git。
- 投诉页已改为服务端一次性验证码挑战；挑战 token 只在短期内存中保存，提交后立即消费，页面不再包含答案。
- 腾讯云 Nginx 已升级到 `1.29.8-1.oc9.ap.2`，默认未知 Host 拒绝，关闭版本号，限制请求体大小；FastAPI API 文档默认返回 404，Trusted Host 校验已启用。
- 回放页固定 `hls.js@1.7.1` 并使用 SRI；微博图片代理增加并发、响应大小和图片 MIME 限制，避免被当作无界中转站。
- 已执行 `deploy/harden_runtime_permissions.sh`，网站数据、投诉和交互日志目录收紧为服务账号可读写；今后权限变更必须重复执行该脚本并核对 ACL。
- 阿里云已使用 `deploy/harden_aliyun_runtime_permissions.sh` 切换到 `snh48-web`、systemd 沙箱和私密运行数据权限；图片代理改为 `DynamicUser` 并只监听回环地址。
- 阿里云 Nginx 1.18 使用兼容的默认 443 虚拟主机返回 444，已隐藏版本、限制请求体并验证裸域名与 `www`；Python 依赖已对齐仓库锁定版本并通过 `pip check`。
- 两台主机 SSH 均已关闭密码、keyboard-interactive 和 GSSAPI，root 只允许公钥；阿里云网站专用密钥在腾讯云只能执行共享状态协议子命令。
- 跨云上麦回放完整性检查使用独立只读 Token，不再要求腾讯云和阿里云复用页面密码；迁移实施顺序、回滚和自动验收见 `doc/security/server_hardening_migration_runbook.md` 与 `deploy/verify_server_security_baseline.sh`。

本批线上验收：`/`、`/complaint` 返回 200；`/openapi.json` 返回 404；未带投诉验证码返回 422、无效挑战返回 400；未知 HTTP Host 被 Nginx 拒绝；后端 8000 只监听本机。SSH 已在笔记本、台式机和阿里云自动同步密钥分别验证后切换为仅公钥认证；密码、keyboard-interactive 和 GSSAPI 认证均关闭，腾讯云控制台终端保留为带外恢复入口。

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
- 网站进程不再复用 root 身份运行：跨云共享状态使用 `snh48-web` 专用密钥，root 侧只保留两个 forced-style 白名单桥接脚本；腾讯云 SSH 公网入口已关闭密码等非公钥认证，root 只允许公钥登录。
- 状态历史使用完整 gzip 快照而不是增量 diff，恢复更直接但会持续占用磁盘；日常检查需要观察目录大小，归档或保留策略必须先确认不能破坏当前 revision 和审计需求。
- 前端混淆不是访问控制，真正的保护仍依赖后端鉴权、限速和不泄露敏感数据。
- 本文件不能证明线上已部署，线上状态必须按验证清单复核。
