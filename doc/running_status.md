# /home/snh48_web 后台运行与同步状态

更新日期：2026-07-20 CST +0800

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
| 腾讯云 `cjy.plus` | screen 会话运行 `python -m website.main` | `127.0.0.1:8000`，公网由 Nginx 代理 | 房间电台双版本与跳转体验提交 `2264e89` 已部署；采样 screen `452859.snh48`、Python PID `452864`，继续使用已验证的 `QA_WARMUP_ON_STARTUP=false` 临时运行覆盖；`/radio` 公网 200，页面已包含原始音质切换、加载/跳转状态和整行消息跳转，未登录 sessions API 为 401；鉴权后的会话详情为 schema v2、默认 `compatible`，兼容版/原始版各自 Range 请求均返回 206；此前计分礼物和翻牌功能仍包含在当前提交中 |
| 阿里云香港 `cjy.我爱你` | systemd 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | 房间电台双版本与跳转体验提交 `2264e89` 已部署；2026-07-20 16:18:04 CST 启动，PID `3021633`，enabled、active/running、`NRestarts=0`；`/radio` 公网 200，页面已包含原始音质切换、加载/跳转状态和整行消息跳转，未登录 sessions API 为 401；鉴权后的会话详情包含 315 条消息和 `compatible/original`，两种音频经公网 Nginx 的 Range 请求均为 206；此前计分礼物和翻牌功能仍包含在当前提交中；远端未跟踪的 `website/data/runtime_backups/` 与 `website/static/js/timeline.js.bak` 保持原样 |

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
| `/home/snh48_web/website/data/memories/memories.json` | 同路径 | 记忆页运行数据，腾讯云为写入源 |
| `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/` | 同路径 | 直播回放汇总 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 同路径 | 直播封面 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 同路径 | 礼物回复派生小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/` | 同路径 | 房间消息分片小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 同路径 | 语音转录文本数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 同路径 | 密码保护的上麦回放发布包；包含兼容版/原始音质版派生 M4A、元数据和同期消息，原始 FLV 不同步 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 同路径 | 计分礼物派生小数据 |

同步分组：

| 分组 | 内容 | 典型频率 |
|------|------|----------|
| `core` | 事件/行程 CSV、手动事件 CSV、记忆页运行数据、直播回放汇总、直播封面 | 低频或人工更新 |
| `dynamic` | 礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物 | 后台导出或上麦会话结束时更新 |

不作为常规同步项：

- `schedule_record/images/`：图片通过网站 `/image-proxy/` 访问。
- 完整原始房间消息、普通语音原文件、上麦原始 FLV、Cookie、Token、`.env`、`config/`、日志和缓存。
- 房间消息忽略状态 `website/data/room_messages_ignored_batches.json`：这是网站运行数据，不由 Git 跟踪，也不进入 `core` / `dynamic` 单向拉取；两台网站服务器通过 `ROOM_MESSAGES_IGNORE_DIRECT_*` 直连同步。
- 记忆页 `memories.json` 进入 `core` 单向拉取。生产上建议腾讯云开放写入、阿里云只作为副本展示；如果阿里云也开放提交，需要先设计双向合并或统一写入 API。
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

- `source changed groups=dynamic, pulling...` 每分钟出现不一定异常。礼物回复、计分礼物、房间消息分片、语音转录等运行数据持续写入时，动态组源数据指纹会持续变化。
- `source changed groups=core,dynamic, pulling...` 如果长期每分钟出现，需要确认 `core` 组是否真的持续变化；否则检查状态文件是否被删除或无法写入。
- 稳定小文件如 `chenjiayi_events.csv`、`schedule.csv`、`manual_events.csv`、`memories.json` 应可以用 `sha256sum` 严格比对。
- 动态目录只能按同步日志、mtime 和 1 到 2 分钟延迟判断，不要要求瞬时 hash 完全一致。
- 修改同步目录、同步方向或云服务器 IP 时，必须同步更新 `doc/codex/project_profile.md`、`doc/daily_website_check.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`。
- 如果新增同步目标或更换阿里云 IP，需要提醒用户更新腾讯云登录风险白名单。
