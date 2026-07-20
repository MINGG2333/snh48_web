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
| 页面清单 | `doc/website_pages.md` |
| 安全文档 | `doc/security/security_baseline.md` |
| 部署手册 | `deploy/TODO.md` |

## 环境

| 环境 | 域名 | IP | 服务管理 | Nginx 配置 |
|------|------|----|----------|------------|
| 腾讯云 | `cjy.plus` | `124.222.72.203` | screen 会话 | `/etc/nginx/conf.d/snh48.conf`，来源 `deploy/nginx.conf` |
| 阿里云香港 | `cjy.我爱你` / `cjy.xn--6qq986b3xl` | `8.210.188.184` | `systemd` 服务 `snh48-aliyun` | `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`，来源 `deploy/nginx-aliyun.conf` |

### 阿里云 HTTPS 证书与月度提醒

- 阿里云公开站 HTTPS 使用 Let's Encrypt / Certbot，证书路径为 `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem`，私钥路径为 `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/privkey.pem`。
- Nginx 仓库配置来源为 `deploy/nginx-aliyun.conf`，线上路径为 `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`。
- Certbot 自动续期由阿里云 `certbot.timer` 负责；不要在证书仍有效、自动续期存在时手动替换。
- 月度提醒机制见 `doc/ops/https_certificate_reminder.md`。阿里云 root cron 每月运行 `script/check_https_certificate.py`，日志写入 `/var/log/snh48/https-cert-reminder.log`，最新报告写入 `/home/snh48_web/website/data/ops_reminders/https_certificate.md`。
- 2026-07-05 检查结论：线上 HTTPS 可用，证书到期时间为 `2026-09-02 00:09:46+00:00`，阿里云存在 `certbot.timer`。

### 云安全与登录白名单

- 2026-07-03：因阿里云主动拉取腾讯云运行数据会每分钟从 `8.210.188.184` 登录腾讯云 `124.222.72.203`，用户已在腾讯云主机安全/登录风险白名单中加入阿里云 IP `8.210.188.184`。
- 如果未来停用阿里云 `8.210.188.184`、迁移到新的云服务器，或新增运行数据同步目标，必须提醒用户在腾讯云控制台删除旧白名单 IP 或新增新服务器 IP。
- 不要把白名单当作通用放行策略；它只对应当前阿里云主动拉取腾讯云运行数据的 SSH 登录告警降噪。

## 数据生成工程依赖

本网站运行时读取 `snh48-fan-hub` 生成的数据。修改 `/timeline`、直播回放、图片代理、`EVENTS_CSV_PATH`、`SCHEDULE_CSV_PATH`、`LIVE_PUSH_REPLAY_ROOT` 或相关展示逻辑前，先确认这份数据契约。

| 环境 | `snh48-fan-hub` 角色 | 同步策略 |
|------|----------------------|----------|
| 本地 | 功能验证副本，路径 `/mnt/zhitainew/snh48/snh48-fan-hub` | 与腾讯云全量工程通过 GitHub 同步，主要用于验证脚本和对接逻辑 |
| 腾讯云 | 全量代码和数据生成服务器，路径 `/home/snh48-fan-hub` | 常驻采集、监控、生成网站数据，供内地版暨测试版网站使用 |
| 阿里云香港 | 网站必要数据副本，路径 `/home/snh48-fan-hub`，另含网站仓库内手动事件 CSV | 由阿里云 cron 主动从腾讯云拉取最小数据集，供香港版暨对外公开版网站使用 |

网站必要数据集：

