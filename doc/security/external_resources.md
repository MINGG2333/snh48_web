# 外部资源与出站请求清单

> 更新日期：2026-07-02
>
> 适用范围：网站运行时会让浏览器或服务器访问站外资源的代码路径。`package-lock.json`、GitHub 仓库地址、npm/pip 下载地址等构建或部署供应链不计入网站运行时外链。

## 风险结论

- 纯前端外链、图片、地图和 HLS 资源主要由访问者浏览器请求，通常不会消耗本站服务器出口 IP；但第三方仍可能看到来源域名、请求量和用户网络特征。
- 会使用本站服务器出口或内部代理的风险点更高：DeepSeek API、`/api/timeline/danmu` 的 `danmu_url` 兜底抓取、`/image-proxy/` 图片代理。
- 当前前端 `safeUrl()` 只允许 `http:`、`https:` 和同源相对 URL，能阻断 `javascript:`、`data:`、协议相对 URL 等直接脚本注入，但仍允许任意 HTTPS 域名作为图片、跳转或 HLS 来源。
- 当前 CSP 为兼容外部图片与 HLS 保留了较宽策略：`img-src https:`、`connect-src https:`、`media-src https: blob:`。这属于功能兼容取舍，新增外链时必须同步复核。
- 已核对 `snh48-fan-hub` 的图片对接说明和 `scripts/weibo_img_proxy.py`：代理不是通用 URL 代理，只拼接到 `https://wx1.sinaimg.cn`，并限制 `/orj960/`、`/orj1080/`、`/large/`、`/mw690/`、`/original/` 路径；当前生产安全组口径为只公网开放 `80/443/22`，`8899` 不公网开放，所以“公网直连图片代理端口”不是当前已成立风险；但脚本本身没有限速、共享缓存和并发保护，若未来安全组或防火墙误放行 `8899`，会绕过 Nginx 保护。

## 当前解决状态

> 状态口径：本表区分“代码库已实现”和“线上已生效”。代码库变更只有在服务器 `git pull`、Nginx `nginx -t` 通过并 reload、Python 服务重启后，才算线上生效。

| 风险项 | 当前状态 | 用户体验影响 | 剩余动作 |
|--------|----------|--------------|----------|
| `8899` 公网直连图片代理 | 当前生产安全组口径为只开放 `80/443/22`，`8899` 不公网开放；文档和验证清单已写入该基线 | 无影响 | 持续验证安全组和公网 `8899` 不可达 |
| `/image-proxy/` 经 `443` 被刷流量 | 代码库已加入 Nginx 共享缓存、缓存锁、stale 缓存、后台更新、7 天浏览器缓存、`X-Cache-Status` 和温和 IP 限速；部署工具会准备缓存目录 | 正常用户多图加载保留 `burst=120`，重复访问同图会更快；首次访问新图仍会立即请求上游 | 部署 Nginx 配置并 reload；线上验证 `X-Cache-Status`、多图弹窗和 429 日志 |
| 图片首次加载速度 | 新增 `script/prewarm_image_proxy.py`，可在 `schedule.csv` 同步后预热最新微博图片 | 预热后用户更少遇到第一张慢图；预热只请求有限数量图片，不会批量压用户浏览器 | 在数据同步流程中按量运行预热，例如 `--limit 120 --workers 8` |
| `danmu_url` 服务端兜底抓取 | 代码库已加入本地 URL 缓存、内网/localhost/非 http(s)/非标准端口拦截、响应大小上限和域名白名单灰度模式 | 仍保持本地弹幕优先；远程失败时接口返回可解析 JSON，不阻断视频播放 | 部署 Python 服务；盘点历史 `danmu_url` 后再决定是否强制域名白名单 |
| DeepSeek QA 被刷 | 已有密码、IP/用户限速、日配额、并发限制、余额接口缓存 | 维持现有使用体验 | 按日志观察，暂不加验证码 |
| 阿里云主动拉取腾讯云运行数据 | 已停用腾讯云侧自动推送；自动任务改为阿里云每分钟通过 SSH 检查腾讯云源数据指纹，源数据变化时才从腾讯云拉取 | 运行数据仍可在 1 分钟内同步；无用户可见影响 | 结合腾讯云站内信确认告警目标；不要恢复腾讯云高频主动出站同步 |
| CSV 任意 HTTPS 图片/链接/HLS | 尚未强制白名单；已在文档中要求先告警后拦截 | 暂不影响旧图片、旧链接和旧回放 | 后续先统计历史域名，再按字段逐步启用白名单 |
| CDN/外部脚本与 `hls.js@latest` | 尚未自托管，仍保留宽 CSP 兼容 | 不影响当前页面加载和回放 | 后续固定版本并自托管，再收窄 CSP |

