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
| 腾讯云 | `cjy.plus` | `124.222.72.203` | `systemd` 服务 `snh48-web` | `/etc/nginx/conf.d/snh48.conf`，来源 `deploy/nginx.conf` |
| 阿里云香港 | `cjy.我爱你` / `cjy.xn--6qq986b3xl` | `8.210.188.184` | `systemd` 服务 `snh48-aliyun` | `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`，来源 `deploy/nginx-aliyun.conf` |

### 阿里云运行与 SSH 边界

- `snh48-aliyun.service` 使用不可登录的 `snh48-web` 账号、`UMask=0077`、`NoNewPrivileges=yes` 和 systemd 文件系统/设备沙箱；版本化 unit 为 `deploy/systemd/snh48-aliyun.service`，权限入口为 `deploy/harden_aliyun_runtime_permissions.sh`。
- FastAPI 只监听 `127.0.0.1:8000`。网站运行数据由 `snh48-web` 以目录 `0700` / 文件 `0600` 管理；`.env` 和 `/var/log/snh48` 仍由 root 以 `0600` 文件权限管理。
- 阿里云 `snh48-weibo-img-proxy.service` 使用 systemd `DynamicUser`，只监听 `127.0.0.1:8899`；unit 源在 fan-hub 的 `deploy/systemd/snh48-weibo-img-proxy-aliyun.service`，公网只能经 Nginx `/image-proxy/` 访问。
- 阿里云 sshd 只允许公钥认证；root 只能用公钥登录，密码、keyboard-interactive、GSSAPI 和 X11 转发均关闭。网站跨云共享状态使用 `/var/lib/snh48-web/.ssh/` 下的专用密钥，远端 `authorized_keys` 只允许 `mutate` / `inbox-put` peer 子命令，不是交互式 root 通道。root cron 的必要数据拉取使用独立运维密钥，不与网站进程共享。

### QA 节点边界

- `QA_ENABLED` 控制当前节点是否注册 QA API、执行知识库归档维护和启动模型预热；默认值为 `true`。
- 腾讯云设置 `QA_ENABLED=false`，`/qa` 只返回本机 503 未启用页面，`/api/qa/*` 不注册，不保留知识库索引和嵌入模型缓存。
- 阿里云保持 `QA_ENABLED=true` 并独立提供 QA。两个站点之间不设置 QA 跳转或互链。
- QA 关闭不影响 `website/data/action_inbox/` 中已有邮箱请求事件，也不授权删除历史问答归档或原始转录文件。

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
| 阿里云香港 | 网站必要数据副本，路径 `/home/snh48-fan-hub` | 由阿里云 cron 主动从腾讯云拉取最小数据集，供香港版暨对外公开版网站使用 |

网站必要数据集：

- `schedule_record/chenjiayi_events.csv`（事件/行程主文件，网站优先读取）
- `schedule_record/schedule.csv`（事件/行程兼容副本，旧配置和回退读取）
- `social_record/timeline/chenjiayi_social_timeline.json`（微博/抖音已过滤的轻量时光轴数据；网站消费副本，阿里云不运行采集器）
- `/home/snh48_web/website/data/scroller_texts.json`（首页背景词非 Git 运行状态）
- `/home/snh48_web/website/data/memories/memories.json`（记忆页运行数据；格式示例见 `website/data/memories/memories.example.json`）
- `live_push_replays/陈嘉仪_161808449/`
- `room_record/陈嘉仪_161808449/live_covers/`
- `room_record/陈嘉仪_161808449/gift_replies/`
- `room_record/陈嘉仪_161808449/messages_shards/`（包含公开房间和小房间消息，按 `room_type` / `room_label` 标识来源）
- `room_record/陈嘉仪_161808449/audio_transcripts/`
- `room_record/陈嘉仪_161808449/room_voice_replays/`（同步默认 AAC-LC 单声道兼容版、源 AAC 原始音质版 M4A、会话元数据和同期消息；不含原始 FLV）
- `room_record/陈嘉仪_161808449/score_gifts/`
- `room_record/pk_scores/current.json`（房间计分 PK 派生小数据；首轮只供腾讯云 `/score-pk`，阿里云同步待用户验收后另行确认）
- `flip_data/web/`（密码保护的脱敏账号清单、schema v4 账号数据和默认兼容副本）
- `flip_data/audio/{account_id}/`、`flip_data/video/{account_id}/`（账号级本地播放依赖；不含 `metadata/`、Token 或登录状态）
- 图片通过网站 `/image-proxy/` 访问，不把 `schedule_record/images/` 作为阿里云常规同步项。