- `schedule_record/chenjiayi_events.csv`（事件/行程主文件，网站优先读取）
- `schedule_record/schedule.csv`（事件/行程兼容副本，旧配置和回退读取）
- `/home/snh48_web/website/data/manual_events.csv`（网站运行数据手动事件 CSV，接口按请求读取；格式示例见 `website/data/manual_events.example.csv`）
- `/home/snh48_web/website/data/scroller_texts.json`（首页背景词非 Git 运行状态）
- `/home/snh48_web/website/data/memories/memories.json`（记忆页运行数据；格式示例见 `website/data/memories/memories.example.json`）
- `live_push_replays/陈嘉仪_161808449/`
- `room_record/陈嘉仪_161808449/live_covers/`
- `room_record/陈嘉仪_161808449/gift_replies/`
- `room_record/陈嘉仪_161808449/messages_shards/`（包含公开房间和小房间消息，按 `room_type` / `room_label` 标识来源）
- `room_record/陈嘉仪_161808449/audio_transcripts/`
- `room_record/陈嘉仪_161808449/room_voice_replays/`（同步默认 AAC-LC 单声道兼容版、源 AAC 原始音质版 M4A、会话元数据和同期消息；不含原始 FLV）
- `room_record/陈嘉仪_161808449/score_gifts/`
- `flip_data/web/flip_cards.json`（密码保护的翻牌记录应用数据，由 fan-hub 脚本生成）
- `flip_chat.html`（下载版翻牌记录 HTML，由 fan-hub 脚本生成）
- `flip_data/audio/`、`flip_data/video/`（仅翻牌页本地播放依赖；不含 `flip_data/metadata/`）
- 图片通过网站 `/image-proxy/` 访问，不把 `schedule_record/images/` 作为阿里云常规同步项。

数据同步脚本：

```bash
python3 deploy/deploy.py sync-data tencent aliyun
bash deploy/sync-from-tencent.sh
bash deploy/sync-from-tencent-if-changed.sh
bash deploy/sync-to-aliyun.sh
bash deploy/sync-to-aliyun-if-changed.sh
```

线上自动同步在阿里云执行：cron 每分钟运行 `deploy/sync-from-tencent-if-changed.sh`，通过 SSH 分组检查腾讯云源数据指纹，只有变化时调用 `deploy/sync-from-tencent.sh` 从腾讯云主动拉取对应分组。`deploy/sync-to-aliyun.sh`、`deploy/sync-to-aliyun-if-changed.sh` 和 `deploy/sync-to-aliyun-loop.sh` 只作为腾讯云临时手动推送兜底，不应放回腾讯云生产 cron 或常驻进程。`deploy.py sync-data` 是本地手动触发入口。`room_voice_replays/` 在三个入口中都采用 payload 先同步、`manifest.json` 临时文件原子改名、旧 payload 最后清理的发布顺序，避免大音频传输期间网站提前看到半个新会话。手动事件 CSV 不由 Git 跟踪，仍按 `core` 单向拉取。四个可写业务状态不进入普通分组同步，也不走 Git；即时一致性由 `doc/shared_runtime_state.md` 的腾讯云权威提交、阿里云操作转发、版本复制和持久 outbox 保证。计分礼物目录的其他只读派生文件继续走 `dynamic`，但所有 rsync 入口都排除可写的 `live_business_fulfillments.json` 和 `.*.lock`。

自动同步运行状态口径：

- 阿里云 cron：`* * * * * bash /home/snh48_web/deploy/sync-from-tencent-if-changed.sh >> /var/log/snh48/sync-from-tencent.log 2>&1`
- 阿里云日志：`/var/log/snh48/sync-from-tencent.log`
- 阿里云状态文件：`/tmp/snh48_sync_from_tencent.state.core`、`/tmp/snh48_sync_from_tencent.state.dynamic`
- 阿里云锁文件：`/tmp/snh48_sync_from_tencent_change.lock`、`/tmp/snh48_sync_from_tencent.lock`
- 腾讯云旧推送日志：`/var/log/snh48/sync-to-aliyun.log`，新方案接管后不应持续更新。

同步分组：`core` 包含事件/行程 CSV、手动事件 CSV、直播回放汇总和直播封面；`dynamic` 包含礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物只读派生文件、`flip_data/web/flip_cards.json`、`flip_chat.html` 和翻牌音视频依赖。手动运行 `bash deploy/sync-from-tencent.sh` 不带参数时仍拉取全部分组，也可以显式传 `core` 或 `dynamic`。