### 缓存行为说明

- 图片代理缓存只针对“同一个 `/image-proxy/...` 路径”。如果网站更新后使用新的微博图片 URL，会生成新的 `/image-proxy/...` 路径，第一次访问会直接请求新资源，不会被旧图片缓存挡住。
- 如果同一个图片 URL 的上游内容被替换，浏览器和 Nginx 可能继续使用旧缓存。微博 CDN 图片通常以图片 ID 表示不可变资源；如果确实要替换内容，建议换成新的图片 URL，而不是复用旧 URL。
- 静态 JS/CSS 已通过 `?v={{ static_version(...) }}` 做版本号。网站发布后文件 mtime 变化，浏览器会请求新的 `/static/...?...` URL；Nginx 的 `immutable` 不会阻止新版本加载。
- `proxy_cache` 是服务器 Nginx 缓存上限，不会占用用户设备；当前腾讯云按资源余量设为 `3GB`，阿里云可用资源更充足，设为 `10GB`。用户浏览器只缓存自己实际访问过的图片、JS、CSS 和字体，由浏览器按自身配额自动清理；不会因为服务器缓存上限变大而显著增加用户本地存储。
- 当前 `/image-proxy/` 的浏览器缓存时间为 7 天。用户只看少量页面时，本地新增缓存通常接近实际下载的图片体积；只有大量浏览历史图片时，浏览器缓存才会相应增长，并且浏览器会在空间紧张时淘汰旧缓存。

## 固定前端资源

| 域名/协议 | 代码位置 | 类型 | 触发方式 | 主要风险 | 当前控制 |
|-----------|----------|------|----------|----------|----------|
| `cdnjs.cloudflare.com` | `website/templates/base.html` | Font Awesome CSS/字体 | 所有使用 `base.html` 的页面加载 | CDN 可用性、第三方样式供应链 | CSP 显式允许；HTTPS |
| `cdnjs.cloudflare.com` | `website/templates/qa.html` | `html2canvas`、`qrcode-generator` JS | 访问 QA 页面 | 第三方脚本供应链；版本虽固定但未自托管/SRI | CSP 显式允许；HTTPS |
| `fonts.googleapis.com` | `website/templates/base.html` | Google Fonts CSS | 所有使用 `base.html` 的页面加载 | 可用性、隐私/跨境访问稳定性 | CSP 显式允许；HTTPS |
| `fonts.gstatic.com` | `website/templates/base.html` | Google Fonts 字体文件 | 字体 CSS 触发 | 可用性、隐私/跨境访问稳定性 | CSP 显式允许；HTTPS |
| `cdn.jsdelivr.net` | `website/templates/replay.html` | `hls.js` JS | 访问回放页 | `@latest` 会随上游变化，供应链风险高于固定版本 | CSP 显式允许；HTTPS |
| `beian.mps.gov.cn` | `website/templates/base.html` | 公安备案链接 | 用户点击页脚备案链接 | 低；仅跳转 | `target="_blank"` + `rel="noopener noreferrer"` |
| `beian.miit.gov.cn` | `website/templates/base.html` | 工信部备案链接 | 用户点击页脚备案链接 | 低；仅跳转 | `target="_blank"` + `rel="noopener noreferrer"` |
| `weibo.com`、`github.com` | `website/templates/about.html` | 致谢/来源链接 | 用户点击关于页链接 | 低；仅跳转 | `target="_blank"` + `rel="noopener noreferrer"` |

