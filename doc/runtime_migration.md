# 非 Git 运行数据迁移清单

本文件用于把当前腾讯云 `/home/snh48_web` 部署迁移到新服务器时，核对 Git 代码之外还需要保留的文件和目录。代码仍以 GitHub 为准；本清单只覆盖不会通过 Git 自动同步的运行数据、配置和运维状态。

## 迁移原则

- 先用 Git 部署代码，再补齐本清单里的运行数据和配置。
- `.env`、证书、Cookie、Token、SSH key、云控制台白名单不进入 Git，只能在服务器之间安全迁移或重新配置。
- 迁移前先给新旧服务器各做一次只读备份；不要用空目录覆盖已有运行数据。
- 从腾讯云迁移到新服务器后，如果新服务器需要从腾讯云或其他源拉取数据，必须同步更新腾讯云主机安全登录白名单；停用旧阿里云时删除旧 IP `8.210.188.184` 白名单。

## 三项迁移约定（可直接核对）

### 1. 需要迁移的六类内容

1. **代码与可复现部署材料**：Git 提交、Python 依赖、systemd unit、Nginx 配置模板、部署脚本和 DNS/证书配置说明。代码通过 GitHub 部署，密钥和证书不进 Git。
2. **网站依赖的只读数据副本**：fan-hub 生成的事件/行程 CSV、直播回放、封面、房间消息分片、礼物/语音派生数据、翻牌发布包等。按 `core` / `dynamic` 分组同步，不能拿空目录或旧副本覆盖新数据。
3. **四类版本化共享状态当前值**：首页背景词 `scroller`、房间忽略 `room_ignore`、计分礼物业务核实 `score_business`、记忆页 `memories`。迁移时以腾讯云当前 revision 为准，不按文件修改时间猜主从。
4. **共享状态的历史、待发送项和待处理事件**：`shared_state_history/`、`shared_state_outbox/`、`action_inbox/` 必须保留完整目录和事件并集；同一事件 ID 的内容必须一致，禁止 `rsync --delete` 整目录覆盖。
5. **秘密和系统外部状态**：生产 `.env`、Cookie/Token、SSH key、云安全组和登录白名单、HTTPS 证书、DNS、Nginx 实际配置、systemd/timer/cron。逐项重新配置并验收，不把明文写进文档或 Git。
6. **观测与回滚材料**：Nginx 访问/错误日志、systemd journal、sysstat 资源采样、备份清单和旧服务器保留窗口。这些不参与业务复制，但迁移前后用于判断容量、排障和回滚。

### 1.1 两种迁移场景的边界

上面的六类是总清单，但实际迁移对象不同，不能把两台机器当成同一种服务器：

| 场景 | 必须迁移/重建 | 明确不迁移 |
|------|---------------|------------|
| **A. 腾讯云非公开站/数据生成主机迁移** | `/home/snh48_web` 网站代码和运行状态；`/home/snh48-fan-hub` 全量代码、虚拟环境、采集配置、Cookie/Token、systemd/cron/screen、原始数据；COS 接入、网站与数据生成任务；新主机继续作为唯一权威 `SHARED_STATE_IS_PRIMARY=true` | 不从阿里云公开副本反向覆盖 fan-hub；不把完整原始采集数据、Cookie/Token 或采集服务搬到阿里云 |
| **B. 阿里云公开站迁移** | 网站代码和 venv；`core` / `dynamic` 最小 fan-hub 副本；四类共享状态当前值、历史、outbox、action inbox 事件并集；HTTPS/Nginx；`SHARED_STATE_NODE_ID`、peer SSH key；阿里云主动拉取 cron；QA 依照目标节点配置 | 不运行 fan-hub 采集器、社交 Cookie、口袋48 Token、完整原始数据或大媒体；不设置 `SHARED_STATE_IS_PRIMARY=true`；不把新公开站当作数据生成源 |