数据同步脚本：

```bash
python3 deploy/deploy.py sync-data tencent aliyun
bash deploy/sync-from-tencent.sh
bash deploy/sync-from-tencent-if-changed.sh
bash deploy/sync-to-aliyun.sh
bash deploy/sync-to-aliyun-if-changed.sh
```

线上自动同步在阿里云执行：cron 每分钟运行 `deploy/sync-from-tencent-if-changed.sh`，通过 SSH 分组检查腾讯云源数据指纹，只有变化时调用 `deploy/sync-from-tencent.sh` 从腾讯云主动拉取对应分组。`deploy/sync-to-aliyun.sh`、`deploy/sync-to-aliyun-if-changed.sh` 和 `deploy/sync-to-aliyun-loop.sh` 只作为腾讯云临时手动推送兜底，不应放回腾讯云生产 cron 或常驻进程。`deploy.py sync-data` 是本地手动触发入口。`room_voice_replays/` 在三个入口中都采用 payload 先同步、`manifest.json` 临时文件原子改名、旧 payload 最后清理的发布顺序，避免大音频传输期间网站提前看到半个新会话。管理员新增的事件和行程统一写入 fan-hub 事件/行程 CSV 并按 `core` 单向拉取。四个可写业务状态不进入普通分组同步，也不走 Git；即时一致性由 `doc/shared_runtime_state.md` 的腾讯云权威提交、阿里云操作转发、版本复制和持久 outbox 保证。计分礼物目录的其他只读派生文件继续走 `dynamic`，但所有 rsync 入口都排除可写的 `live_business_fulfillments.json` 和 `.*.lock`。

自动同步运行状态口径：

- 阿里云 cron：`* * * * * bash /home/snh48_web/deploy/sync-from-tencent-if-changed.sh >> /var/log/snh48/sync-from-tencent.log 2>&1`
- 阿里云日志：`/var/log/snh48/sync-from-tencent.log`
- 阿里云状态文件：`/tmp/snh48_sync_from_tencent.state.core`、`/tmp/snh48_sync_from_tencent.state.dynamic`
- 阿里云锁文件：`/tmp/snh48_sync_from_tencent_change.lock`、`/tmp/snh48_sync_from_tencent.lock`
- 腾讯云旧推送日志：`/var/log/snh48/sync-to-aliyun.log`，新方案接管后不应持续更新。

同步分组：`core` 包含统一事件/行程 CSV、社交时间轴、直播回放汇总和直播封面；`dynamic` 包含礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物只读派生文件、脱敏 `flip_data/web/` 和账号级翻牌音视频依赖。翻牌数据先同步账号 JSON，再原子提交 `web/accounts.json`。手动运行 `bash deploy/sync-from-tencent.sh` 不带参数时仍拉取全部分组，也可以显式传 `core` 或 `dynamic`。

排查时不要把每分钟 `source changed groups=dynamic, pulling...` 直接判定为异常。`gift_replies/`、`messages_shards/`、`audio_transcripts/`、`room_voice_replays/`、`score_gifts/`、`flip_data/web/` 和翻牌音视频等派生数据在后台更新时，动态组源数据指纹会变化，阿里云每分钟拉取是预期行为。判断是否异常时，应结合腾讯云最近 mtime、阿里云同步日志和 1 到 2 分钟延迟。如果长期出现 `groups=core,dynamic`，需要确认 `core` 组是否真的持续变化，或检查状态文件是否被清理。

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