## 数据驱动的前端资源

这些 URL 来自 CSV 或后端数据，浏览器会在页面渲染、弹窗打开或用户点击时访问。

| 数据来源 | 字段 | 代码路径 | 可能域名 | 触发方式 | 风险说明 |
|----------|------|----------|----------|----------|----------|
| `website/data/manual_events.csv` | `image`、`images`、`link` | `website/timeline_api/router.py` → `website/static/js/timeline.js` | 当前为 `www.snh48.com` | 时光轴卡片/弹窗加载图片；用户点击链接 | 运行数据，由腾讯云同步到阿里云；若替换为高频外站图片可能被视为盗链 |
| 服务器 `schedule.csv` | `cover_url`、`event_images`、`image_urls` | `read_schedule()` → `timeline.js` | `sinaimg.cn`、`hdslb.com`、其他 HTTPS 图源 | 时光轴卡片/弹窗加载图片 | URL 来自运行时数据；前端允许任意 HTTPS 图片；`.sinaimg.cn` 会被改写到 `/image-proxy/` |
| 服务器 `schedule.csv` | `event_link`、`source_url`、`video_urls`、`snh48_bilibili_urls`、`snh48_weibo_urls`、`chenjiayi_weibo_urls` | `read_schedule()` → `buildSourceLinks()` | 微博、B站、活动页等 | 用户点击弹窗链接 | 能跳转到任意 HTTPS URL；前端会过滤危险协议，但不限制域名 |
| 服务器 `summary.csv` | `live_cover_url` | `read_live_pushes()` | `source3.48.cn` | 直播卡片/弹窗加载封面 | 服务端拼接为 `https://source3.48.cn{path}`，但高流量直连官方图源仍可能触发防盗链/限流 |
| 服务器 `summary.csv` | `play_url` | `/replay/{live_id}` → `hls.js` | HLS/CDN 域名不固定 | 用户打开回放页后浏览器拉取 `.m3u8` 和分片 | CSP 允许任意 HTTPS 连接与媒体；若数据被污染，访问者浏览器会请求非预期 HLS 域名 |

当前前端控制点：

- `timeline.js` 的 `safeUrl()` 拒绝空值、协议相对 URL、非 `http/https` 协议。
- 外链使用 `target="_blank"` 和 `rel="noopener"` 或 `noopener noreferrer`。
- 多数时光轴图片带 `referrerpolicy="no-referrer"`；页面级 `Referrer-Policy` 为 `strict-origin-when-cross-origin`，跨站默认只发送来源域名。

## 地图外链

| 服务 | 代码位置 | 协议/域名 | 触发方式 | 风险说明 |
|------|----------|-----------|----------|----------|
| 高德 App | `website/static/js/timeline.js` | `iosamap://poi`、`androidamap://poi` | 用户点击地点后的“高德地图”按钮 | App scheme 只在用户动作后触发；地点文本来自行程数据 |
| 高德网页 | `website/static/js/timeline.js` | `https://uri.amap.com/search` | App 未打开时自动或手动兜底 | 请求包含地点关键词和 `src`；移动端固定为 `xinshangzhenzangji` |
| 百度 App | `website/static/js/timeline.js` | `baidumap://map/place/search`、`bdapp://map/place/search` | 用户点击地点后的“百度地图”按钮 | App scheme 只在用户动作后触发；地点文本来自行程数据 |
| 百度网页 | `website/static/js/timeline.js` | `https://map.baidu.com/search/` | App 未打开时自动或手动兜底 | 请求包含地点关键词 |

