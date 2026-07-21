# /home/snh48_web 后台运行与同步状态

更新日期：2026-07-21 CST +0800

翻牌网站 HTML 移除专项复核：2026-07-21 15:31 CST +0800

电台/翻牌交互统计阿里云同步专项复核：2026-07-21 15:12 CST +0800

双服务器版本化运行状态阿里云完成发布专项复核：2026-07-21 15:15 CST +0800

翻牌应用页与阿里云同步专项复核：2026-07-20 21:54 CST +0800

双服务器版本化运行状态腾讯云阶段发布专项复核：2026-07-20 17:59 CST +0800

计分礼物刷新体验与阿里云补发专项复核：2026-07-20 12:06 CST +0800

腾讯云翻牌记录页发布专项复核：2026-07-20 04:18 CST +0800

腾讯云成员房间上麦回放发布专项复核：2026-07-17 16:13 CST +0800

腾讯云成员房间上麦双版本播放专项复核：2026-07-20 12:35 CST +0800

阿里云成员房间上麦双版本与跳转体验专项复核：2026-07-20 16:21 CST +0800

阿里云成员房间上麦回放发布与同步专项复核：2026-07-19 04:51 CST +0800

本文件记录 `/home/snh48_web` 的长期运行方式和腾讯云到阿里云的数据同步口径。进程 PID 会随重启变化，排查时以文中的命令实时查询为准。

## 当前运行方式

| 环境 | 网站服务 | 监听 | 说明 |
|------|----------|------|------|
| 腾讯云 `cjy.plus` | screen 会话运行 `python -m website.main` | `127.0.0.1:8000`，公网由 Nginx 代理 | checkout 为 `35a4134`；2026-07-21 15:28:30 CST 重启为 screen `1407658.snh48`、Python PID `1407675`，本轮运行命令临时覆盖 `QA_WARMUP_ON_STARTUP=false`；本机 `/flip-cards` 为 200，旧 `/api/flip-cards/html` 为 404，未登录 `/api/flip-cards/status` 为 401，页面不再含下载 HTML 入口；共享状态开关为 `tencent True True True` |
| 阿里云香港 `cjy.我爱你` | systemd 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | checkout 为 `35a4134`；部署流程已于 2026-07-21 15:29:22 CST 重启服务，PID `3257540`，active/running；公网 `/flip-cards` 为 200，旧 `/api/flip-cards/html` 为 404，未登录 `/api/flip-cards/status` 为 401，页面不再含下载 HTML 入口；阿里云旧 `/home/snh48-fan-hub/flip_chat.html` 副本已删除且同步脚本不再引用；既有未跟踪 `website/data/runtime_backups/` 与 `website/static/js/timeline.js.bak` 保持原样 |

## 常用状态命令

腾讯云：

```bash
screen -ls
ps -eo pid,ppid,lstart,cmd | grep 'python -m website.main' | grep -v grep
ss -ltnp | grep ':8000'
tail -f /var/log/snh48/snh48_screen.log
```

阿里云：

```bash
systemctl status snh48-aliyun
journalctl -u snh48-aliyun --no-pager -n 80
ss -ltnp | grep ':8000'
```

Nginx：

```bash
nginx -t
systemctl status nginx
```

2026-07-17 本次重启发现既有 `/api/qa/status` 会在模型尚未加载时启动后台预热；模型加载线程会在当前小规格主机上短时占用 GIL，导致全站请求等待。为先恢复用户页面，本次 screen 命令临时覆盖 `QA_WARMUP_ON_STARTUP=false`，未修改 `.env`；QA 仍会在状态接口或首次使用时按既有逻辑加载。该现象不是上麦回放代码引起，后续如专项优化 QA 启动行为，应单独评估和发布。

## 阿里云 HTTPS 证书与月度提醒

阿里云公开站 `cjy.我爱你` / `cjy.xn--6qq986b3xl` 使用 Let's Encrypt / Certbot 证书。2026-07-05 已确认线上 HTTPS 可用，证书到期时间为 `2026-09-02 00:09:46+00:00`，服务器存在 `certbot.timer`。

| 项 | 当前值 |
|----|--------|
| 证书路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem` |
| 私钥路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/privkey.pem` |
| 自动续期 | 阿里云 `certbot.timer` |
| 月度提醒脚本 | `/home/snh48_web/script/check_https_certificate.py` |
| 月度提醒 cron | `0 10 1 * * cd /home/snh48_web && /usr/bin/python3 script/check_https_certificate.py --host cjy.xn--6qq986b3xl --cert-file /etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem --output /home/snh48_web/website/data/ops_reminders/https_certificate.md >> /var/log/snh48/https-cert-reminder.log 2>&1` |
| 提醒日志 | `/var/log/snh48/https-cert-reminder.log` |
| 最新提醒报告 | `/home/snh48_web/website/data/ops_reminders/https_certificate.md` |

