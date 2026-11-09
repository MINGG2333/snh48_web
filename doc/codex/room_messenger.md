# 房间信使（个人号房间消息发送）

> 页面：`/room/messenger`（短入口 `/room-messenger`）
>
> 状态：仅腾讯云私密站 `cjy.plus` 启用；阿里云页面壳存在但功能禁用。
>
> 2026-11-09 新增。真实发送的端到端验收由 owner 手动完成，开发与自动测试不得向任何真实频道发送消息。

## 1. 目标与边界

- 允许 owner 在网页上用**个人口袋48账号**查看成员房间最近聊天并发送文本消息。
- 支持即时发送、单次定时、批量消息（可定义间隔和随机浮动）、每日重复批量。
- 支持删除当前账号自己发送的房间消息（口袋48 REST `/im/api/v1/team/msg/delete`）。
- 个人号 Token 失效时页面显示“重新登录”入口；同一手机号的大号/小号可在账号弹窗内切换。
- 左侧保留最近使用频道；成员目录可按姓名/口袋号/团体搜索，展开后选择公开房间或小房间。
- 桌面端三栏（频道 / 聊天 / 发送计划），移动端侧栏抽屉 + 底部输入 + 计划全屏抽屉。
- **不**使用账号池账号；**不**把该账号加入 `account_pool`；**不**让任何采集任务使用它。
- 页面只发送文本；图片、语音、礼物、翻牌等复杂消息不在本期范围。

## 2. 账号与凭据

- 登录方式：手机号 + 短信验证码（必要时口袋48安全验证），复用 fan-hub 既有短信/登录流程。
- 登录成功后由 `token_manager.upsert_account()` 写入 `config/accounts.json`，随后立即
  `token_manager.mark_personal(account_id)`：
  - 记录上带 `personal: true`；
  - 从 `default` / `default_fallbacks` 中摘除；
  - **不**调用 `auto_join_account_pool()`，不创建翻牌刷新任务。
- 如果该账号本来就在 `account_pool` 中，登录会明确失败并提示先从账号池移出，不会静默改动池。
- Token 只在 `config/accounts.json`（root 0600）中；网页进程不读取、不返回、不写日志。
- 网页通过本机 root 特权桥 `snh48-privileged-bridge-flip.service` 调用新增命令：
  - `messenger-status`：个人号清单（不含 Token/手机号）；
  - `messenger-probe`：验证个人号 Token，并返回同一手机号的大号/小号列表；
  - `messenger-switch`：在同一手机号的大号/小号之间切换，保存新 Token 并标记 personal；
  - `messenger-history`：读取房间最近消息；
  - `messenger-send`：一次 QChat 连接内发送 1–10 条文本；
  - `messenger-delete`：删除当前账号自己发送的消息。
- 登录命令 `send-sms` / `security-answer` / `verify-code` 沿用原桥；`verify-code` 新增
  `personal_only: true` 分支。没有新增 systemd 服务、socket 或可写目录。

## 3. 发送链路

```
浏览器
  |  HttpOnly Cookie（/api/room-messenger，60 分钟）
  v
FastAPI website/room_messenger_api.py
  |  本机 Unix Socket，固定命令 + JSON stdin
  v
snh48-privileged-bridge-flip.service (root)
  |  scripts/web/flip_account_admin.py
  |  scripts/web/room_messenger_ops.py
  v
config/accounts.json（读取个人号 Token）
  |  REST：/im/api/v1/im/userinfo、/user/api/v1/user/info/reload
  |  QChat：NIM CommonLink → QChat 24/10
  v
scripts/web/room_messenger_qchat.js
```

- QChat 发送采用 Pocket48 客户端同款流程：NIM 登录 → 请求 QChat 地址 → QChat 登录 →
  订阅频道（访客优先，失败回退成员）→ 服务 24 命令 10 发送文本。
- 一条任务批次在一个 Node 进程内复用连接，按间隔/浮动逐条发送；单批最多 10 条，避免频繁重连。
- 发送消息带 `QCHAT` ext（昵称、头像、等级等），避免消息在客户端显示成无来源文本。

## 4. 聊天记录

- 通过个人号 Token 调用 `POST /im/api/v1/team/message/list/all`，首次取最新 50 条，
  向上分页加载更早消息。
- 页面每 20 秒轮询最新一页并去重合并；只在距底部 120px 内自动滚动。
- 消息归一化为：`id/server_id/time/type/inner_type/sender_id/sender_name/text/
  reply_text/gift_name/gift_count/media_url/channel_id`。