## 服务端出站请求

| 目标 | 代码位置 | 触发入口 | 当前控制 | 风险说明 |
|------|----------|----------|----------|----------|
| `https://api.deepseek.com` 或 `DEEPSEEK_BASE_URL` | `website/config.py`、`transcript_analyze/kb_qa/qa_utils.py` | QA 提问 | `SITE_PASSWORD`、QA 限速、用户冷却、日配额、并发限制 | 消耗 API 额度；被刷可能触发服务商限流或封禁 |
| `https://api.deepseek.com/user/balance` | `website/balance_api/router.py` | `/api/balance` | IP 限速、成功结果缓存 | 公开状态接口会触发服务端请求；当前已有缓存和限速降低压力 |
| `danmu_url` 任意 URL | `website/timeline_api/router.py` 的 `_read_text_url()` | `/api/timeline/danmu?live_id=...`，且本地弹幕文件缺失 | 仅能按 `live_id` 选中 CSV 行，不能由前端直接传 URL；15 秒超时 | 如果 `summary.csv` 被污染，服务器可能请求非预期 URL，存在 SSRF、出口 IP 被限流、访问内网地址等风险 |
| `/image-proxy/` 上游代理 | `deploy/nginx.conf`、`deploy/nginx-aliyun.conf` | 浏览器访问被改写后的新浪图片路径或直接请求 `/image-proxy/...` | 生产入口经 Nginx `/image-proxy/` 反代到本机或内网 `8899`；当前安全组不公网放行 `8899`；代理写死上游为 `wx1.sinaimg.cn`；代码库 Nginx 配置已加入共享缓存、缓存锁、stale 缓存、7 天浏览器缓存、温和 IP 限速和 `X-Cache-Status` | 这是本站服务器/代理出口风险点；即使 `8899` 不公网开放，公网用户仍可经 `443` 请求 `/image-proxy/...`；代码库已通过缓存和温和限速降低刷量影响，线上需部署验证 |
| 阿里云 `ssh/rsync` 到腾讯云 `124.222.72.203:22` | `deploy/sync-from-tencent-if-changed.sh`、`deploy/sync-from-tencent.sh`、阿里云 root crontab | 阿里云主动拉取网站必要运行数据 | 阿里云 cron 每分钟通过 SSH 检查腾讯云源数据指纹；源数据变化时才执行拉取；`sync-from-tencent.sh` 在一次同步内复用同一条 SSH 连接；脚本有 flock 防重入 | 连接由阿里云主动发起，降低腾讯云主动对外 SSH/rsync 被风控误判的概率；腾讯云仍会作为 SSH 服务端发送数据 |

## `snh48-fan-hub` 图片代理核对

参考文件：

- 服务器路径：`/home/snh48-fan-hub/schedule_record/网站开发对接说明.md`
- 本地副本：`/mnt/zhitainew/snh48/snh48-fan-hub/schedule_record/网站开发对接说明.md`
- 代理脚本：`/home/snh48-fan-hub/scripts/weibo_img_proxy.py`
- 本地副本：`/mnt/zhitainew/snh48/snh48-fan-hub/scripts/weibo_img_proxy.py`

已确认事实：

