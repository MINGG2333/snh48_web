# 每日网站检查清单

本文件记录每天需要做的基础网站检查项。检查时按当前任务目标选择执行，不把某一次专项排查扩展成所有部署的固定验收。

HTTPS 证书不是每日必查项；阿里云已建立月度提醒机制，详见 `doc/ops/https_certificate_reminder.md`。处理 HTTPS、Nginx、证书或阿里云部署问题时，应额外检查 `certbot.timer`、月度提醒 cron 和 `/var/log/snh48/https-cert-reminder.log`。

## 1. 腾讯云到阿里云必要数据同步

目的：确认阿里云正在主动从腾讯云拉取网站必要运行数据，并确认旧的腾讯云主动推送任务没有恢复。

当前方案：

- 自动任务运行在阿里云香港服务器 `/home/snh48_web`。
- 阿里云 root cron 每分钟执行 `deploy/sync-from-tencent-if-changed.sh`。
- 脚本先通过 SSH 分别检查腾讯云 `core` 和 `dynamic` 两组源数据指纹；只有某组指纹变化时才调用 `deploy/sync-from-tencent.sh` 拉取对应分组。
- 四个可写业务状态不进入这两组；计分目录指纹和 rsync 都排除 `live_business_fulfillments.json`、`.*.lock`。
- 上麦回放目录先同步 session、消息和音频，再原子提交 `manifest.json`，最后清理旧文件；同步中途旧 manifest 仍保持可播放。
- 腾讯云侧 `sync-to-aliyun.sh`、`sync-to-aliyun-if-changed.sh`、`sync-to-aliyun-loop.sh` 只作为手动兜底，不应放回生产 cron。

### 阿里云检查命令

执行环境：阿里云香港服务器 `/home/snh48_web`，通常使用 `root` 用户。

```bash
cd /home/snh48_web

# 1. 确认当前服务器时间，便于判断最近一次同步是否足够新
date '+%Y-%m-%d %H:%M:%S %Z %z'

# 2. 确认阿里云 cron 正在每分钟运行主动拉取检查
crontab -l | grep 'sync-from-tencent-if-changed'

# 3. 查看最近同步日志
tail -n 80 /var/log/snh48/sync-from-tencent.log

# 4. 确认没有卡住的同步进程；同步执行瞬间可能短暂出现 bash、ssh、rsync
pgrep -af 'sync-from-tencent|sync-to-aliyun|rsync|124.222.72.203' || true

# 5. 比对稳定小文件。动态导出文件可能有 1 到 2 分钟延迟，不适合做严格瞬时 hash 判断
sha256sum /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv
ssh -o BatchMode=yes -o ConnectTimeout=8 root@124.222.72.203 \
  "sha256sum /home/snh48-fan-hub/schedule_record/chenjiayi_events.csv"

sha256sum /home/snh48-fan-hub/schedule_record/schedule.csv
ssh -o BatchMode=yes -o ConnectTimeout=8 root@124.222.72.203 \
  "sha256sum /home/snh48-fan-hub/schedule_record/schedule.csv"

sha256sum /home/snh48_web/website/data/manual_events.csv
ssh -o BatchMode=yes -o ConnectTimeout=8 root@124.222.72.203 \
  "sha256sum /home/snh48_web/website/data/manual_events.csv"

# 6. 可选：确认阿里云网站接口能读取行程和手动事件数据
curl -sS --connect-timeout 8 -D - -o /tmp/aliyun_schedule.json https://cjy.xn--6qq986b3xl/api/timeline/schedule
wc -c /tmp/aliyun_schedule.json
curl -sS --connect-timeout 8 -D - -o /tmp/aliyun_manual_events.json https://cjy.xn--6qq986b3xl/api/timeline/manual-events
wc -c /tmp/aliyun_manual_events.json
```

### 腾讯云反向检查命令

执行环境：腾讯云服务器 `/home/snh48_web`。

