# /home/snh48_web 后台运行与同步状态

更新日期：2026-07-20 CST +0800

腾讯云翻牌记录页发布专项复核：2026-07-20 04:18 CST +0800

腾讯云成员房间上麦回放发布专项复核：2026-07-17 16:13 CST +0800

阿里云成员房间上麦回放发布与同步专项复核：2026-07-19 04:51 CST +0800

本文件记录 `/home/snh48_web` 的长期运行方式和腾讯云到阿里云的数据同步口径。进程 PID 会随重启变化，排查时以文中的命令实时查询为准。

## 当前运行方式

| 环境 | 网站服务 | 监听 | 说明 |
|------|----------|------|------|
| 腾讯云 `cjy.plus` | screen 会话运行 `python -m website.main` | `127.0.0.1:8000`，公网由 Nginx 代理 | 翻牌记录页发布后 checkout `23d493a`；采样 screen `229664.snh48`、Python PID `229668`；本机验证 `/flip-cards` 为 200、未登录 `/api/flip-cards/status` 为 401、错误密码登录为 403、`/timeline` 为 200；公网验证 `https://cjy.plus/flip-cards` 为 200、未登录 status API 为 401、首页为 200、`/api/qa/status` 为 200；生产 `.env` 中 `OB_PASSWORD` 已设置，`FLIP_CARDS_PASSWORD` 未单独设置，本轮按回退规则复用 `OB_PASSWORD` |
| 阿里云香港 `cjy.我爱你` | systemd 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | checkout `3a7b05b`；PID `2899269`，enabled、active/running、`NRestarts=0`；`/room-voice-replays` 公网 200、未登录 sessions API 401、时光轴 200；尚未部署本次翻牌记录页和翻牌数据同步脚本变更，需用户确认腾讯云页面后再推进 |

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

> 2026-07-20 腾讯云已部署翻牌记录页代码 `23d493a`，但阿里云仍停在 `3a7b05b`，尚未加载 `flip_chat.html`、`flip_data/audio/`、`flip_data/video/` 的 dynamic 同步脚本变更，也未执行本次数据同步。等待用户确认腾讯云页面可用后，再部署阿里云并让阿里云主动拉取或手动拉取必要数据。

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
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 同路径 | 密码保护的上麦回放发布包；原始 FLV 不同步 |
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