- `schedule.csv` 的 `image_urls`、`cover_url`、`event_images` 存储微博 CDN 原图链接，例如 `https://wx1.sinaimg.cn/original/...`。
- 对接说明推荐网站把 `.sinaimg.cn` 图片改写为同域名 `/image-proxy/...`，由 Nginx 转发到图片代理。
- `weibo_img_proxy.py` 固定上游为 `https://wx1.sinaimg.cn`，并固定 `Referer: https://weibo.com/`，不是“前端传什么 URL 就代理什么”的开放代理。
- 代理只允许 `/orj960/`、`/orj1080/`、`/large/`、`/mw690/`、`/original/` 开头的路径，其他路径返回 404。
- 脚本监听 `0.0.0.0:8899`；当前生产安全组口径为只公网开放 `80/443/22`，所以公网直连 `8899` 当前不成立。这里仍要作为安全基线持续验证，避免后续排障或迁移时误放行。
- 脚本向浏览器返回 `Cache-Control: public, max-age=86400`；代码库中的网站 Nginx 配置已覆盖为 7 天浏览器缓存，并启用 `proxy_cache`、`proxy_cache_lock`、stale 缓存和后台更新。部署生效后，不同用户访问同一图片时，首个请求后会优先命中本站缓存。
- 脚本使用 Python 标准库 `HTTPServer`，默认单进程单线程；大量慢请求或上游 15 秒超时可能阻塞后续请求。
- 脚本没有 IP 限速、路径长度限制、响应大小上限、上游 Content-Type 白名单或访问日志轮转策略。

结论：

- 代理已经规避了最危险的“任意 URL 开放代理/SSRF”形态，因为上游域名被写死为 `wx1.sinaimg.cn`。
- 当前主要风险转为“经 `443` 暴露的 `/image-proxy/` 被当作微博图片中转站刷流量”：消耗本站带宽、占用单线程代理、放大对 `wx1.sinaimg.cn` 的请求量，进而导致代理 IP 被新浪限流或封禁。
- `8899` 直连风险当前被安全组关闭；生产基线应继续保持 `8899` 不公网开放，入口只允许网站 Nginx 的 `/image-proxy/` 反代访问。

## 维护规则

- 新增任何 CDN、外部脚本、外部样式、字体、图片、HLS、地图、API 或代理路径时，必须同步更新本文件。
- 需要修改 CSP 时，同步维护 `deploy/nginx.conf`、`deploy/nginx-aliyun.conf` 和 `deploy/deploy.py` 的 `SECURITY_CSP`。
- 服务端出站请求不得直接接受前端传入的任意 URL；确需动态 URL 时必须做协议、域名、端口、内网地址、响应大小和超时限制。
- 腾讯云到阿里云运行数据同步不得恢复 15 秒常驻循环，也不得把腾讯云主动推送脚本放回生产 cron；新增目录时必须同时更新 `sync-from-tencent-if-changed.sh` 的远端指纹列表和 `sync-from-tencent.sh` 的拉取逻辑。
- 运行时 CSV 中的 URL 字段建议按用途做 allowlist：图片、来源链接、视频/HLS、地图地点分别校验，不要只做“允许任意 HTTPS”。
- 高流量图片尽量使用本地缓存或受控代理；直连官方图片时继续使用 `referrerpolicy="no-referrer"`，并避免预加载大量历史图片。
- 外部脚本优先固定版本并自托管；暂不自托管时至少避免 `@latest`。
- 发现第三方返回大量 `403`、`429`、超时或代理错误时，优先检查 `/image-proxy/` 日志、Nginx access log、回放 HLS 域名和 CSV URL 来源。

## 用户体验约束

安全加固必须以不破坏正常用户体验为前提：

- 图片代理：不能用过低的全局限速牺牲首屏图片加载；优先使用 Nginx 共享缓存、浏览器缓存、`proxy_cache_lock`、后台更新和 stale 缓存，降低重复上游请求。限速只用于异常刷量场景，并保留合理 `burst`，避免用户一次打开弹窗多图时被误伤。
- 图片首图：热门或最新行程图片可在数据同步后预热缓存；不要依赖严格文件后缀白名单，因为微博图片路径可能没有常规扩展名。更稳妥的是限制路径前缀、路径长度、上游响应大小，并校验 `Content-Type` 为图片。
- 弹幕：优先保证已有回放弹幕可用。当前代码已本地文件优先、远程 `danmu_url` 兜底；加白名单前必须先盘点历史 `danmu_url` 域名并补齐本地弹幕缓存，不能直接上线会让旧弹幕失败的拦截规则。
- 弹幕降级：远程弹幕源超时、被拦截或为空时，视频播放不能失败；接口应保持返回可解析 JSON，并优先返回本地文件或历史缓存。安全拦截应记录日志，页面侧只表现为暂无弹幕或继续使用已缓存弹幕。
- 灰度原则：URL 白名单、CSP 收窄和限速阈值先用日志观察真实域名、请求频率和命中率，再逐步执行；每一步都要验证图片首次加载、弹窗多图、回放视频和弹幕加载。