操作细节见 `doc/ops/https_certificate_reminder.md`。证书仍有效且 Certbot 自动续期存在时，不要手动替换证书。

## 腾讯云到阿里云的数据同步任务

当前生产自动同步是“阿里云主动拉取腾讯云”，不是腾讯云主动推送。

> 2026-07-21 15:31 翻牌网站 HTML 移除专项复核：网站仓库提交 `35a4134` 已推送并部署。腾讯云网站 screen 重启为 `1407658.snh48`、PID `1407675`；阿里云 `snh48-aliyun` 重启为 PID `3257540`。两端 `/flip-cards` 均为 200，旧 `/api/flip-cards/html` 均为 404，未登录 `/api/flip-cards/status` 均为 401，页面源码不再包含 `downloadHtmlLink`、`/api/flip-cards/html` 或“下载版”。阿里云旧 `/home/snh48-fan-hub/flip_chat.html` 副本已删除；已部署的动态同步脚本和 `deploy.py` 不再引用 `flip_chat.html`，后续 cron 不会重新拉取该 HTML。腾讯云 fan-hub 的 `flip_chat.html` 仍保留为本地下载查看产物，不作为网站同步项。

> 2026-07-21 15:12 用户确认腾讯云后复核阿里云发布。另一条协作流程已先把阿里云快进到 `5ea0077` 并于 15:06:33 重启 `snh48-aliyun`，因此本轮没有重复拉取或重启。阿里云每分钟 cron 仍启用；15:07、15:08 两轮日志均按 `room_voice_replays payload done` → `manifest committed` → `obsolete payload cleaned` 顺序完成并更新状态。公网 `/radio`、`/flip-cards` 为 200，页面含最新电台/翻牌交互统计代码，未登录电台 API 为 401。跨云健康检查确认最新会话 `rv_20260720_212821_main_36376935_cff7b6` 的消息与腾讯云一致，兼容版、原始音质版共 2 个媒体对象均可通过阿里云鉴权 Range 播放。共享状态角色为 `tencent True True True` / `aliyun False True True`，腾讯云持久 outbox 无积压；阿里云没有 outbox 文件积压。

> 2026-07-21 15:15 共享运行状态第二阶段专项复核：部署前把四个当前状态以 `0600` 权限备份到阿里云 `website/data/runtime_backups/shared-state-rollout-20260721T070349Z/`，并补齐显式 `SHARED_STATE_*` / `ACTION_INBOX_ROOT` 配置。首页背景词、房间忽略、计分业务和记忆页的 revision 与状态 SHA-256 在两端逐项一致；腾讯云向阿里云手动幂等重放四项均成功，阿里云向腾讯云幂等回送既有待办也成功，两端 outbox 均为 0。可靠待处理箱现有 9 条腾讯云来源事件，文件均为 `0600`；模板按 `origin_node` / `origin_label` 区分今后的腾讯云与阿里云请求。阿里云未发现可迁移的旧投诉或邮箱记录，因此没有制造测试待办。公网 `/`、`/scroller-admin`、`/room`、`/sg`、`/memories`、`/ob` 均为 200，首页词 API 返回 22 条，未认证的房间、计分、记忆、观察页及首页词写接口均为 401。

> 2026-07-20 21:54 翻牌应用页发布后，阿里云从 `b8da683` 快进到 `7d5c3b1` 并重启 `snh48-aliyun`。同轮累计补齐 `344f3a1` 至 `92a896c` 的共享运行状态、上麦回放原子同步和文档提交；阿里云配置已变为 `aliyun False True True`。随后在阿里云手动运行 `bash deploy/sync-from-tencent.sh dynamic`，日志确认 `flip_data/web/flip_cards.json done`、`flip_chat.html done`、`flip_data/audio done`、`flip_data/video done` 和 `All sync completed`。腾讯云与阿里云的 `flip_data/web/flip_cards.json` mtime 均为 2026-07-20 21:38 CST，阿里云受保护数据 API 验证通过。后续纯文档提交以 `--no-restart` 快进，公开烟测继续通过。

> 2026-07-20 18:06 上麦回放原子同步提交 `402551a` 已完成 Shell 语法、通用部署命令顺序和现有共享状态排除回归测试并推送。腾讯云网站 checkout 已包含该提交，手动推送兜底入口已更新但未执行；阿里云仍停留在 `2264e89`，其每分钟主动拉取暂未加载新脚本。原因是 `402551a` 的祖先包含尚待用户确认的共享运行状态提交 `344f3a1`，不能为本任务越过分阶段发布规则把无关功能一并上线。当前最新上麦会话已由腾讯云健康检查确认在阿里云完整可播；录音服务和网站服务均未因本次同步脚本改动重启。

