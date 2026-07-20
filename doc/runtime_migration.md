# 非 Git 运行数据迁移清单

本文件用于把当前腾讯云 `/home/snh48_web` 部署迁移到新服务器时，核对 Git 代码之外还需要保留的文件和目录。代码仍以 GitHub 为准；本清单只覆盖不会通过 Git 自动同步的运行数据、配置和运维状态。

## 迁移原则

- 先用 Git 部署代码，再补齐本清单里的运行数据和配置。
- `.env`、证书、Cookie、Token、SSH key、云控制台白名单不进入 Git，只能在服务器之间安全迁移或重新配置。
- 迁移前先给新旧服务器各做一次只读备份；不要用空目录覆盖已有运行数据。
- 从腾讯云迁移到新服务器后，如果新服务器需要从腾讯云或其他源拉取数据，必须同步更新腾讯云主机安全登录白名单；停用旧阿里云时删除旧 IP `8.210.188.184` 白名单。

## 网站仓库内运行数据

| 路径 | 是否必须迁移 | 用途 | 同步/恢复方式 |
|------|--------------|------|---------------|
| `/home/snh48_web/.env` | 必须 | 生产密码、API key、监听、安全和数据路径配置 | 手动安全迁移，按 `.env.example` 补齐；不要输出明文 |
| `/home/snh48_web/deploy/targets.local.json` | 需要时迁移 | 部署目标本地覆盖配置 | 手动迁移；不存在时按部署目标重新生成 |
| `/home/snh48_web/website/data/manual_events.csv` | 必须 | 时光轴手动事件运行数据 | 腾讯云为源；阿里云由 `sync-from-tencent.sh core` 拉取；新服务器迁移时直接复制 |
| `/home/snh48_web/website/data/memories/memories.json` | 必须 | 记忆页运行数据 | 腾讯云为源；阿里云由 `sync-from-tencent.sh core` 拉取；新服务器迁移时直接复制 |
| `/home/snh48_web/website/data/room_messages_ignored_batches.json` | 必须 | 房间消息页“忽略未回礼物批次”状态 | 不由 Git 跟踪；两台线上服务器通过 `ROOM_MESSAGES_IGNORE_DIRECT_*` 直连同步；迁移前分别备份两端并以 `updated_at` 较新的文件为准 |
| `/home/snh48_web/website/data/scroller_texts.json` | 必须 | 首页背景词内容 | 当前由 Git 跟踪；迁移时仍建议核对线上文件是否有未提交修改 |
| `/home/snh48_web/website/data/balance_log.csv` | 可选 | DeepSeek 余额查询历史 | 需要保留审计历史时复制；丢失不影响网站运行 |
| `/home/snh48_web/website/data/ip_clients.json` | 可选 | IP 到匿名客户端 ID 的后台观察映射 | 需要保留观察页连续性时复制；丢失后会重新生成 |
| `/home/snh48_web/website/data/ip_daily_quota.json` | 可选 | AI 问答每日 IP 配额计数 | 需要保持当天限额状态时复制；丢失后当天计数重置 |
| `/home/snh48_web/website/data/interaction_logs/` | 可选 | 用户行为日志和通知中心归档 | 需要保留运营记录时复制 |
| `/home/snh48_web/website/data/complaints/` | 可选 | 用户反馈/投诉记录 | 建议迁移，除非明确放弃历史记录 |
| `/home/snh48_web/nohup.out` | 不迁移 | 旧启动残留日志 | 可忽略 |

## fan-hub 数据依赖

网站运行依赖 `/home/snh48-fan-hub` 的生成数据。完整迁移腾讯云数据源服务器时，应优先按 `snh48-fan-hub` 工程自己的文档迁移；只迁移网站所需最小数据副本时，至少保留：

| 路径 | 用途 | 阿里云当前来源 |
|------|------|----------------|
| `/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv` | 时光轴事件/行程主文件 | `sync-from-tencent.sh core` |
| `/home/snh48-fan-hub/schedule_record/schedule.csv` | 行程兼容副本 | `sync-from-tencent.sh core` |
| `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/` | 直播回放汇总 | `sync-from-tencent.sh core` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 直播封面 | `sync-from-tencent.sh core` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 礼物回复页派生小数据 | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/` | 房间消息页分片数据 | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 房间语音转录文本 | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 密码保护的成员房间上麦回放发布包；包含兼容版/原始音质版 M4A、元数据和同期消息，不含原始 FLV | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 计分礼物页派生小数据 | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/flip_chat.html` | 密码保护的翻牌记录 HTML | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/flip_data/audio/`、`/home/snh48-fan-hub/flip_data/video/` | 翻牌页本地音视频依赖；不含 `flip_data/metadata/` | `sync-from-tencent.sh dynamic` |

如果新服务器要接替腾讯云成为数据生成源，还必须迁移 fan-hub 的代码、虚拟环境、采集配置、Cookie/Token、systemd/cron/screen 任务和历史原始数据；这些不属于网站仓库，不要从 `/home/snh48_web` 覆盖。

## 服务与系统配置

| 项 | 腾讯云当前口径 | 迁移注意 |
|----|----------------|----------|
| 网站服务 | screen 会话运行 `python -m website.main` | 可改为 systemd，但要保持 `HOST=127.0.0.1` 由 Nginx 代理 |
| Nginx | `/etc/nginx/conf.d/snh48.conf`，仓库来源 `deploy/nginx.conf` | 迁移后运行 `nginx -t`；证书和域名按新服务器重配 |
| HTTPS 证书 | 系统证书目录 | 不在 Git；迁移或重新签发 |
| 阿里云拉取 cron | 阿里云 root crontab 每分钟运行 `deploy/sync-from-tencent-if-changed.sh` | 新目标如果继续拉取腾讯云，更新 `TENCENT`、SSH key、白名单和文档 |
| 日志 | `/var/log/snh48/`、`kb_qa.log`、各类 screen/systemd 日志 | 只在需要保留排障历史时迁移 |

## 迁移后核对

1. `python3 deploy/deploy.py check-env <target>` 确认必要环境变量存在。
2. `python3 -m compileall -q website` 确认代码可导入。
3. `curl -sS -D - -o /dev/null https://新域名/`、`/timeline`、`/gift-replies`、`/room-messages`、`/room-voice-replays`、`/flip-cards`、`/score-gifts`、`/memories`。
4. 核对 `manual_events.csv`、`memories.json` 和 `room_messages_ignored_batches.json` 在新服务器存在且不是空文件覆盖。
5. 如果新服务器接替阿里云公开站，确认数据拉取 cron、日志和腾讯云白名单都已更新。