代码库已落地的体验优先措施：

- Nginx `/image-proxy/` 已在代码库配置共享缓存、缓存锁、stale 缓存、后台更新和 7 天浏览器缓存；腾讯云配置为 `3GB`，阿里云配置为 `10GB`。响应返回 `X-Cache-Status`，便于部署后验证 `MISS`/`HIT`。
- Nginx `/image-proxy/` 已在代码库配置按 IP 的温和限速：`10r/s`，`burst=120 nodelay`。正常浏览器并发加载多图应不受影响，异常刷量会被削峰。
- 新增 `script/prewarm_image_proxy.py`，可在同步 `schedule.csv` 后按日期倒序预热最新微博图片缓存。示例：

```bash
python3 script/prewarm_image_proxy.py --base-url https://cjy.plus --limit 120 --workers 8
python3 script/prewarm_image_proxy.py --base-url https://cjy.xn--6qq986b3xl --limit 120 --workers 8
```

- 远程弹幕读取已在代码库增加本地 URL 缓存、响应大小上限、危险地址拦截和可灰度的域名白名单。默认不强制域名白名单，避免历史弹幕误伤。

## 风险等级与解决方案

### 高风险

| 风险项 | 可能后果 | 解决方案 | 坏处/兼容性风险 | 建议 |
|--------|----------|----------|----------------|------|
| `/image-proxy/` 被刷流量 | 公网用户可经 `443` 访问 `/image-proxy/...`，打满本站带宽和代理进程；大量请求转发到 `wx1.sinaimg.cn`，导致代理服务器出口 IP 被上游限流或封禁 | 代码库已实现：1. 保持云安全组不公网放行 `8899`；2. Nginx `proxy_cache`、`proxy_cache_lock`、stale 缓存、后台更新和按环境配置的缓存容量，腾讯云 `3GB`、阿里云 `10GB`；3. 7 天浏览器缓存；4. 预热脚本；5. 温和 `limit_req`。后续：代理只监听 `127.0.0.1` 或内网 IP；代理脚本补路径长度、响应大小和上游 `Content-Type` 校验 | 缓存会增加磁盘占用；预热会产生少量主动请求；温和限速对正常多图加载影响低，但仍需线上观察 429 | 第一批代码已实现；部署后验证 `X-Cache-Status` 和正常多图加载 |
| `danmu_url` 服务端兜底抓取 | 如果 `summary.csv` 被污染，服务器可能请求内网或非预期外站；可被用于 SSRF、出口 IP 滥用或大响应拖垮进程 | 代码库已实现：1. 本地 `danmu_local_path` 优先；2. 远程抓取成功后落本地 URL 缓存；3. 硬拦截内网、localhost、链路本地地址、非 `http/https` 和非标准端口；4. 限制响应大小；5. 支持域名白名单灰度告警，默认不强制；6. 失败时接口仍返回可解析 JSON，不阻断视频播放 | 缓存会占用磁盘；默认不强制白名单意味着需要后续盘点后再收紧外站域名 | 第一批代码已实现；下一步盘点历史 `danmu_url` 域名后再开启强制白名单 |
| DeepSeek QA 被刷 | API 额度消耗、服务商限流、QA 不可用 | 维持 `SITE_PASSWORD`；继续使用 IP/用户/日配额/并发限制；对异常 IP 加封禁或验证码；后台监控失败率和额度 | 验证码会降低使用便利性；封禁策略可能误伤共享网络 | 已有基础防护，按日志观察后加固 |