密码保护页的登录反馈分为“正在验证密码”和“密码正确，正在加载数据”两阶段。礼物、房间消息、计分礼物和观察页通过轻量 `/verify` 接口先确认密码；记忆页公开数据无需登录，只有应援会/本人管理模式需要独立密码；翻牌、上麦回放和隐藏社交凭据页使用 `/login` 写入路径限定 Cookie。密码已确认后若完整数据读取失败，前端保留登录状态并提供免重输密码的重试按钮。

### 社交 Cookie 隐藏管理页

- 页面 `/social-credentials-admin` 不进入任何公开导航并设置 `noindex,nofollow`；API 前缀 `/api/social-credentials`。
- 只在腾讯云主节点启用更新；`SHARED_STATE_IS_PRIMARY=false` 时无论环境开关如何均返回 403。阿里云不保存 Cookie，也不需要 fan-hub 采集脚本或桥。
- 新 Cookie 只经 HTTPS 请求体传给 fan-hub 的 `scripts/web/social_credentials_admin.py` stdin；桥先实时验证，成功后原子替换微博/抖音对应主备槽位或 B站主槽位，响应和状态不含 Cookie。
- 生产应设置独立 `SOCIAL_CREDENTIALS_ADMIN_PASSWORD`；迁移期留空复用现有 `OB_PASSWORD`。相关边界见 fan-hub `doc/social_credentials_admin.md`。

### 礼物回复管理页

入口和文档：