因此，本文中“网站运行数据”和“观测/回滚材料”适用于两种场景；“fan-hub 全量数据生成环境”只属于场景 A，“网站必要最小副本和主动拉取 cron”只属于场景 B。迁移公开站时，不需要把腾讯云的采集任务、敏感凭据或完整原始数据复制过去。

### 2. 推荐的安全迁移顺序

1. 提前降低 DNS TTL，记录旧服务器当前提交、共享状态 revision、outbox 数量和磁盘/日志快照。
2. 创建新主机并先完成 SSH、非 root 服务账号、文件权限、Nginx、证书和防火墙基线；从 GitHub 部署代码和依赖。
3. 安全写入新服务器 `.env`，核对 `NODE_ID`、共享状态路径、SSH peer、Cookie/Token 和 `QA_ENABLED` 等节点差异；不要复制旧 `.env` 后不审查。
4. 停止新服务器的采集/生成 cron（如果它只是网站副本），先以只读方式同步 `core` / `dynamic` 数据、四类当前状态、历史、outbox 和 action inbox。新机器不能自行成为第二个主节点。
5. 在旧公开站设置 `SITE_MAINTENANCE_MODE=true`，让页面和查询继续服务，但所有共享状态写入、可靠待处理箱新增事件和处理状态更新返回 `503`；等待旧站请求排空。
6. 处理腾讯云 outbox 并确认两端四类 revision、历史链、outbox 和 inbox 事件并集一致。新站先以副本身份启动，完成本机和公网只读烟测。
7. 更新腾讯云 `SHARED_STATE_PEER`、新服务器 SSH 公钥/强制命令和云安全组白名单；验证新站能接收复制，且没有旧的双向 cron 或第二个权威写入者。
8. 切换 DNS，观察新站访问日志、服务状态和 outbox。至少保留旧服务器 48--72 小时，不删除数据、不撤销回滚所需的密钥。
9. 确认 DNS 缓存和旧站访问量降为零后，关闭旧站、删除旧 IP 白名单和旧 peer 授权，再按保留策略归档旧日志和备份。

> 当前模型仍是“腾讯云唯一权威提交、另一台操作转发”。因此迁移切换期间必须先冻结旧站写入；不能让新旧两台同时各自改同一份当前文件。

### 3. 迁移前建议补的两个小功能

- **节点显示名配置**：`SHARED_STATE_NODE_LABEL` 可覆盖本机名称，`SHARED_STATE_NODE_LABELS_JSON` 可补充多个节点名称。`NODE_ID` 仍是稳定机器身份，显示名只用于 `/ob` 和待处理箱，迁移到新域名时不必改代码。
- **业务写入维护模式**：设置 `SITE_MAINTENANCE_MODE=true` 后，读取页面、GET 查询和访问追踪仍可用；会改变共享状态或写入可靠待处理箱的业务接口统一返回 `503`，并附 `Retry-After`。切换完成后将其恢复为 `false` 并重启对应网站服务。

## “修改共享状态或产生待办”具体指什么

维护模式的拦截范围是会造成跨服务器数据变化、而且迁移时容易丢失的业务写入，不是所有 HTTP `POST` 都会被禁止：

| 类别 | 接口 | 会写入的内容 |
|------|------|--------------|
| 共享状态 | `PUT /api/scroller/texts` | 首页背景词当前值、revision、历史和 outbox |
| 共享状态 | `POST /api/room-messages/ignore-latest-batch`、`/undo-ignore` | 房间消息忽略状态、revision、历史和 outbox |
| 共享状态 | `POST /api/score-gifts/business-review` | 计分礼物业务核实状态、revision、历史和 outbox |
| 共享状态 | `POST /api/memories/submit`、`/review` | 记忆页提交/审核状态、revision、历史和 outbox |
| 可靠待办 | `POST /api/complaint/submit` | 投诉事件和本地兼容日志 |
| 可靠待办 | `POST /api/qa/archive-email` | 邮箱请求事件、通知和本地归档 |
| 可靠待办 | `POST /api/feedback-chat/message`、`/reply` | 客服聊天请求/回复事件 |
| 可靠待办 | `POST /api/ob/inbox/status` | 待处理事件的不可变处理状态事件 |