排查时不要把每分钟 `source changed groups=dynamic, pulling...` 直接判定为异常。`gift_replies/`、`messages_shards/`、`audio_transcripts/`、`room_voice_replays/`、`score_gifts/`、`flip_data/web/flip_cards.json`、`flip_chat.html` 和翻牌音视频等派生数据在后台更新时，动态组源数据指纹会变化，阿里云每分钟拉取是预期行为。判断是否异常时，应结合腾讯云最近 mtime、阿里云同步日志和 1 到 2 分钟延迟。如果长期出现 `groups=core,dynamic`，需要确认 `core` 组是否真的持续变化，或检查状态文件是否被清理。

修改同步方向、频率、源路径、目标路径或服务器 IP 时，必须同时更新 `doc/daily_website_check.md`、`doc/running_status.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`；并验证阿里云 cron 已启用、腾讯云旧推送 cron/进程已停用、稳定小文件两端 hash 一致。

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
for f in deploy/deploy.sh deploy/sync-to-aliyun.sh deploy/sync-to-aliyun-if-changed.sh deploy/sync-from-tencent.sh deploy/sync-from-tencent-if-changed.sh; do bash -n "$f" || exit 1; done
git diff --check
```

修改源 JS/CSS 后还必须运行：

```bash
node script/obfuscate_js.cjs
```

## 功能维护备注

### 礼物回复管理页

入口和文档：

- 页面入口：`/gift-replies`，短入口：`/gr`
- API：`/api/gift-replies/data`、`/api/gift-replies/summary`
- 数据源：`GIFT_REPLIES_DIR`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/`
- 鉴权：独立环境变量 `GIFT_REPLIES_PASSWORD`，请求头 `X-Gift-Replies-Password`
- 数据契约：`/home/snh48-fan-hub/doc/gift_reply_data_contract.md`

维护边界：

- 页面不进入公开导航，仅 URL 访问并要求密码。
- 默认每页 `100` 条，页面按数据文件里的 `refresh_interval_seconds` 自动刷新，默认 `30` 秒；运行时可在 fan-hub 的 `config/room_monitor.json` 中热更新。
- 后端只读取 `gifts.csv` 和 `summary.json` 派生小数据，不读取或同步完整 `messages.csv`、语音原文件、图片归档或敏感配置。

### 房间消息管理页

入口和文档：

- 页面入口：`/room-messages`，短入口：`/room`；旧短入口 `/rm` 保留兼容。
- API：`/api/room-messages/data`、`/api/room-messages/summary`、`/api/room-messages/ignore-latest-batch`、`/api/room-messages/undo-ignore`
- 数据源：优先读取 `ROOM_MESSAGES_SHARDS_DIR`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/`；没有分片时回退到 `ROOM_MESSAGES_CSV_PATH`；消息字段中的 `room_type=main/small` 和 `room_label=公开房间/小房间` 用于页面标识公开房间或小房间
- 语音转录参考：`ROOM_AUDIO_TRANSCRIPTS_PATH`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/room_audio_transcripts.jsonl`
- 忽略状态：`ROOM_MESSAGES_IGNORE_PATH`，默认 `/home/snh48_web/website/data/room_messages_ignored_batches.json`
- 鉴权：默认复用 `GIFT_REPLIES_PASSWORD`；如需单独密码可设置 `ROOM_MESSAGES_PASSWORD`；请求头 `X-Room-Messages-Password`

维护边界：

- 页面不进入公开导航，仅 URL 访问并要求密码。
- 交互是聊天记录式加载：首次读取最新一批，向上滚动加载更早消息，不使用页码切换。
- 语音转录参考是按 `message_id` 关联的派生小文本数据；缺失时页面隐藏转录块，不影响音频消息展示。
- 为支持阿里云房间消息页，数据同步清单同步派生的 `messages_shards/` 分片目录，不再每轮传完整 `messages.csv`。忽略状态文件位于 `website/data/room_messages_ignored_batches.json`，不由 Git 跟踪；两端按钮都发送操作到腾讯云权威节点串行提交并保存历史，再复制 revision 到阿里云。不要恢复 GitHub 同步或整文件双向覆盖。

### 成员房间上麦回放页

入口和文档：