- 媒体只显示可点击链接，不代理、不下载。

## 5. 定时与批量任务

任务保存在 `/var/lib/snh48-web/room_messenger/jobs.json`（0600），由网站进程内的
`room-messenger-scheduler` 守护线程执行：

- 单次定时：一条消息，指定开始时间。
- 批量：多行消息，间隔 ≥ `ROOM_MESSENGER_MIN_INTERVAL_SECONDS`（默认 1 秒），
  浮动 ±`jitter` 秒；默认不设业务批量上限（`ROOM_MESSENGER_MAX_BATCH_MESSAGES=0`），代码保留 5000 条技术请求上限。
- 每日批量：同一批消息每天在同一开始时间重复，直到取消。
- 跨批间隔：上一批最后一条发送后至少等待一个间隔再发下一批。
- 每日上限：默认不设（`ROOM_MESSENGER_DAILY_SEND_CAP=0`）；需要时再配置。
- 编辑：等待中或已暂停、且没有任何已发送/发送中/未知记录的任务，可修改消息、间隔、浮动、开始时间和每日重复；保存后回到等待中。已有发送记录的任务不允许改正文，避免错位。
- 失败/限流告警：任务失败、暂停或命中疑似限流（频繁/429/rate limit）时，页面顶部显示红色提醒；“发送计划”面板可开启浏览器通知。命中疑似限流时任务自动暂停，不继续发送后续消息。
- 发送记录筛选：按成员/房间/内容、状态（已发送/失败）和日期筛选最近记录；暂不提供导出和自动保留策略。
- 账号隔离：发送计划列表和发送记录都只显示当前绑定账号；切换账号后，另一账号的任务仍在后台按原计划运行，但不会出现在当前账号的列表/告警中，切回该账号可见。
- 暂停/取消：
  - 暂停在当前一批发送结束后生效；
  - 取消把未发送项标记为 `cancelled`，已发送不撤回；
  - 页面关闭或网站重启不丢任务；重启时把遗留 `sending` 标记为 `unknown` 并暂停任务，
    **不自动重发**，避免重复消息。
- 任务状态：`scheduled` / `running` / `paused` / `completed` / `failed` / `cancelled`。
- 错过每日任务超过 1 小时时顺延到下一次，不在异常时间补发。

## 6. 安全与防误操作

- 访问密码：复算计分页密码；`ROOM_MESSENGER_PASSWORD` 留空时使用 `SCORE_GIFTS_PASSWORD`（再回退 `GIFT_REPLIES_PASSWORD`）。不要为该页单独发明密码。仅腾讯云启用。
- 模式 A：60 分钟路径限定 HttpOnly Cookie（`Path=/api/room-messenger`），签名密钥只在进程内存；
  网站重启后需重新输入。
- 所有写接口要求同源 `Origin`，所有响应 `Cache-Control: no-store`。
- 即时发送必须输入确认词“确认发送”；创建定时/批量任务必须勾选确认。
- 页面不保存密码到 `localStorage`/`sessionStorage`；密码不进 URL。
- 登录短信沿用 fan-hub 的每手机号/全局小时限速；页面密码失败使用独立限速组。
- 发送文本长度 1–1000 字；桥与网页双重校验。
- 审核日志：`/var/lib/snh48-web/room_messenger/audit.jsonl`（0600），记录账号、频道、长度、短摘要、SHA256 前缀和结果。
- 完整发送记录：`/var/lib/snh48-web/room_messenger/sent.jsonl`（0600，超过 20MB 轮转为 `.1`），每条记录包含完整 `text`、来源 `manual/job`、账号、频道、消息 ID、状态和错误；页面“发送计划 → 发送记录”可查看最近 80 条。
- 删除墓碑：`/var/lib/snh48-web/room_messenger/deleted.json`（0600），保存被删除消息的完整原文、消息 ID、时间和删除时间；历史接口会把墓碑合并为“此消息已删除”。
- 个人号 Token 会随 `config/accounts.json` 的 `hub` 组同步到阿里云（既有策略）；
  阿里云页面禁用，不会使用该 Token 发送。

## 7. 环境变量

见 `.env.example` 的“房间消息发送页”段落。关键项：