页面 GET、静态资源、访问追踪、管理员登录/退出 Cookie、`/api/ob/mark-read` 的本节点已读状态，以及 QA 的临时问答任务不属于上述跨服务器权威写入，所以维护模式不会拦截它们。社交凭据和翻牌账号管理是节点本地的敏感操作，不进入这套共享状态通道；迁移窗口若要完全冻结它们，应同时停用相应管理员操作或服务。

## 现有访问与资源记录（截至 2026-09-03）

- 两台服务器均保留 Nginx 原始访问日志并按日轮转。**在本次规则部署前**可见的专用站点日志约为：腾讯云 `2026-08-24` 至 `2026-09-03`（约 3,700 个请求），阿里云 `2026-08-20` 至 `2026-09-03`（约 32,800 个请求）；旧规则通常只保留约 10--14 份轮转文件，因此这不是“自首次部署以来”的完整历史。新规则已取消按份数删除，后续由“超过 1 GiB 且 COS 归档校验成功后才删除”的任务控制。这里的请求数包含静态资源、爬虫和 4xx/5xx，不能直接当作 PV/UV；旧日志没有现成的跨域 PV/UV 报表。
- 腾讯云已启用 sysstat 定时采样，`/var/log/sa/sa01`、`sa02`、`sa03` 等文件可回看 CPU、内存、I/O 和负载。近期平均 CPU idle 约 55--64%，内存使用率约 48--51%；当前根分区约 85%（50G 中可用约 7.6G），需要优先关注磁盘增长和日志/缓存清理。
- 阿里云当前为 4 vCPU、约 7.1GiB 内存、根分区约 47% 使用率（约 36G 可用），但未发现已启用的 `/var/log/sa` 历史采样；只能依靠当前快照、Nginx 日志和 systemd journal 做近期判断。
- `website/data/interaction_logs/`、OB 访问记录和 systemd journal 也会保留应用层/访客观测信息，但它们不是按天汇总的容量数据。历史数据仍不足以覆盖部署全周期；从本版本开始，两台机器分别写入统一格式的长期统计，避免以后再次只能做粗略判断。

## 访问统计、资源统计与日志保留策略

从本版本开始，两台网站节点分别运行 `snh48-website-metrics.timer`，每 5 分钟写入 root-only 的 `/var/lib/snh48-web/metrics/<node_id>/`：

- `snapshots.jsonl`：每次采样的 CPU 使用率（相邻采样差值）、1/5/15 分钟负载、内存/Swap、根盘容量和磁盘 I/O 计数/增量；
- `daily.json`：按日期聚合的专用站点请求数、页面请求数、响应字节、状态码和匿名访客数；只保存聚合数字，不保存 IP、User-Agent、请求正文或路径明细；
- `latest.json`：最近一次快照；`collector_state.json`：轮转日志增量读取位置和 CPU/I/O 基线。

腾讯云节点使用 `/var/log/nginx/snh48_access.log*`，阿里云节点使用 `/var/log/nginx/snh48_aliyun_access.log*`；两者分别写入 `metrics/tencent` 和 `metrics/aliyun`，不能合并为一个容量口径。统计文件本身不参与双向业务同步，迁移时作为第六类观测材料按需备份。

两台机器的 Nginx `/var/log/nginx/*.log` 继续每日轮转和压缩，但仓库规则把 `rotate` 提高到 `100000`，因此普通 logrotate 不再按 10/14 份删除。`snh48-website-log-archive.timer` 每天检查所有 Nginx 日志的总大小：未超过 **1 GiB** 时只记录状态；超过阈值时只选择最旧的已轮转文件，先制作含逐文件 SHA-256 清单的压缩归档，上传 COS 并校验远端对象大小，再复核文件 inode/大小/mtime 未变化，最后才删除已归档文件。