- 页面入口：逐条明细 `/room/gifts`；综合回礼 `/room/gift-senders`，并从 `/room` 顶部进入；旧 `/gift-replies`、`/gift-replies/senders` 和 `/gr` 不保留兼容路由
- API：`/api/gift-replies/verify`、`/api/gift-replies/data`、`/api/gift-replies/summary`、`/api/gift-replies/senders`、`/api/gift-replies/sender-history`
- 数据源：`GIFT_REPLIES_DIR`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/`
- 鉴权：独立环境变量 `GIFT_REPLIES_PASSWORD`，请求头 `X-Gift-Replies-Password`
- 数据契约：`/home/snh48-fan-hub/doc/gift_reply_data_contract.md`

维护边界：

- 页面不进入公开导航，仅 URL 访问并要求密码。
- 逐条明细默认每页 `100` 条并按数据文件里的 `refresh_interval_seconds` 自动刷新。综合回礼页按相同间隔轮询轻量 summary；检测到礼物或回复统计变化时只显示更新提醒，用户点击后才刷新送礼人列表，不自动打断当前阅读。默认间隔 `30` 秒，可在 fan-hub 的 `config/room_monitor.json` 中热更新。
- 综合回礼页以稳定 `sender_id`（缺失时回退昵称）聚合同一送礼人的日期范围内历史，送礼人和组内礼物都按最新送礼时间倒序；默认起始日期为 `2026-05-30`，默认显示全部送礼人，可筛选“有未回复”或“已全部回复”，每个送礼人栏始终显示对应状态标签。
- 送礼人摘要一次返回全部匹配结果并默认折叠；展开时再按需请求该人的历史，避免首屏下载所有礼物明细。统计与个人计数默认隐藏，由页面上的低显眼度“统计”按钮切换；标题及返回 Room、逐条明细入口随页面滚动自然离开视野，不固定占据顶部空间。
- 综合回礼页只整理和展示真实逐条回礼状态，不自行推断一次综合感谢覆盖了哪些旧礼物，也不写入额外回礼状态。
- 后端只读取 `gifts.csv` 和 `summary.json` 派生小数据，不读取或同步完整 `messages.csv`、语音原文件、图片归档或敏感配置。

### 房间消息管理页

入口和文档：

- 页面入口：`/room-messages`，短入口：`/room`。
- API：`/api/room-messages/verify`、`/api/room-messages/data`、`/api/room-messages/summary`、`/api/room-messages/ignore-latest-batch`、`/api/room-messages/undo-ignore`
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

- 页面入口：`/room-voice-replays`，短入口：`/radio`
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
- API：`/api/flip-cards/login`、`/status`、`/accounts`、`/data?account_id=...`、`/accounts/{account_id}/flip_data/{kind}/{filename}`、`/account-management/*`
- 数据源：`FLIP_CARDS_ACCOUNTS_PATH` 默认 `/home/snh48-fan-hub/flip_data/web/accounts.json`；账号 JSON 位于 `web/accounts/`；`FLIP_CARDS_DATASET_PATH` 保留旧默认账号兼容；`FLIP_CARDS_DATA_DIR` 为媒体根目录
- 鉴权：`FLIP_CARDS_PASSWORD`，默认复用 `OB_PASSWORD`；登录成功后使用仅限 API 路径的 HttpOnly Cookie，也可用 `X-Flip-Cards-Password`
- 产物说明：`/home/snh48-fan-hub/doc/flip_artifacts.md`

维护边界：

- 页面不进入公开导航并设置 `noindex,nofollow`；登录页、应用数据和本地 MP3/MP4 都必须先鉴权。
- 后端只按脱敏清单允许的稳定口袋号读取账号 JSON 和账号子目录媒体；不得把 `flip_data/` 挂到 `/static`。schema v4 逐条包含回复成员身份，语音记录可带转录参考，缺失时隐藏。
- 腾讯云、阿里云使用同一页面和代码。`FLIP_CARDS_ACCOUNT_ADMIN_ENABLED` 默认跟随 `SHARED_STATE_IS_PRIMARY`：腾讯云可在同一弹窗发送短信、验证码登录并启动后台刷新；阿里云弹窗只显示当前节点不开放账号操作，不提供腾讯云跳转。
- 网页账号管理继续受翻牌密码 Cookie 保护，POST 还要求同源；手机号只进入 fan-hub 本机短期 `0600` 会话，验证码不落盘，Token 只进入 `config/accounts.json`。阿里云只同步脱敏 `web/`、账号级音频和视频，不同步 `metadata/`、`transcripts/`、登录会话或任务日志。
- 翻牌应用数据由 fan-hub 的 `scripts/tools/render_flip_chat.py` 生成；本地 Whisper 转录仍在 fan-hub 数据生成阶段完成，网站不对转录正文调用 Codex 或其他外部润色模型。页面采用浅色聊天消息流，引用提问使用灰色摘要，转录参考使用语音条下方的分隔文本区。顶部筛选默认收起且默认选择陈嘉仪，其他回复成员可单独筛选；陈嘉仪头像显示“嘉仪”，其他成员显示完整姓名。账号登录和更新状态入口分离，状态弹窗可收起并恢复；首次只渲染筛选结果中最新 50 条翻牌，向上滚动每次补入 50 条并保持阅读位置，音频使用 `preload=none`，避免 iPhone Safari 登录后同时初始化全部媒体。底部“跳到最新”只滚动当前数据，检测到新版本后显示“有新记录，点击查看最新”，此时才重新加载并跳到底部。问题状态 Tag、双向跳转和 4 秒高对比高亮保持不变。

### 计分礼物管理页

入口和文档：

- 页面入口：`/score-gifts`，兼容入口：`/score`
- API：`/api/score-gifts/verify`、`/api/score-gifts/data`、`/api/score-gifts/summary`、`/api/score-gifts/export.xlsx`、`/api/score-gifts/sender-export.xlsx`、`/api/score-gifts/business-review`
- 数据源：`SCORE_GIFTS_DATA_PATH`，默认 `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/score_gifts.json`
- 鉴权：默认复用 `GIFT_REPLIES_PASSWORD`；如需单独密码可设置 `SCORE_GIFTS_PASSWORD`；请求头 `X-Score-Gifts-Password`
- 数据契约：`/home/snh48-fan-hub/doc/score_gift_data_contract.md`

维护边界：

- 页面不进入公开导航，仅 URL 访问并要求密码。
- 后端只读取 `score_gifts.json` 派生小数据，不读取或同步完整 `messages.csv`、语音原文件、图片归档或敏感配置。
- `/api/score-gifts/business-review` 把核实操作交给腾讯云权威节点，在同一文件锁下更新 `score_gifts/` 下的 `live_business_fulfillments.json`，用于人工确认或修正直播计分礼物的业务兑换结果；与 fan-hub 分析器写入共用锁和版本历史。
- 页面按数据文件里的 `refresh_interval_seconds` 轮询轻量 summary；检测到新条目时只显示更新提示，不重建当前已加载详情，用户点击提示后才加载最新数据。该值由 fan-hub 的 `config/room_monitor.json` 中 `gift_reply_export_interval_seconds` 热更新，和礼物回复页保持一致。
- 详情区可导出当前筛选条件下的逐笔明细；“送礼用户分布”可导出包含“送礼用户汇总”和“投分明细”两个工作表的 Excel，逐笔记录按用户汇总顺序分组，并保留送礼时间、房间/直播来源、计分礼物、数量、单个分值和对应分数。
- 阿里云只同步 `room_record/陈嘉仪_161808449/score_gifts/` 小目录，不同步整个 `room_record/陈嘉仪_161808449/`。

### 房间计分 PK 页

入口和文档：

- 页面入口：`/score-pk`
- API：`/api/pk-score/verify`、`/api/pk-score/data`
- 数据源：`/home/snh48-fan-hub/room_record/pk_scores/current.json`
- 鉴权：复用 `SCORE_GIFTS_PASSWORD`，请求头 `X-PK-Score-Password`
- 数据契约：`/home/snh48-fan-hub/doc/pk_score_data_contract.md`

维护边界：

- 页面不进入公开导航并设置 `noindex,nofollow`；显示双方基础分、统计起点后新增分、累计分、当前差值和计分礼物明细。
- 后端只读取 fan-hub 派生的小 JSON，不读取两位成员完整 `messages.csv`，明细不含 sender ID、完整房间正文或本地媒体路径。
- 前端按数据中的 `refresh_interval_seconds` 自动刷新，密码验证复用计分礼物页的限速和凭据。
- 首轮只在腾讯云 `cjy.plus` 验证。阿里云自动同步和页面发布必须等用户确认腾讯云效果后另行实施；届时也只允许同步 `room_record/pk_scores/`，不得同步曾雪婷完整房间数据。

### 记忆页

入口和文档：

- 页面入口：`/memories`，短入口：`/memory`
- API：`/api/memories/verify`、`/api/memories/data`、`/api/memories/submit`、`/api/memories/manage`、`/api/memories/review`
- 数据源：`MEMORIES_DATA_PATH`，默认 `/home/snh48_web/website/data/memories/memories.json`
- 鉴权：公开浏览和提交不需要访问密码，但提交受 `MEMORIES_SUBMIT_ENABLED`、基础审核和 IP 限速约束；应援会模式使用 `MEMORIES_FANCLUB_PASSWORD` 和 `X-Memories-Fanclub-Password`；本人模式使用 `MEMORIES_IDOL_PASSWORD` 和 `X-Memories-Idol-Password`；`/api/memories/verify` 保留为历史管理入口，不是公开浏览前置步骤
- 产品说明：`doc/memories.md`

维护边界：

- 页面记录“记忆”，不做粉丝贡献榜或排名。
- 普通 API 不返回平台 ID；后台数据保留平台 ID 用于去重和核对。
- `memories.json` 是运行数据，不由 Git 跟踪；仓库只保留 `website/data/memories/memories.example.json`。
- 初始数据可由 `python3 script/build_memories_seed.py` 从 fan-hub 的礼物回复、直播计分礼物和时光轴行程生成。
- 两个域名都开放公开提交；公开提交只进入基础审核通过或待人工审核状态，确认和隐藏仍由应援会/本人管理模式完成。阿里云把写操作转发给腾讯云统一串行提交，随后接收相同 revision；普通 `core` 拉取明确不包含此文件。种子脚本也通过同一锁内合并入口写入，不能直接覆盖文件。

### 双服务器版本化状态与可靠待处理箱

- 详细契约、环境变量、迁移、历史恢复和巡检命令见 `doc/shared_runtime_state.md`。
- 腾讯云为唯一权威提交节点；阿里云是可接受操作的副本节点。首页背景词、房间忽略状态、计分礼物业务核实和记忆页都采用操作转发，不做对等整文件合并。
- 每次提交产生 gzip 不可变历史快照；复制失败进入 `website/data/shared_state_outbox/`，网站进程内线程自动重试，不新增常驻服务。
- 投诉、QA 邮箱请求和客服聊天消息写入 `website/data/action_inbox/events/` 的不可变事件。客服识别码计算 SHA-256 内部会话编号，并在 `0600` 事件中保存用户自定义识别码供密码保护的 `/ob` 和飞书通知展示；事件通过现有双服务器待处理箱复制。

### 时光轴与分类筛选

入口和文档：

- 页面入口：`/timeline`
- 源文件：`website/static/js/timeline.js`
- 生产产物：`website/static/js-dist/timeline.js`
- 详细行为文档：`doc/timeline_badges.md`、`doc/admin_guide.md`、`doc/ai_agent_instructions.md`

时光轴将传统的行程与事件拆成独立的“行程”和“事件”筛选；`schedule.csv` 中 `event_type=行程` 归入行程，`里程碑` 和手工历史节点归入事件，`日常` 不再输出到时间轴。所有里程碑统一只显示“里程碑”主标签；“首演”“巡演”“助演”关键词子标签只用于非里程碑条目。微博、抖音、抖音共创和直播仍分别按来源筛选。抖音“相关视频”使用稳定的作品页面 URL，不展示会过期的签名 MP4 URL；社交卡片标题使用来源加正文摘要，过长时截断并追加省略号。

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
FLIP_CARDS_ACCOUNTS_PATH=/home/snh48-fan-hub/flip_data/web/accounts.json
FLIP_CARDS_DATA_DIR=/home/snh48-fan-hub/flip_data
FLIP_CARDS_ACCOUNT_ADMIN_ENABLED=腾讯云 true；阿里云 false（默认跟随 SHARED_STATE_IS_PRIMARY）
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
curl -sS -D - -o /dev/null https://cjy.plus/room/gifts
curl -sS -D - -o /dev/null https://cjy.plus/room/gift-senders
curl -sS -D - -o /dev/null https://cjy.plus/score-gifts
curl -sS -D - -o /dev/null https://cjy.plus/score
curl -sS -D - -o /dev/null https://cjy.plus/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.plus/radio
curl -sS -D - -o /dev/null https://cjy.plus/memories
curl -sS -D - -o /dev/null https://cjy.plus/memory
test "$(curl -sS -o /dev/null -w '%{http_code}' https://cjy.plus/qa)" = 503
test "$(curl -sS -o /dev/null -w '%{http_code}' https://cjy.plus/api/qa/status)" = 404
curl -sS -D - -o /dev/null https://cjy.plus/api/timeline/schedule
curl -sS -D - -o /dev/null https://cjy.plus/static/js/main.js
curl -sS -D - -o /dev/null https://cjy.plus/static/js/timeline.js
curl -sS -D - -o /dev/null https://cjy.plus/image-proxy/health
```

阿里云：

```bash
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/timeline
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/room/gifts
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/room/gift-senders
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/score-gifts
curl -sS -D - -o /dev/null https://cjy.xn--6qq986b3xl/score
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