### 中风险

| 风险项 | 可能后果 | 解决方案 | 坏处/兼容性风险 | 建议 |
|--------|----------|----------|----------------|------|
| 运行时 CSV 允许任意 HTTPS 图片/链接/HLS | 数据污染后，访问者浏览器会访问非预期域名；可能引入钓鱼跳转、隐私暴露或浏览器侧请求放大 | 按字段做 allowlist，但先统计现有数据并输出告警；图片允许 `sinaimg.cn`、`hdslb.com`、`snh48.com`、同源代理和已确认历史图源；链接允许微博/B站/官方活动页及确认来源；HLS 允许已确认 CDN 域名 | 新活动来源需要维护白名单；如果未先盘点历史数据，可能导致旧图片、链接或回放不可用 | 建议实施，先告警后拦截 |
| CSP 过宽：`img-src https:`、`connect-src https:`、`media-src https:` | CSP 无法限制被污染数据访问任意 HTTPS 图源/HLS/API | 先统计真实线上外部域名，再逐步收窄 CSP；HLS 先按回放 CDN 域名试点；每次收窄都用浏览器验证回放、弹幕接口、图片弹窗和地图跳转 | 域名摸排不完整会导致图片、弹幕请求或回放无法加载 | 谨慎实施，放在 URL 白名单和历史数据盘点之后 |
| 外部脚本依赖 CDN，且 `hls.js@latest` | 上游 CDN 不可用、版本变化或供应链污染会影响页面 | 固定 `hls.js` 版本；下载并自托管 `hls.js`、`html2canvas`、`qrcode-generator`、Font Awesome；更新 CSP 到 `'self'` | 需要维护静态资源更新；自托管后资源体积进入仓库 | 建议实施 |
| 新浪图片无共享缓存 | 多用户访问同一图仍会重复打到上游，增加被限流概率；首个用户之后的加载速度也无法改善 | 代码库已通过 Nginx `proxy_cache`、缓存锁、stale 缓存、后台更新和预热脚本处理；缓存 key 按 URI | 磁盘占用增加，需要清理策略；预热频率过高会增加上游请求 | 代码已实现，部署后观察缓存命中率 |

### 低风险

| 风险项 | 可能后果 | 解决方案 | 坏处/兼容性风险 | 建议 |
|--------|----------|----------|----------------|------|
| 备案、关于页、微博/GitHub 外链 | 用户点击跳出本站；第三方知道来源 | 保持 `rel="noopener noreferrer"`；必要时加跳转提示 | 加提示会降低跳转效率 | 保持现状 |
| 地图 App/网页兜底 | 地图服务收到地点关键词和来源参数；境外网络下可能不稳定 | 保持用户点击触发；不要自动批量打开；保留当前移动端 `src=xinshangzhenzangji` | 无明显坏处 | 保持现状 |
| Google Fonts 跨境可用性 | 字体加载慢或失败 | 自托管字体或使用系统字体 fallback | 字体文件进入仓库；视觉略有变化 | 有空再做 |

### 推荐实施顺序

1. 把 `8899` 不公网开放写入生产验收并定期验证；当前安全组口径为只开放 `80/443/22`，已满足该基线。
2. 部署 Nginx 图片代理缓存、温和限速和预热脚本，并验证图片首次加载、多图弹窗和缓存命中。
3. 部署弹幕远程兜底安全边界和本地 URL 缓存，并验证本地弹幕、远程兜底弹幕和远程失败降级。
4. 盘点历史 `danmu_url` 域名和本地弹幕覆盖率，确认后再开启 `DANMU_REMOTE_ENFORCE_HOST_ALLOWLIST=true`。
5. 给时光轴 CSV 的 URL 字段增加按用途白名单，先告警后拦截，避免误伤旧数据。
6. 固定并自托管外部脚本/CDN 资源。
7. 在确认真实外部域名后，逐步收窄 CSP。