归档任务遵循 fail-closed：COS rclone 配置/凭据缺失、上传失败、远端校验失败或日志在归档期间发生变化，均不删除任何文件并以失败状态留在 systemd journal。腾讯云可复用 `/home/snh48-fan-hub/config/` 中已有私有 COS 接入；阿里云不复制该凭据，默认只保留日志并在达到阈值时报警，待配置受限的跨云归档通道后才允许清理。这样“没有备份就不会删除”优先于磁盘自动释放。

该策略针对网站 Nginx 访问/错误日志；systemd journal 和系统审计日志仍由系统 journald/logrotate 自己管理，不会被网站归档任务直接 vacuum。它们的占用会进入资源快照，若要改变 journald 的保留期，必须另开主机日志归档专项并先备份验证。

## 网站仓库内运行数据

| 路径 | 是否必须迁移 | 用途 | 同步/恢复方式 |
|------|--------------|------|---------------|
| `/home/snh48_web/.env` | 必须 | 生产密码、API key、监听、安全和数据路径配置 | 手动安全迁移，按 `.env.example` 补齐；不要输出明文 |
| `/home/snh48_web/deploy/targets.local.json` | 需要时迁移 | 部署目标本地覆盖配置 | 手动迁移；不存在时按部署目标重新生成 |
| `/home/snh48_web/website/data/memories/memories.json` | 必须 | 记忆页运行数据 | 非 Git 版本化共享状态；迁移时以腾讯云权威 revision 为当前值，普通 `core` 拉取不覆盖 |
| `/home/snh48_web/website/data/room_messages_ignored_batches.json` | 必须 | 房间消息页“忽略未回礼物批次”状态 | 非 Git 版本化共享状态；迁移时保留腾讯云权威 revision，不按 `updated_at` 猜测并互相覆盖 |
| `/home/snh48_web/website/data/scroller_texts.json` | 必须 | 首页背景词内容 | 非 Git 版本化共享状态；从腾讯云权威节点迁移 |
| `/home/snh48_web/website/data/shared_state_history/` | 必须 | 四类共享状态的不可变 gzip 历史和幂等回执 | 安全复制整个目录；不得只迁当前 JSON 后丢弃版本链 |
| `/home/snh48_web/website/data/shared_state_outbox/` | 必须 | 尚未复制到对端的持久待发送项 | 停服务后复制；恢复后让网站线程继续重试，不要删除积压 |
| `/home/snh48_web/website/data/action_inbox/` | 必须 | 投诉、邮箱请求和处理状态的双服务器可靠待处理箱 | 两端事件取并集；同 event ID 内容必须一致，不能整目录 `--delete` 覆盖 |
| `/home/snh48_web/website/data/balance_log.csv` | 可选 | DeepSeek 余额查询历史 | 需要保留审计历史时复制；丢失不影响网站运行 |
| `/home/snh48_web/website/data/ip_clients.json` | 可选 | IP 到匿名客户端 ID 的后台观察映射 | 需要保留观察页连续性时复制；丢失后会重新生成 |
| `/home/snh48_web/website/data/ip_daily_quota.json` | 可选 | AI 问答每日 IP 配额计数 | 需要保持当天限额状态时复制；丢失后当天计数重置 |
| `/home/snh48_web/website/data/interaction_logs/` | 可选 | 用户行为日志和通知中心归档 | 需要保留运营记录时复制 |
| `/home/snh48_web/website/data/complaints/` | 可选 | 本节点投诉兼容日志 | 权威待办已在 `action_inbox/`；需保留旧人类可读历史时迁移 |
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
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 计分礼物页派生小数据；其中 `live_business_fulfillments.json` 是版本化共享状态 | 其他文件由 `sync-from-tencent.sh dynamic` 拉取；可写业务状态和锁文件明确排除 |
| `/home/snh48-fan-hub/flip_data/web/flip_cards.json` | 密码保护的翻牌记录应用数据 | `sync-from-tencent.sh dynamic` |
| `/home/snh48-fan-hub/flip_data/audio/`、`/home/snh48-fan-hub/flip_data/video/` | 翻牌页本地音视频依赖；不含 `flip_data/metadata/` | `sync-from-tencent.sh dynamic` |