> 2026-07-20 17:59 腾讯云先行部署 `344f3a1`：首页背景词、房间忽略、计分业务和记忆页各建立 1 个基线 revision；既有投诉/邮箱请求导入 9 条，来源均记录为“腾讯云 cjy.plus”，事件权限为 `0600`。阿里云尚未部署新接收脚本，因此腾讯云 outbox 暂有状态 4 项、待处理箱 9 项，属于分阶段发布的预期积压。当前阿里云 cron 仍按旧提交拉取 `memories.json` 和整个计分目录；用户验收后部署阿里云时，才会切换为四个可写状态只走 revision/outbox，并从普通 rsync 排除 `memories.json`、`live_business_fulfillments.json` 和锁文件。

> 2026-07-20 用户确认腾讯云双音质、加载/跳转状态和整行消息跳转体验后，阿里云从 `32bc7f1` 快进到 `2264e89`。由于累计提交包含双版本 Python API，16:18:04 只重启 `snh48-aliyun` 以加载新模块；16:21 采样 PID `3021633`、enabled、active/running、`NRestarts=0`。`/radio` 公网页面包含新交互，未登录 sessions API 为 401；鉴权详情返回 315 条消息和 `compatible/original`，兼容版与原始音质版经公网 Nginx 的 Range 请求均为 206。上麦 schema v2 manifest 和两个 M4A 此前已由阿里云每分钟 `dynamic` 拉取 cron 自动同步，本轮没有手动扩大数据同步范围。

> 2026-07-20 12:03 用户确认腾讯云计分礼物页面后，阿里云从 `643ad46` 快进到 `4369db9`，同时补齐此前尚未部署的翻牌记录页代码和 dynamic 同步清单；12:03:46 重启 `snh48-aliyun`。既有阿里云 cron 自动检测到变化并拉取必要数据，12:06:05 记录 `flip_data/audio done`、`flip_data/video done`、`All sync completed` 和 `state updated`。腾讯云与阿里云 `flip_chat.html` SHA-256 同为 `aae4347c71111e44c0443faf6cfb35a97587f50c951b0dbfae6aff90a867ab9c`；音频清单摘要同为 `ccbde5d7a00598467e22357beea47e72852201bce1c8b5b56e3b22be6b67ea89`、共 185 个文件，视频清单摘要同为 `3129f251859e67224872c14d5d7e3a6a75bf0c744e2633b9947faa6020b1abe8`、共 4 个文件。

> 2026-07-19 用户确认腾讯云页面后，阿里云已快进到 `3a7b05b` 并加载把 `room_voice_replays/` 纳入 `dynamic` 组的新脚本。04:50 手动同步成功，04:51 cron 又自动检测到 dynamic 变化并记录 `room_voice_replays done`、`state updated`。腾讯云与阿里云 `manifest.json` SHA-256 同为 `7679687352fc2cc210d3ecbbb55dcaa53a466556098d7680954aa8ff8bda2f82`，当时 `session_count=0`；原始 FLV 未同步。

| 项 | 当前值 |
|----|--------|
| 自动任务所在服务器 | 阿里云香港 |
| cron | `* * * * * bash /home/snh48_web/deploy/sync-from-tencent-if-changed.sh >> /var/log/snh48/sync-from-tencent.log 2>&1` |
| 轻量检查脚本 | `/home/snh48_web/deploy/sync-from-tencent-if-changed.sh` |
| 实际拉取脚本 | `/home/snh48_web/deploy/sync-from-tencent.sh` |
| 状态文件 | `/tmp/snh48_sync_from_tencent.state.core`、`/tmp/snh48_sync_from_tencent.state.dynamic` |
| 锁文件 | `/tmp/snh48_sync_from_tencent_change.lock`、`/tmp/snh48_sync_from_tencent.lock` |
| 同步日志 | `/var/log/snh48/sync-from-tencent.log` |
| 源服务器 | 腾讯云 `root@124.222.72.203` |
| 目标服务器 | 阿里云本机 |

脚本逻辑：

1. 阿里云每分钟 SSH 到腾讯云，分别计算 `core` 和 `dynamic` 两组源数据指纹。
2. 两组指纹都没有变化时只写入 `no source changes, skipped`。
3. 某组指纹变化时调用 `sync-from-tencent.sh <group>`，在一次同步内复用同一条 SSH ControlMaster 连接并用 `rsync` 拉取对应分组。
4. 同步成功后更新 `/tmp/snh48_sync_from_tencent.state.core` 和 `/tmp/snh48_sync_from_tencent.state.dynamic`。