```bash
cd /home/snh48_web

# 1. 腾讯云生产 cron 不应恢复主动推送任务；注释行可以存在
crontab -l | grep -E 'sync-to-aliyun|sync-from-tencent' || true

# 2. 旧推送日志不应持续更新
stat -c '%y %s %n' /var/log/snh48/sync-to-aliyun.log 2>/dev/null || true
tail -n 20 /var/log/snh48/sync-to-aliyun.log 2>/dev/null || true

# 3. 确认当前没有腾讯云主动推送进程
pgrep -af 'sync-to-aliyun|rsync|8.210.188.184' || true
```

### 合格标准

- 阿里云 `crontab -l` 中存在这一行或等价配置：

```cron
* * * * * bash /home/snh48_web/deploy/sync-from-tencent-if-changed.sh >> /var/log/snh48/sync-from-tencent.log 2>&1
```

- `/var/log/snh48/sync-from-tencent.log` 最近 2 到 3 分钟内出现一次检查记录。
- 无变化时允许出现：

```text
[sync-from-tencent-if-changed][YYYY-MM-DD HH:MM:SS] no source changes, skipped
```

- 有变化时应出现一次完整成功记录：

```text
[sync-from-tencent-if-changed][YYYY-MM-DD HH:MM:SS] source changed groups=core,dynamic, pulling...
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] Starting sync groups=core,dynamic...
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] chenjiayi_events.csv done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] schedule.csv done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] manual_events.csv done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] live_push_replays done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] live_covers done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] gift_replies done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] messages_shards done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] audio_transcripts done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] score_gifts done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] room_voice_replays payload done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] room_voice_replays manifest committed
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] room_voice_replays obsolete payload cleaned
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] room_voice_replays done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] flip_chat.html done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] flip_data/audio done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] flip_data/video done
[sync-from-tencent][YYYY-MM-DD HH:MM:SS] All sync completed
[sync-from-tencent-if-changed][YYYY-MM-DD HH:MM:SS] state updated
```

- 腾讯云生产 cron 没有启用 `sync-to-aliyun-loop.sh`、`sync-to-aliyun-if-changed.sh` 或 `sync-to-aliyun.sh`；旧任务注释行可以保留。
- 腾讯云 `/var/log/snh48/sync-to-aliyun.log` 不再持续产生新记录。
- `chenjiayi_events.csv`、`schedule.csv`、`manual_events.csv` 两端 hash 一致；四个可写状态按下一节核对 revision，不用普通 rsync 日志作为一致性依据。
- 动态目录如 `gift_replies/`、`messages_shards/`、`audio_transcripts/`、`room_voice_replays/`、`score_gifts/`、`flip_chat.html`、`flip_data/audio/`、`flip_data/video/` 如果腾讯云正在生成新数据，阿里云允许有 1 到 2 分钟同步延迟。
- `room_voice_replays manifest committed` 只能出现在 `payload done` 之后；如果同步在提交 manifest 前失败，网站继续读取旧回放是预期的安全降级，下一分钟应重试。
- 只有动态小数据变化时，日志应优先显示 `groups=dynamic`；不应每次都同步 `live_covers` 和 `live_push_replays`。

### 异常判断

- 如果日志每分钟都是 `source changed groups=dynamic, pulling...`：先检查腾讯云动态导出目录最近 mtime。礼物回复、计分礼物、房间消息分片、语音转录持续更新，上麦录音会话正在发布/核对同期消息，或翻牌 HTML/音视频刚更新时，这是正常现象，不代表指纹判断失效。
- 如果动态数据变化却总是 `groups=core,dynamic`：检查 `core` 目录是否真的持续变化；如果没有，检查状态文件 `/tmp/snh48_sync_from_tencent.state.core` 是否被删除或无法写入。
- 如果反复出现 `previous check still running, skipped` 或 `previous sync still running, skipped`：检查 SSH 是否卡住、网络是否异常，以及 `/tmp/snh48_sync_from_tencent*.lock` 是否被长期持有。
- 如果阿里云日志出现 `Permission denied` 或 `Host key verification failed`：检查阿里云到腾讯云的 SSH 免密登录、known_hosts 和腾讯云登录白名单。
- 如果腾讯云旧推送日志继续更新：说明旧 cron、screen、systemd 或手动循环被恢复，应先停用旧任务，再保留阿里云主动拉取。
- 如果源文件已更新但阿里云文件长期落后：先保留阿里云现有数据，排查同步脚本和日志；不要删除或覆盖 `/home/snh48-fan-hub` 运行数据。
- 如果日志停在 `room_voice_replays payload done` 而没有 `manifest committed`：不要手工复制 manifest；先修复 SSH/rsync 后重跑 `bash deploy/sync-from-tencent.sh dynamic`，让脚本完成原子提交。
- 如果 `curl` 偶发 DNS 失败，但 SSH 文件比对和同步日志正常：重试 API 检查，优先以同步日志和两端文件时间戳判断同步链路。