上述阿里云只读副本由 root 同步，但必须以 `root:snh48-web`、目录 `0750`、文件 `0640` 落盘。`deploy/sync-from-tencent.sh` 和手动兜底 `deploy/sync-to-aliyun.sh` 已在每个 rsync 接收操作中固化该规则；迁移时不得只运行一次 ACL 后继续使用会恢复源端 `root:root` 权限的旧同步脚本。

如果新服务器要接替腾讯云成为数据生成源，还必须迁移 fan-hub 的代码、虚拟环境、采集配置、Cookie/Token、systemd/cron/screen 任务和历史原始数据；这些不属于网站仓库，不要从 `/home/snh48_web` 覆盖。

## 服务与系统配置

| 项 | 腾讯云当前口径 | 迁移注意 |
|----|----------------|----------|
| 网站服务 | `snh48-web.service` 以不可登录 `snh48-web` 账号运行；公开副本使用 `snh48-aliyun.service` | 从仓库安装对应 unit 和权限脚本，保持 `HOST=127.0.0.1`、`UMask=0077` 和 systemd 沙箱，不恢复 root/screen/nohup 生产方式 |
| Nginx | `/etc/nginx/conf.d/snh48.conf`，仓库来源 `deploy/nginx.conf` | 迁移后运行 `nginx -t`；证书和域名按新服务器重配 |
| HTTPS 证书 | 系统证书目录 | 不在 Git；迁移或重新签发 |
| 阿里云拉取 cron | 阿里云 root crontab 每分钟运行 `deploy/sync-from-tencent-if-changed.sh` | 新目标如果继续拉取腾讯云，更新 `TENCENT`、SSH key、白名单和文档 |
| 跨云回放监控 Token | 阿里云网站 `.env` 与腾讯云 `/etc/snh48/room-voice-cross-cloud-health.env` 各保存同一高熵值 | 使用 `deploy/set_env_secret.py` 从 stdin 写入；保持 root `0600`，不输出、不进 Git；不能用页面密码替代长期监控 Token |
| 日志 | `/var/log/snh48/`、`kb_qa.log` 和各 systemd journal | 只在需要保留排障历史时迁移；不恢复旧 screen/nohup 启动方式 |

## 迁移后核对

1. `python3 deploy/deploy.py check-env <target>` 确认必要环境变量存在。
2. `python3 -m compileall -q website` 确认代码可导入。
3. `curl -sS -D - -o /dev/null https://新域名/`、`/timeline`、`/room/gifts`、`/room/gift-senders`、`/room-messages`、`/room-voice-replays`、`/flip-cards`、`/score-gifts`、`/memories`。
4. 核对统一事件/行程 CSV、四类当前共享状态、`shared_state_history/`、`shared_state_outbox/` 和 `action_inbox/` 存在且不是空目录覆盖。
5. 在新的腾讯云权威节点运行 `script/shared_state_history.py list <resource>`，确认当前 revision 可在历史中找到；在 `/ob` 核对待处理箱来源标签。
6. 如果新服务器接替阿里云公开站，确认数据拉取 cron、日志和腾讯云白名单都已更新。
7. 按 `doc/security/server_hardening_migration_runbook.md` 执行 SSH、非 root 服务、Nginx、跨云密钥和回滚核对；运行 `deploy/verify_server_security_baseline.sh`，再从独立网络验证公网不能直连 8000/8899。