同步内容：

| 腾讯云源路径 | 阿里云目标路径 | 说明 |
|--------------|----------------|------|
| `/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv` | 同路径 | 事件/行程主文件，网站优先读取 |
| `/home/snh48-fan-hub/schedule_record/schedule.csv` | 同路径 | 兼容副本 |
| `/home/snh48_web/website/data/manual_events.csv` | 同路径 | 网站手动事件运行数据 |
| `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/` | 同路径 | 直播回放汇总 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 同路径 | 直播封面 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 同路径 | 礼物回复派生小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/` | 同路径 | 房间消息分片小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 同路径 | 语音转录文本数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 同路径 | 密码保护的上麦回放发布包；包含兼容版/原始音质版派生 M4A、元数据和同期消息，原始 FLV 不同步 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 同路径 | 计分礼物只读派生文件；排除 `live_business_fulfillments.json` 和 `.*.lock`，可写业务状态走版本化共享状态 |
| `/home/snh48-fan-hub/flip_data/web/flip_cards.json` | 同路径 | 翻牌记录应用页最小 JSON；不含完整 metadata、Token 或配置 |
| `/home/snh48-fan-hub/flip_data/audio/`、`/home/snh48-fan-hub/flip_data/video/` | 同路径 | 翻牌页本地音视频依赖；不含 `flip_data/metadata/` |

同步分组：

| 分组 | 内容 | 典型频率 |
|------|------|----------|
| `core` | 事件/行程 CSV、手动事件 CSV、直播回放汇总、直播封面 | 低频或人工更新 |
| `dynamic` | 礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物只读派生文件、翻牌应用 JSON、翻牌音视频 | 后台导出、上麦会话结束或翻牌批处理更新时变化 |

不作为常规同步项：

- `schedule_record/images/`：图片通过网站 `/image-proxy/` 访问。
- 完整原始房间消息、普通语音原文件、上麦原始 FLV、Cookie、Token、`.env`、`config/`、日志和缓存。
- 首页背景词、房间忽略、计分业务和记忆页是非 Git 版本化共享状态；腾讯云和阿里云均已启用统一提交、历史和 outbox。不得用普通 rsync 或 Git 覆盖这四个当前文件；腾讯云 outbox 如果短时保留待补发文件，应按共享状态工具排查，不要手工覆盖阿里云。
- 阿里云不是 `snh48-fan-hub` 的 Git checkout，不在阿里云生成 fan-hub 数据。

## 旧推送方案状态

腾讯云旧脚本仍保留为手动兜底：

```text
/home/snh48_web/deploy/sync-to-aliyun.sh
/home/snh48_web/deploy/sync-to-aliyun-if-changed.sh
/home/snh48_web/deploy/sync-to-aliyun-loop.sh
```

生产环境不应启用这些任务：

- 腾讯云 `crontab -l` 不应有未注释的 `sync-to-aliyun*` 任务。
- `/var/log/snh48/sync-to-aliyun.log` 不应持续更新。
- `ps` 不应长期出现 `sync-to-aliyun-loop.sh`、推送方向的 `rsync` 或连接阿里云 `8.210.188.184` 的同步进程。

2026-07-03 排查结论：

- 腾讯云 `sync-to-aliyun.sh` cron 已注释。
- 腾讯云没有发现 `sync-to-aliyun` 常驻进程。
- 旧推送日志最后更新时间停在 `2026-07-03 02:45:04 +0800`。
- 阿里云 `sync-from-tencent.log` 持续出现成功记录，说明新方案已经接管自动同步。

## 排查注意

- `source changed groups=dynamic, pulling...` 每分钟出现不一定异常。礼物回复、计分礼物、房间消息分片、语音转录、上麦发布包或翻牌应用数据等运行数据更新时，动态组源数据指纹会变化。
- `source changed groups=core,dynamic, pulling...` 如果长期每分钟出现，需要确认 `core` 组是否真的持续变化；否则检查状态文件是否被删除或无法写入。
- 稳定单向文件如 `chenjiayi_events.csv`、`schedule.csv`、`manual_events.csv` 应可以用 `sha256sum` 严格比对；四个可写共享状态改为核对 `_state.revision` 和 outbox，不能用普通 rsync 修复。
- 动态目录只能按同步日志、mtime 和 1 到 2 分钟延迟判断，不要要求瞬时 hash 完全一致。
- 修改同步目录、同步方向或云服务器 IP 时，必须同步更新 `doc/codex/project_profile.md`、`doc/daily_website_check.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`。
- 如果新增同步目标或更换阿里云 IP，需要提醒用户更新腾讯云登录风险白名单。