### 手动恢复

优先在阿里云手动拉取：

```bash
cd /home/snh48_web
bash deploy/sync-from-tencent.sh
tail -n 40 /var/log/snh48/sync-from-tencent.log
```

也可以只拉取指定分组：

```bash
bash deploy/sync-from-tencent.sh core
bash deploy/sync-from-tencent.sh dynamic
```

只有确认阿里云主动拉取链路不可用，且用户明确同意临时兜底时，才在腾讯云手动执行：

```bash
cd /home/snh48_web
bash deploy/sync-to-aliyun.sh
```

不要把腾讯云手动兜底脚本重新加入生产 cron 或 15 秒常驻循环。

## 2. 双服务器版本化状态与可靠待处理箱

目的：确认两个域名的可写业务状态由腾讯云统一提交、复制积压可恢复，并且管理员能看到每条待办的来源服务器。

### 两端检查命令

```bash
cd /home/snh48_web

# 只显示本机角色和开关，不输出密码或请求正文
/home/snh48_web/venv/bin/python -c 'from website import config as c; print(c.SHARED_STATE_NODE_ID, c.SHARED_STATE_IS_PRIMARY, c.SHARED_STATE_SYNC_ENABLED, bool(c.SHARED_STATE_PEER))'

# 正常应为空；对端故障时允许暂时积压，但不能长期增长
find website/data/shared_state_outbox -type f -name '*.json' -printf '%p\n' 2>/dev/null

# 历史命令只输出元数据
/home/snh48_web/venv/bin/python script/shared_state_history.py list scroller --limit 1
/home/snh48_web/venv/bin/python script/shared_state_history.py list room_ignore --limit 1
/home/snh48_web/venv/bin/python script/shared_state_history.py list score_business --limit 1
/home/snh48_web/venv/bin/python script/shared_state_history.py list memories --limit 1

du -sh website/data/shared_state_history website/data/action_inbox website/data/shared_state_outbox 2>/dev/null
```

在浏览器登录 `/ob`，确认可靠待处理箱中的请求分别显示“来源：腾讯云 cjy.plus”或“来源：阿里云 cjy.我爱你”，并抽查一次状态更新后另一端能看到相同结果。不要在截图或聊天中暴露邮箱和投诉正文。

### 合格标准与恢复

- 腾讯云输出 `tencent True True True`；阿里云输出 `aliyun False True True`。
- 四类资源至少有一个当前 revision，当前 JSON 的 `_state.revision` 能在对应历史列表中找到。
- 正常网络下 outbox 为空；对端不可用期间产生的文件在恢复后逐步清空。
- 延迟到达旧版本不会改变当前 revision；不得手工用阿里云文件覆盖腾讯云。
- outbox 长期不清空时先验证双方 SSH 和 `script/shared_state_peer.py`，再查看网站启动日志；保留积压文件。需要补发当前权威版本时，在腾讯云运行：

```bash
/home/snh48_web/venv/bin/python script/shared_state_history.py replicate memories
```

- 历史恢复只在腾讯云运行 `script/shared_state_history.py restore ...`；恢复也会生成新 revision。完整说明见 `doc/shared_runtime_state.md`。