- 页面入口：`/room-voice-replays`，短入口：`/radio`；兼容入口 `/radio-replays`
- API：`/api/room-voice-replays/login`、`/sessions`、`/sessions/{session_id}`、`/sessions/{session_id}/segments/{filename}`
- 数据源：`ROOM_VOICE_REPLAYS_DIR`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/`
- 鉴权：`ROOM_VOICE_REPLAYS_PASSWORD`，默认复用 `ROOM_MESSAGES_PASSWORD`；登录成功后使用仅限 API 路径的 HttpOnly Cookie，也可用 `X-Room-Voice-Replays-Password`
- 数据契约：`/home/snh48-fan-hub/doc/room_voice_replay_data_contract.md`

维护边界：

- 页面不进入公开导航并设置 `noindex,nofollow`；会话元数据、同期消息和 M4A 都必须先鉴权。
- 音频只通过校验后的固定文件名和支持 HTTP Range 的 API 提供，不把回放目录挂到 `/static`。
- 页面按整场墙钟时间同步消息，并根据 `wall_start_offset_seconds` 切换多个音频段；断流缺口应如实显示。
- schema v2 默认播放 AAC-LC 单声道兼容版；用户可切换到源 AAC 无二次编码的原始音质版，切换时保持当前分段、秒数和播放状态。schema v1 单文件会话继续降级为兼容播放。
- 点击或拖动原生音频进度条、点击同期消息、切换音频分段或播放模式时，播放器会显示“正在跳转/正在加载”状态；媒体恢复可播放后自动隐藏，长时间缓冲和加载失败会继续给出明确反馈。
- 有录音覆盖且能关联到音频分段的消息整行都可点击，并支持键盘回车或空格跳转到消息对应的墙钟时间；选择消息文字时不会误触跳转，录音缺口内的消息保持不可跳转。
- API 只接受 `segment_000001.m4a` 和 `segment_000001_original.m4a` 两类固定文件名；两种文件都沿用同一密码鉴权和 Range 边界。
- 数据同步只包含 `room_voice_replays/` 发布包中的两种派生 M4A、元数据和同期消息；腾讯云 `live_record/room_voice/` 的原始 FLV、日志和短时流 URL不得同步。
- `manifest.json` 是跨云可见性提交点：同步日志必须先出现 `room_voice_replays payload done`，再出现 `manifest committed` 和 `obsolete payload cleaned`；不得改回对整个目录一次普通 `rsync --delete`。

### 翻牌记录页

入口和文档：

- 页面入口：`/flip-cards`，短入口：`/flip`
- API：`/api/flip-cards/login`、`/status`、`/data`、`/html`、`/flip_data/audio/{filename}`、`/flip_data/video/{filename}`
- 数据源：`FLIP_CARDS_DATASET_PATH`，默认 `/home/snh48-fan-hub/flip_data/web/flip_cards.json`；`FLIP_CARDS_HTML_PATH`，默认 `/home/snh48-fan-hub/flip_chat.html`；`FLIP_CARDS_DATA_DIR`，默认 `/home/snh48-fan-hub/flip_data/`
- 鉴权：`FLIP_CARDS_PASSWORD`，默认复用 `OB_PASSWORD`；登录成功后使用仅限 API 路径的 HttpOnly Cookie，也可用 `X-Flip-Cards-Password`
- 产物说明：`/home/snh48-fan-hub/doc/flip_artifacts.md`

维护边界：

- 页面不进入公开导航并设置 `noindex,nofollow`；登录页、应用数据、下载版 HTML 和本地 MP3/MP4 都必须先鉴权。
- 后端只读取 fan-hub 已生成的 `flip_data/web/flip_cards.json` 和 `flip_chat.html`，并按文件名从 `flip_data/audio/`、`flip_data/video/` 流式读取本地媒体；不得把 `flip_data/` 挂到 `/static`。
- 阿里云只同步在线查看必要的 `flip_data/web/flip_cards.json`、`flip_chat.html`、`flip_data/audio/` 和 `flip_data/video/`；不常规同步 `flip_data/metadata/`、账号 Token、Cookie、脚本运行日志或下载缓存。
- 翻牌应用数据和下载版 HTML 都由 fan-hub 的 `scripts/tools/render_flip_chat.py` 生成；网站只负责鉴权发布和前端渲染，不负责拉取口袋48数据。

### 计分礼物管理页

入口和文档：

- 页面入口：`/score-gifts`，短入口：`/sg`
- API：`/api/score-gifts/data`、`/api/score-gifts/summary`、`/api/score-gifts/business-review`
- 数据源：`SCORE_GIFTS_DATA_PATH`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/score_gifts.json`
- 鉴权：默认复用 `GIFT_REPLIES_PASSWORD`；如需单独密码可设置 `SCORE_GIFTS_PASSWORD`；请求头 `X-Score-Gifts-Password`
- 数据契约：`/home/snh48-fan-hub/doc/score_gift_data_contract.md`

