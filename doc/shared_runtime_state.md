# 双服务器版本化运行状态

本文说明腾讯云 `cjy.plus` 与阿里云 `cjy.我爱你` 之间需要即时一致的可写运行数据、可靠待处理箱和历史恢复方式。

## 一致性模型

- 两个域名都可接受用户或管理员操作，产品层面是“双向可写”。
- 腾讯云是唯一权威提交节点。腾讯云收到操作时直接提交；阿里云收到操作时通过现有 SSH 通道把“操作”转发给腾讯云。
- 腾讯云在文件锁内重新读取最新版本、应用操作、原子替换文件并生成新 revision，再把已提交版本复制到阿里云。这样不会让两台服务器各自修改整份文件后互相覆盖。
- 每个操作都有 `operation_id` 幂等回执。响应丢失后重试不会再次追加或再次执行。
- 对端暂时不可用时，本地成功提交不会回滚；待复制版本写入持久 outbox，由网站进程内后台线程每 60 秒重试。延迟到达的旧 revision 只补历史快照，不得回滚当前文件。
- 这套机制不使用 Git 保存运行数据，也不新增 systemd、screen、cron 或独立守护进程。

## 纳入复制的数据

| 资源 | 当前文件 | 网站操作 | 额外写入者 |
|------|----------|----------|------------|
| `scroller` | `website/data/scroller_texts.json` | 首页背景词管理 | 无 |
| `room_ignore` | `website/data/room_messages_ignored_batches.json` | 房间消息忽略/撤销 | 无 |
| `score_business` | fan-hub `score_gifts/live_business_fulfillments.json` | 直播计分礼物人工核实/修正 | 腾讯云 `score_gift_business_analyzer.py` |
| `memories` | `website/data/memories/memories.json` | 粉丝提交、应援会审核、本人确认 | `script/build_memories_seed.py` |

四个当前状态文件都只走版本化复制通道，不再由普通 `core` / `dynamic` rsync 覆盖。计分礼物目录中的 `score_gifts.json` 等只读派生文件仍按 `dynamic` 拉取，但明确排除 `live_business_fulfillments.json` 和 `.*.lock`；手动 `deploy.py sync-data` 也使用相同排除规则。这样旧文件不会在新 revision 到达后把副本回滚。

不纳入业务复制：`interaction_logs/`、`ip_clients.json`、`read_notifications.json`、`ip_daily_quota.json`、`balance_log.csv`、缓存、进程日志和 QA 任务内存状态。它们分别属于本节点观测、已读、限额、审计或临时状态，强行整目录双向覆盖会制造重复日志、错误已读状态或限额回滚。

## 历史版本

每次提交会把完整 JSON 以 gzip 不可变快照保存到：

```text
website/data/shared_state_history/<resource>/snapshots/<revision>.json.gz
website/data/shared_state_history/<resource>/operations/<operation_id>.json
```

完整压缩快照比文本 diff 占用略多，但可以独立校验 SHA-256 并直接恢复，不依赖一长串差异文件。历史目录不由 Git 跟踪，也不会被普通 `core` / `dynamic` rsync 删除；迁移和备份时必须保留。

常用命令只输出版本元数据，不输出状态正文：

```bash
cd /home/snh48_web
/home/snh48_web/venv/bin/python script/shared_state_history.py list scroller --limit 20
/home/snh48_web/venv/bin/python script/shared_state_history.py list room_ignore --limit 20
/home/snh48_web/venv/bin/python script/shared_state_history.py list score_business --limit 20
/home/snh48_web/venv/bin/python script/shared_state_history.py list memories --limit 20
```

恢复必须在腾讯云权威节点执行。恢复本身会生成一个新的 revision，因此恢复前后的历史都保留：

```bash
/home/snh48_web/venv/bin/python script/shared_state_history.py restore scroller <revision>
```

## 可靠待处理箱

投诉和 QA 邮箱请求采用一事件一文件，而不是同步会并发追加的 JSONL：

```text
website/data/action_inbox/events/<event_id>.json
```

- 请求事件写入后不可修改，事件 ID 幂等；处理状态也是新的不可变 `status_update` 事件。
- 每条请求记录 `origin_node` 和 `origin_label`。`/ob` 的“可靠待处理箱”用不同颜色明确显示“腾讯云 cjy.plus”或“阿里云 cjy.我爱你”。
- 任一服务器收到请求或状态事件后立即复制到对端；失败时进入 `website/data/shared_state_outbox/inbox/` 重试。
- `website/data/complaints/` 与会话目录中的邮箱 Markdown/JSONL 继续作为本节点兼容日志，但不再是跨服务器权威待办。
- 待处理箱含邮箱、投诉正文等个人信息，目录文件权限为 `0600`，不得提交 Git、放入静态目录或在诊断输出中打印正文。

导入两台服务器既有记录时分别运行；命令只打印数量：

```bash
/home/snh48_web/venv/bin/python script/migrate_action_inbox.py
/home/snh48_web/venv/bin/python script/migrate_action_inbox.py --apply
```

## 环境配置

腾讯云：

```ini
SHARED_STATE_SYNC_ENABLED=true
SHARED_STATE_NODE_ID=tencent
SHARED_STATE_IS_PRIMARY=true
SHARED_STATE_PEER=root@8.210.188.184
```

阿里云：

```ini
SHARED_STATE_SYNC_ENABLED=true
SHARED_STATE_NODE_ID=aliyun
SHARED_STATE_IS_PRIMARY=false
SHARED_STATE_PEER=root@124.222.72.203
```

两端还要保持 `SHARED_STATE_REMOTE_ROOT=/home/snh48_web` 和正确的虚拟环境 Python 路径。旧 `ROOM_MESSAGES_IGNORE_DIRECT_*` 只作为本次滚动迁移的配置兼容回退，新部署应显式配置 `SHARED_STATE_*`。

## 首次迁移与巡检

首次只在腾讯云创建四个基线 revision：

```bash
/home/snh48_web/venv/bin/python script/shared_state_history.py baseline all
```

巡检积压和当前 revision：

```bash
find website/data/shared_state_outbox -type f -name '*.json' -printf '%p\n' 2>/dev/null
/home/snh48_web/venv/bin/python script/shared_state_history.py list memories --limit 1
/home/snh48_web/venv/bin/python script/shared_state_history.py list score_business --limit 1
```

正常情况下 outbox 很快清空。对端故障时保留积压文件，修复 SSH 或对端服务代码后等待后台线程重试；不要删除 outbox，也不要用旧副本覆盖腾讯云当前文件。