| 变量 | 默认 | 说明 |
|------|------|------|
| `ROOM_MESSENGER_PASSWORD` | 回退 `SCORE_GIFTS_PASSWORD` | 留空即可，默认复算计分页密码 |
| `ROOM_MESSENGER_ENABLED` | 跟随主节点 | 阿里云默认关闭 |
| `ROOM_MESSENGER_STATE_DIR` | `/var/lib/snh48-web/room_messenger` | 任务/绑定/日志 |
| `ROOM_MESSENGER_CATALOG_PATH` | fan-hub `member_catalog.json` | 成员/频道目录 |
| `ROOM_MESSENGER_ROOM_CONFIG_PATH` | fan-hub `config/room_monitor.json` | 补入目录中缺失的已监控成员（如陈嘉仪） |
| `ROOM_MESSENGER_COMMAND` | 回退 `FLIP_CARDS_ACCOUNT_ADMIN_COMMAND` | 特权桥客户端 |
| `ROOM_MESSENGER_MIN_INTERVAL_SECONDS` | `1` | 批量最小间隔（技术下限） |
| `ROOM_MESSENGER_MAX_BATCH_MESSAGES` | `0` | 0 表示不设业务批量上限 |
| `ROOM_MESSENGER_DAILY_SEND_CAP` | `0` | 0 表示不设每日发送上限 |
| `ROOM_MESSENGER_MAX_JITTER_SECONDS` | `0` | 0 表示不额外限制浮动；仍不得低于最小间隔 |
| `ROOM_MESSENGER_CHUNK_SECONDS` | `300` | 单次桥调用/连接复用窗口 |

## 8. 部署与验收（禁止真实发送）

代码部署：

1. 网站仓库提交后，腾讯云 `git pull`；同步 fan-hub 的 `scripts/web/room_messenger_ops.py`、
   `scripts/web/room_messenger_qchat.js` 和 `flip_account_admin.py`。
2. 安装新版特权桥服务端/客户端（`deploy/harden_runtime_permissions.sh` 或等价安装），
   重启 `snh48-privileged-bridge-flip.service`。**不新增服务。**
3. 不要设置独立密码；保持 `.env` 的 `ROOM_MESSENGER_PASSWORD` 为空，页面复用 `SCORE_GIFTS_PASSWORD`。
4. 重启 `snh48-web.service`，确认 `/var/lib/snh48-web/room_messenger` 可写（0700/0600）。
5. 运行 `node script/obfuscate_js.cjs`，提交 `static/js-dist/room_messenger.js` 和
   `static/css-dist/room_messenger.css`。

只读烟测（不得发送）：

```bash
curl -sS -D - -o /dev/null https://cjy.plus/room/messenger          # 200
curl -sS -o /dev/null -w '%{http_code}\n' https://cjy.plus/api/room-messenger/verify  # 401
# 登录后：
curl -sS -b cookie.txt https://cjy.plus/api/room-messenger/verify  # 200
curl -sS -b cookie.txt https://cjy.plus/api/room-messenger/account # 200，accounts 可为空
curl -sS -b cookie.txt 'https://cjy.plus/api/room-messenger/catalog?q=陈嘉仪' # 200，只读
```

真实发送验收由 owner 手动指定频道和内容完成；自动化/agent 不得调用 `/send` 或创建任务后启动。

## 9. 常见失败

| 现象 | 原因 | 处理 |
|------|------|------|
| 页面提示仅腾讯云启用 | 当前是阿里云或未设置密码 | 在腾讯云访问 `cjy.plus` |
| 登录个人号提示“已在账号池” | 该账号已是池账号 | 先从池移出，或换个人号 |
| 历史消息 403/401 | Token 失效或账号非个人号 | 重新登录 / 检查 Token |
| 发送返回“订阅频道失败” | QChat 订阅被拒 | 确认频道存在、账号状态正常；不要连续重试 |
| 任务暂停且最后错误为“结果未知” | 桥超时/网站重启 | 人工核对频道记录后再继续，避免重复 |
| 阿里云无法发送 | CDN 与功能门控 | 预期行为，仅腾讯云 |

## 10. 代码位置

- `website/room_messenger_api.py`：鉴权、账号绑定、目录、历史、发送、任务调度。
- `website/templates/room_messenger.html`：页面结构。
- `website/static/js/room_messenger.js`、`website/static/css/room_messenger.css`：前端。
- `snh48-fan-hub/scripts/web/flip_account_admin.py`：登录分流与命令分发。
- `snh48-fan-hub/scripts/web/room_messenger_ops.py`：个人号校验、REST 历史、QChat 发送。
- `snh48-fan-hub/scripts/web/room_messenger_qchat.js`：QChat CommonLink 发送实现。
- `deploy/privileged/snh48_privileged_bridge_server.py` / `_client.py`：命令白名单与超时。