维护边界：

- 页面不进入公开导航，仅 URL 访问并要求密码。
- 后端只读取 `score_gifts.json` 派生小数据，不读取或同步完整 `messages.csv`、语音原文件、图片归档或敏感配置。
- `/api/score-gifts/business-review` 把核实操作交给腾讯云权威节点，在同一文件锁下更新 `score_gifts/` 下的 `live_business_fulfillments.json`，用于人工确认或修正直播计分礼物的业务兑换结果；与 fan-hub 分析器写入共用锁和版本历史。
- 页面按数据文件里的 `refresh_interval_seconds` 轮询轻量 summary；检测到新条目时只显示更新提示，不重建当前已加载详情，用户点击提示后才加载最新数据。该值由 fan-hub 的 `config/room_monitor.json` 中 `gift_reply_export_interval_seconds` 热更新，和礼物回复页保持一致。
- 阿里云只同步 `room_record/陈嘉仪_161808449/score_gifts/` 小目录，不同步整个 `room_record/陈嘉仪_161808449/`。

### 记忆页

入口和文档：

- 页面入口：`/memories`，短入口：`/memory`
- API：`/api/memories/data`、`/api/memories/submit`、`/api/memories/manage`、`/api/memories/review`
- 数据源：`MEMORIES_DATA_PATH`，默认 `/home/snh48_web/website/data/memories/memories.json`
- 鉴权：普通访问/提交使用 `MEMORIES_VIEW_PASSWORD` 和请求头 `X-Memories-Password`；应援会模式使用 `MEMORIES_FANCLUB_PASSWORD` 和 `X-Memories-Fanclub-Password`；本人模式使用 `MEMORIES_IDOL_PASSWORD` 和 `X-Memories-Idol-Password`
- 产品说明：`doc/memories.md`

维护边界：

- 页面记录“记忆”，不做粉丝贡献榜或排名。
- 普通 API 不返回平台 ID；后台数据保留平台 ID 用于去重和核对。
- `memories.json` 是运行数据，不由 Git 跟踪；仓库只保留 `website/data/memories/memories.example.json`。
- 初始数据可由 `python3 script/build_memories_seed.py` 从 fan-hub 的礼物回复、直播计分礼物和时光轴行程生成。
- 两个域名都开放提交和审核。阿里云把操作转发给腾讯云统一串行提交，随后接收相同 revision；普通 `core` 拉取明确不包含此文件。种子脚本也通过同一锁内合并入口写入，不能直接覆盖文件。

### 双服务器版本化状态与可靠待处理箱

- 详细契约、环境变量、迁移、历史恢复和巡检命令见 `doc/shared_runtime_state.md`。
- 腾讯云为唯一权威提交节点；阿里云是可接受操作的副本节点。首页背景词、房间忽略状态、计分礼物业务核实和记忆页都采用操作转发，不做对等整文件合并。
- 每次提交产生 gzip 不可变历史快照；复制失败进入 `website/data/shared_state_outbox/`，网站进程内线程自动重试，不新增常驻服务。
- 投诉和 QA 邮箱请求写入 `website/data/action_inbox/events/` 的不可变事件。`/ob` 显示来源服务器并用状态事件处理待办。

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

### 多服务器发布顺序

涉及网站页面、API、运行行为或用户可见功能时，默认按下面顺序，不要直接 `deploy all`：

1. 先部署腾讯云，让 `https://cjy.plus` 生效。
2. 在腾讯云执行本次任务相关烟测，并把验证结果和用户需要手动检查的 URL 发给用户。
3. 明确说明“阿里云尚未同步”，等待用户手动验证腾讯云并确认可以继续。
4. 用户确认后，再部署阿里云，并执行阿里云对应烟测。
5. 如果本次还涉及运行数据同步，也在用户确认腾讯云验证通过后再执行或等待阿里云从腾讯云拉取数据。

`deploy all` 只在用户明确要求一次性同步两台服务器，或本次变更确认没有用户可见影响时使用。文档、Codex 规则和部署说明更新通常不需要重启，但仍应按用户要求决定是否同步到远端。

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
| Python 代码、依赖、`.env`、服务入口 | 先 `python3 deploy/deploy.py deploy tencent`，用户确认后 `python3 deploy/deploy.py deploy aliyun` |
| 仅文档、Codex 文件、部署说明 | 通常可用 `--no-restart`；是否同步两台按用户目标决定 |
| 仅静态 JS/CSS 产物、图片、模板 HTML | 先腾讯云 `--no-restart` 并验证目标页面，用户确认后阿里云 `--no-restart` |
| Nginx 配置、证书、CSP | 先腾讯云 `--nginx --no-restart` 且 `nginx -t` 通过，用户确认后阿里云；只 reload Nginx |

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
OB_PASSWORD=观察页密码；翻牌页未单独设置时复用
SHARED_STATE_SYNC_ENABLED=true
SHARED_STATE_NODE_ID=tencent 或 aliyun
SHARED_STATE_IS_PRIMARY=腾讯云 true、阿里云 false
SHARED_STATE_PEER=另一台服务器 SSH 目标
SHARED_STATE_HISTORY_ROOT=/home/snh48_web/website/data/shared_state_history
SHARED_STATE_OUTBOX_ROOT=/home/snh48_web/website/data/shared_state_outbox
ACTION_INBOX_ROOT=/home/snh48_web/website/data/action_inbox
FLIP_CARDS_PASSWORD=独立翻牌页密码；留空复用 OB_PASSWORD
FLIP_CARDS_DATASET_PATH=/home/snh48-fan-hub/flip_data/web/flip_cards.json
FLIP_CARDS_HTML_PATH=/home/snh48-fan-hub/flip_chat.html
FLIP_CARDS_DATA_DIR=/home/snh48-fan-hub/flip_data
GIFT_REPLIES_PASSWORD=独立礼物回复页密码
ROOM_VOICE_REPLAYS_PASSWORD=独立上麦回放密码或留空复用房间消息密码
MEMORIES_VIEW_PASSWORD=记忆页访问密码
MEMORIES_FANCLUB_PASSWORD=记忆页应援会模式密码
MEMORIES_IDOL_PASSWORD=记忆页本人模式密码
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
curl -sS -D - -o /dev/null https://cjy.plus/gift-replies
curl -sS -D - -o /dev/null https://cjy.plus/gr
curl -sS -D - -o /dev/null https://cjy.plus/score-gifts
curl -sS -D - -o /dev/null https://cjy.plus/sg
curl -sS -D - -o /dev/null https://cjy.plus/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.plus/radio
curl -sS -D - -o /dev/null https://cjy.plus/memories
curl -sS -D - -o /dev/null https://cjy.plus/memory
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
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/gift-replies
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/gr
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/score-gifts
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/sg
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/radio
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/memories
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/memory
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

完整迁移清单见 `doc/runtime_migration.md`。

这些文件可能出现在服务器 `git status --short` 中，通常是运行期数据，不要作为代码冲突处理：

- `nohup.out`
- `website/data/room_messages_ignored_batches.json`
- `website/data/scroller_texts.json`
- `website/data/memories/memories.json`
- `website/data/shared_state_history/`
- `website/data/shared_state_outbox/`
- `website/data/action_inbox/`
- `website/data/balance_log.csv`
- `website/data/ip_clients.json`
- `website/data/ip_daily_quota.json`
- `website/data/read_notifications.json`
- `website/static/js/timeline.js.bak`
