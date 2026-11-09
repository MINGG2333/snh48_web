# /home/snh48_web 后台运行与同步状态

## 2026-11-09 房间信使修复发送失败并补齐删除/小号/Token 失效入口（腾讯云已生效，阿里云仅同步代码）

- 用户反馈发送时返回 `account is invalid`。根因不是 Pocket48 拒绝，而是 QChat 发送脚本把 NIM accId 当成纯数字校验：实际值为 `20250222083119_250u4g4lgoivmjr`（30 位字母数字下划线），在本地 `normalizeId` 就被拒绝。修复为独立的 `normalizeAccount`（允许字母/数字/下划线/短横线），serverId/channelId 仍保持纯数字校验。修复后用个人号 `147062891` 做只读 QChat 连接探针：NIM 登录、QChat 登录、订阅陈嘉仪公开房间全部成功（未发送消息）。
- 新增删除消息：网页只对自己发送的消息显示删除图标；服务端再次校验 `sender_id == 当前个人号 userId`；经桥命令 `messenger-delete` 调 Pocket48 `/im/api/v1/team/msg/delete`（friendship 头，accId 取当前 NIM 凭据）；删除要求输入确认词“确认删除”。
- 新增同手机号大号/小号切换：`messenger-probe` 返回 `bigSmallInfo`；账号弹窗显示大号/小号，点击小号通过 `messenger-switch` 调 `/user/api/v1/bigsmall/switch/user`，保存新 Token、立即标记 personal 并切换页面绑定。未在自动验收中实际执行切换。
- Token 失效入口：页面加载和打开账号弹窗时自动做只读 probe；失效时账号卡显示“重新登录”和红色提示条，历史/发送/删除错误含 token/失效/非法授权时也会切到该状态。
- 密码策略：不再为房间信使自定义密码。腾讯云 `.env` 的 `ROOM_MESSENGER_PASSWORD` 已置空，页面复用 `SCORE_GIFTS_PASSWORD`（再回退 `GIFT_REPLIES_PASSWORD`）。已删除登录页“个人号专用”“HttpOnly 会话”等内部提示。
- 代码：网站 `9c0e46f`；fan-hub `80759901d`。桥命令白名单新增 `messenger-delete` / `messenger-switch`（45 秒）；普通翻牌命令仍 40 秒，`messenger-send` 仍 380 秒。
- 部署：腾讯云重新安装 `/usr/local/libexec/snh48-privileged-bridge-server` 和 `/usr/local/bin/snh48-privileged-bridge-client`，重启 `snh48-privileged-bridge-flip.service`（PID `1729055`）；移动端与选择模式修复后 `snh48-web.service` 最终 PID `1826348`，`snh48-privileged-bridge-flip.service` PID `1807016`；启动日志有 `Room messenger scheduler started`。
- 只读烟测：页面 200；用 `SCORE_GIFTS_PASSWORD` 登录 200；账号 200，绑定 `147062891`；probe 200 且返回大号 `147062891`、小号 `174063630`；catalog 200；删除接口错误确认词 422、他人消息 403；切换非法目标 400；QChat 连接探针成功。未调用真实 `/send` 或 `/delete`，未发送/删除任何真实消息。
- 待 owner 手动验收：先看历史，再发 1 条低风险消息，确认气泡和客户端显示；随后测试删除自己刚发的消息、定时/批量、以及小号切换。首次真实发送/删除前仍需 owner 明确同意并提供内容。
- 完整发送文本：`1e03cad` 起新增 `/var/lib/snh48-web/room_messenger/sent.jsonl`（0600，20MB 轮转），即时发送和定时/批量每条消息都保存完整 `text`、来源、账号、频道、消息 ID、状态和错误；页面“发送计划 → 发送记录”可查看最近 80 条。测试消息“1”已按审计回填，可在小号 `174063630` 的发送记录中看到。
- 批量测试复盘：21:39 的 3 条任务功能正常（completed，3/3 sent，实际间隔约 2.2 秒）。发现旧代码把整批 `sent_at` 和发送记录时间都写成批完成时间（21:39:07），已用 QChat ack 时间修复，并把这次测试回填为 21:39:02/21:39:04/21:39:06；预演时间改为精确到秒。
- 移动端修复（`00657a8`、`837bd14`）：iOS 自动放大根因是输入框字体 0.88rem≈13.3px；移动端媒体查询将所有输入框/textarea/select 固定 16px，并加 `text-size-adjust:100%`、登录层可滚动、Font Awesome 改非阻塞加载。另一个更严重的 bug 是 `selectChannel()` 调用 `S.selectedIds.clear()` 但状态对象缺少 `selectedIds/selectMode/deleteTargets` 字段，导致选频道抛错、聊天区一直“未选择频道”、输入框不出现；已补齐状态字段并加静态防回归断言。移动端实测选频道后标题、消息和输入框正常。
- 新增批量删除：聊天页支持选择模式、全选当前、勾选自己发送的多条消息并一次删除；服务端 `messenger-delete-batch` 单次最多 50 条，失败项单独返回，成功项写墓碑。
- 发送计划栏改为桌面端第三列推开聊天区（`queue-open`），不再覆盖聊天消息；移动端仍为全屏抽屉。
- 业务上限调整（2026-11-09 晚，用户定）：`49feeab`/`596d608cb` 起取消每日 100 条、单批 30 条和最小间隔 15 秒的业务限制；默认 `ROOM_MESSENGER_MIN_INTERVAL_SECONDS=1`、`MAX_BATCH_MESSAGES=0`、`DAILY_SEND_CAP=0`、`MAX_JITTER_SECONDS=0`。只剩 1 秒技术下限、单任务 5000 条请求上限和单条 1000 字；随机浮动仍保证实际间隔不低于最小间隔。腾讯云 `/verify` 已返回 `min_interval=1,max_batch=0,daily_cap=0`。
- 删除可视化：`d371be5` 起删除成功不再从页面移除消息，而是在本地 `deleted.json` 写墓碑；历史接口会把墓碑合并为“此消息已删除”并保留原短文本（灰色删除线），刷新页面仍可见。删除审计新增 `text_length`/`text_sha256`/`preview`。测试中已删除的 `91a6dab84d8ae657bdcf177e15ea680c` 已按审计回填墓碑；未重新发送或重新删除。
- 阿里云：代码已同步到 `41429f7` / `9c4275571`，未重启 `snh48-aliyun.service`，房间信使保持关闭。

## 2026-11-09 房间信使（个人号房间消息发送页）腾讯云已部署，阿里云仅同步代码（待确认）

- 需求：在 `/room/messenger` 新增个人号房间消息页面，支持成员/频道选择、最近聊天、即时发送、单次定时、批量间隔/浮动、每日重复、左侧常用频道、发送计划队列和移动端布局。真实发送由 owner 手动验收，自动化不向任何真实频道发送消息。
- 代码：网站 `dfbf496`、`d713e77`、`3a01dc7`、`ed833ed`、`4e52196`；fan-hub `03d85f35c`。网站新增 `website/room_messenger_api.py`、模板/JS/CSS 及混淆产物、测试；fan-hub 新增 `scripts/web/room_messenger_ops.py`、`scripts/web/room_messenger_qchat.js`，并扩展 `flip_account_admin.py` 的 `verify-code` 个人号分支和 `messenger-*` 命令。
- 账号策略：手机号验证码登录后立即 `token_manager.mark_personal()`，不进入 `account_pool`、不创建翻牌任务；如果账号已在池中则明确失败。Token 只存在 root `config/accounts.json`，网页进程不接触。
- 发送链路：网页 → 既有 `snh48-privileged-bridge-flip.service` 固定命令 `messenger-status/probe/history/send` → fan-hub `room_messenger_ops.py` → QChat CommonLink 发送脚本；未新增 systemd 服务/socket。桥命令白名单与按命令超时已更新，普通翻牌命令仍为 40 秒，`messenger-send` 为 380 秒。
- 安全：`ROOM_MESSENGER_PASSWORD` 已写入腾讯云 `/home/snh48_web/.env`（0600，未在对话中输出）；60 分钟路径限定 HttpOnly Cookie；即时发送确认词“确认发送”；每日上限 100、最小间隔 15 秒、单批最多 30 条、单批发送块最多 10 条；任务持久化 `/var/lib/snh48-web/room_messenger/`，重启时遗留 `sending` 标记 `unknown` 并暂停，不自动重发。
- 部署：腾讯云安装新版 `/usr/local/libexec/snh48-privileged-bridge-server` 和 `/usr/local/bin/snh48-privileged-bridge-client`，重启 `snh48-privileged-bridge-flip.service`（PID `1520951`，18:43:53 起，`NRestarts=0`）；`snh48-web.service` 最终重启后 PID `1536440`（19:00 后最终重启），启动日志出现 `Room messenger scheduler started`。`snh48-privileged-bridge-social.service` 未重启（PID `3014153`）。
- 只读烟测（腾讯云 `https://cjy.plus`）：页面 200；未登录 `/api/room-messenger/verify` 401；登录 200、`/verify` 200、`/account` 200（仅 `has_token` 布尔和账号元数据，无 Token 值）、`/catalog` 200、`/jobs` 200、静态 JS/CSS 200；`catalog?q=陈嘉仪` 返回 1 个成员、2 个频道（`36376935` 公开、`36393478` 小房间），目录补入 `config/room_monitor.json` 的已监控成员。未调用真实 `/messages`、`/send`，未创建/启动真实发送任务；页面聊天/定时/批量弹窗用拦截的合成消息做过桌面与移动端截图检查，未向任何真实频道读取或发送。
- 测试：网站 `test_room_messenger_api` 9 项、`test_room_messenger_template` 3 项、`test_privileged_bridge` 7 项、`test_password_page_security` 全部通过；fan-hub `test_room_messenger_ops` 7 项、`test_room_messenger_qchat.cjs` 通过。仓库全量测试仍有既有的 Python 3.9/缺失 venv 环境性错误，与本次无关。
- 阿里云：代码已 `git pull`（网站 `d713e77`、fan-hub `03d85f35c`），但**未重启** `snh48-aliyun.service`；`ROOM_MESSENGER_ENABLED` 在阿里云保持关闭。待 owner 在腾讯云手动验收通过后再重启阿里云。阿里的代码已到 `ad41dea`/`03d85f35c`，运行进程仍是旧版。
- 待 owner 手动完成：用个人号登录、在低风险频道发送 1 条测试消息、确认 QChat 订阅与消息显示；验收前不得把真实频道写入自动测试。

## 2026-11-09 密码页统一 60 分钟会话并修正旧 Cookie 误报（双端已生效）

- 背景：`/flip` 在部署重启后，浏览器里的旧 Cookie 被当成“密码错误”（403），页面反复请求后把翻牌页限流打到 429；同类问题也存在于上麦回放、社交凭据、红蓝台账、微店订单和背景词管理。
- 代码（web `e97a53d`、`dee6126`）：新增 `website/password_session.py`，统一 HttpOnly Cookie 有效期为 `PASSWORD_SESSION_MAX_AGE_SECONDS`（默认 60 分钟），签名密钥只放进程内存、不落盘；旧/未知 Cookie 一律返回 401“需要密码”，不计入密码失败限流；只有真正提交错误密码才计数。红蓝台账停用 `private_handover/web_state/redblue_ledger_cookie_secret` 持久密钥（已于 2026-11-09 移入 `private_handover/存档/停用密钥/`，不再读取）。上麦回放、社交凭据、红蓝、微店、背景词和翻牌页均按此规则处理；翻牌页保持内存密码 + 媒体签名 URL 方案。`dee6126` 起密码失败限流按页面组独立（`PASSWORD_LOGIN_MAX_PER_WINDOW`/`PASSWORD_LOGIN_WINDOW_SECONDS`），业务管理、礼物回复、计分、房间消息、PK、记忆等请求头密码页也不再和观察页共用预算；scroller 成功登录不再消耗限流额度。
- 文档：`doc/security/password_page_best_practices.md` 将“60 分钟 Cookie + 内存密钥 + 旧 Cookie 401 不计限流”定为新密码页默认最佳实践；存量纯请求头密码页无需改造。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` PID `768519`，阿里云 `snh48-aliyun.service` PID `1364709`。
- 并发合并注意：`97c9734` 曾短暂恢复红蓝持久密钥配置；阿里云在 07:23 由旧逻辑生成了临时密钥文件。已由 `adfbddf` 恢复为 `password_session` 内存密钥，并把该临时文件移入 `private_handover/存档/停用密钥/redblue_ledger_cookie_secret.recreated-20261109-0723`；`web_state/` 保持无密钥文件。
- 验证：双端 92 项相关单测通过（礼物回复模板 2 项既有失败与本次无关）；腾讯云和阿里云实测上麦回放/红蓝/微店/背景词未登录 401、正确密码登录 200 且 `Max-Age=3600; HttpOnly`、带有效 Cookie 200、连续 12 次旧 Cookie 全部 401 且未触发 429；腾讯云社交凭据页同样通过。限流隔离实测：社交凭据连续 10 次错误密码后第 11 次 429，此时上麦回放和红蓝正确密码仍登录 200；上麦回放被刷满后社交凭据和观察页仍正常。恢复内存密钥后再次登录红蓝，确认不会重新生成密钥文件。
- 注意：本次重启前签发的红蓝/上麦回放/社交凭据/微店/背景词 Cookie 会全部失效一次，属预期；重新输入密码后，60 分钟内有效。

## 2026-11-09 红蓝导出保留昵称中的常见符号与 emoji（双端已生效）

- 现象：`/business/redblue2026` 导出按条目图时，昵称 `挺吉⛽` 的 `⛽` 没有显示。
- 根因：`gift_reply_export._display_text()` 把所有 `U+2500–U+28FF` 字符都当作装饰符号直接过滤，误伤了该区间内的常见符号/emoji（如 `⛽` U+26FD、`✅` U+2705、`⚡` U+26A1）。
- 代码（web `b8edb17`）：过滤范围收窄为制表线/方块元素 `U+2500–U+259F` 与盲文 `U+2800–U+28FF`；Miscellaneous Symbols、Dingbats 等交给字体缺失检测和备用字体链处理，能渲染就保留。同步扩展礼物回复导出的符号测试用例。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `675703`，阿里云 `snh48-aliyun.service` 最终 PID `1273057`。
- 验证：网站 `tests.test_gift_reply_export` + `tests.test_redblue_ledger_api` 55 项双端通过；腾讯云实际导出 `2026-11-09` 按条目图已显示 `挺吉⛽` 的加油机 emoji，业务名仍只在第一条 `01:34` 记录显示。

## 2026-11-09 红蓝台账悬浮回顶部/底部按钮（双端已生效）

- 需求：`/business/redblue2026` 增加悬浮按钮，可在页面顶部和底部之间快速跳转。
- 前端：新增固定在右下角的 `#floatingScrollBtn`；滚动超过 200px 时显示“↑ 顶部”，回到顶部区域后显示“↓ 底部”，点击平滑滚动到对应位置。按钮层级低于弹窗，避免遮挡弹窗操作。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `666828`，阿里云 `snh48-aliyun.service` 最终 PID `1262406`。
- 验证：生产页 Playwright 实测初始为“↓ 底部”，点击后滚到页面底部并切换为“↑ 顶部”，再次点击回到顶部；无 JS pageerror。

## 2026-11-09 红蓝导出业务名改挂首个分摊条目（双端已生效）

- 需求：多人拼单导出时，业务名不再显示在“完成该笔业务”的条目，改为显示在该笔兑换最早的第 1 条分摊记录上。
- 代码（web `1959694`）：兑换新增 `display_entry_id/display_entry_time`（取分摊按时间排序后的第一条），导出标签改由 `business_display_labels` 承载；`completion_entry_id` 仍保留用于页面“拼成点”标记。`redblue_export._business_text()` 改为优先读取展示标签，后续贡献条目仍显示 `—`。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `628265`，阿里云 `snh48-aliyun.service` 最终 PID `1230364`。
- 验证：网站 `tests.test_redblue_ledger_api` 46 项双端通过；两端已登录数据接口 21 条兑换的 `display_entry_id` 均等于各自第一条分摊条目，无不一致；页面 200。

## 2026-11-09 多人拼单业务兑换（双端已生效）

- 需求：`/business/redblue2026` 的业务兑换支持多人拼单，多个粉丝的条目可以合并兑换同一个业务；导出图只在一个人的条目上显示业务名。
- 后端（web `6187055`）：`business_redemptions` 新增 `participants`（按分摊条目自动汇总每人的分数与条目数）；分摊校验不再限制单一粉丝，但仍要求所有条目同一种计分方式、同一条目不可重复使用、分摊合计必须等于业务分值。`fan_summary` 的 `business_allocated_score` 改为按各人实际分摊累计，`business_labels` 只给名义持有人（`fan_id/fan_name`），其他拼单参与者写入 `business_shared_labels`；导出仍只在 `completion_entry_id` 对应条目显示业务名。
- 前端：兑换弹窗“粉丝”改为可多选列表（按住 Ctrl/⌘ 多选），分摊表新增“粉丝”列，跨粉丝按最早条目自动分摊/手动填写；“自动分摊”和汇总按所选粉丝合并计算。编辑多人兑换时回填全部参与者；“新建兑换”清空选择。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `579193`，阿里云 `snh48-aliyun.service` 最终 PID `1188186`。
- 验证：网站 `tests.test_redblue_ledger_api` 46 项双端通过（新增多人拼单分摊、导出仅一个完成条目带业务名、混用计分方式被拒）；两端 `/business/redblue2026` 200、未登录 `/api/redblue/data` 401、已登录返回 126 条条目/21 条兑换且旧兑换 `participants` 均为 1 人；生产页 Playwright 多选两名粉丝自动分摊成功（“参与 2 人”、两行分别来自不同粉丝），无 JS pageerror。

## 2026-11-08 20:54 CST 红蓝台账分数多选、统一右下提示与内部错误脱敏（双端已生效）

- 需求：`/business/redblue2026` 偶尔在右下弹窗显示 `ssh: connect to host ... port 22: Connection timed out`，不希望页面暴露内部信息；新增按分数多选筛选；“加载中/正在生成…”等状态统一到右下弹窗；“全选当前列表”移到时间列表头左侧且不显示文字。
- 后端（web `40ecad8`）：`/api/redblue/data` 和两个导出接口新增 `scores` 多选参数（逗号分隔），`_filter_entries` 按四舍五入后的分数精确匹配；`/data` 新增 `score_options`（全部条目的去重分数，供前端生成多选菜单）。`SharedStatePeerError`/`SharedStateError`/基础设施类 `ValueError` 统一改写为“主节点暂时不可用”或“红蓝台账暂时不可用”，详细 SSH/路径/traceback 只写服务端日志；前端 `publicError()` 再做一层兜底。
- 前端：筛选区新增“分数”多选下拉（复选框 + 清除，支持 1/2 个时显示具体分数、3 个以上显示数量）；`filterQuery` 把选中分数传给数据和导出接口。`setStatus()` 改为右下角 sticky toast，移除工具栏 `actionStatus` 内联提示；错误/成功 toast 仍自动隐藏。表头第一列改为 `selectAll` 复选框（`aria-label`/`title` 保留无障碍说明，不显示可见文字），移除工具栏“全选当前列表”。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `67114`，阿里云 `snh48-aliyun.service` 最终 PID `675959`。
- 验证：网站 `tests.test_redblue_ledger_api` 44 项双端通过；`scores=3,6` 直接调用返回 45 条且分数集合 `{3.0,6.0}`，`score_options` 11 个；两端页面 200；模板 JS `node --check` 通过。

## 2026-11-08 20:05 CST 红蓝微店自动补采与阿里云转发（双端已生效）

- 现象：`/business/redblue2026` 11-07 至 11-08 微店渠道缺失；阿里云微店 Cookie 11-07 00:38 后过期，页面每 5 分钟自动 sync 持续失败且静默，台账停在 11-06。
- 代码（web `0498e75`）：`redblue_ledger_api.py` 新增 `_primary()/run_weidian_sync_once()/start_weidian_auto_sync()`；主节点每 10 分钟检查缓存/台账并自动 `sync + upsert_weidian`，失败 5 分钟重试，Cookie 恢复后全量补全。非主节点的 `sync/ship` 任务经 `peer_command("weidian-admin")` 转发腾讯云，`apply` 通过新增的 `redblue-cache` 读取腾讯云缓存，阿里云不再需要微店 Cookie。状态落 `private_handover/web_state/redblue_weidian_sync_state.json`，`/api/redblue/data` 返回 `weidian_sync`，页面顶部显示最近同步时间/失败原因。
- 部署：网站已推送并双端 pull；腾讯云 `snh48-web.service` 最终 PID `21102`（20:14:44 重启，含 pending sync 复用修复），阿里云 `snh48-aliyun.service` 最终 PID `629387`（20:14:43 重启）。阿里云 `redblue-weidian-worker.timer` 已停用，旧 `config/weidian_cookies.txt` 移到 `/root/weidian_cookies.txt.removed-20261108-2004`。
- 验证：腾讯云启动日志 `Red-blue Weidian auto-sync checked (primary=True)`；20:03:22、20:13:30 两轮自动同步完成，网站重启后 20:24:10 再次成功，状态 `ok`、28 单、`skipped=true`。阿里云 peer 实测 `job-submit → job-result done → redblue-cache 28 单`。网站 42 项、fan-hub 48 项相关单测双端通过；两端页面 200、未登录 API 401。

## 2026-11-07 21:13 CST 修复微店 Cookie 验证 503 与结果不可见（腾讯云已生效）

- 现象：在 `/social-credentials-admin` 填写微店 Cookie 点“验证并更新”无反馈；服务日志显示 `POST /api/social-credentials/update` 连续 503。
- 根因：特权桥把 venv Python 解析为系统 `/usr/bin/python3.11`，该环境缺 `websockets`；桥内 `validate_weidian` import 重型订单监控模块失败，stdout 为空，桥返回 503。页面错误消息又在长列表底部，用户看不到，表现为“没有反应”。
- 修复：fan-hub `3a06e1007` 改为桥内用 `requests` 直接调店长版订单列表接口验证 `wdtoken`；web `f8526a2` 在验证中/成功/失败时把消息滚动到视口中央。
- 部署：两仓库已推送并双端 pull；腾讯云 `snh48-web.service` 21:13:03 重启（PID `2842874`，active），页面 200、未登录 status 401。
- 验证：特权桥客户端以当前过期 Cookie 实测返回 `ok:false` 和“微店 cookies 已过期”，不再 503；重新提交有效 Cookie 即可完成写入并恢复订单监控。

## 2026-11-07 15:05 CST 社交凭据页恢复平台卡片并新增微店 Cookie（腾讯云已生效）

- 现象：`/social-credentials-admin` 登录后只显示“口袋48账号 Token”，微博/抖音/B站/闲鱼/48商城区块全部消失；后端 `status` 实际返回完整 6 项。
- 根因：提交 `da47c08` 把 `slotLabel` 的取值写在 `for(const slot of platform.slots)` 循环外，引用未定义的 `slot`，`render()` 抛 `ReferenceError`，所有动态平台区块未渲染。
- 修复：提交 `918c457` 把 `slotLabel` 移回槽位循环内；同时新增“微店”单槽，`PLATFORMS` 和主槽限制加入 `weidian`，模板增加名称、说明、无手机号表单和验证按钮。
- 部署：网站 `918c457` 已推送，腾讯云 `snh48-web.service` 14:59:47 重启（PID `2504473`，active），页面与 API 加载新代码。阿里云未重启（该页在阿里云硬禁用，代码随下次重启生效）。
- 验证：腾讯云桥 `status` 返回 `weibo/douyin/bilibili/xianyu/weidian/shop48`；`validate_weidian` 对当前过期 Cookie 正确报 `code=2`；页面 200、未登录 `/api/social-credentials/status` 401；用真实 status 数据执行 `render()` 生成 6 个平台区块；网站 6 项单测、fan-hub 23 项相关单测通过，`node --check` 与 `py_compile` 通过。
- 待办：腾讯云 `config/weidian_cookies.txt` 当前已过期；管理员在页面登记新的微店 Cookie 后，`weidian-order-monitor` / `-test` 会在下一轮自动读取并恢复采集，无需人工重启。

## 2026-11-07 12:12 CST 兑换限制同计分方式、无口袋ID昵称也可兑换（双端已生效）

- 需求：拼单只能同一种计分方式（鸡腿只能和鸡腿、计分卡只能和计分卡）；没有口袋ID/昵称的条目也必须能兑换，不能只读保留。
- 后端：兑换新增必填 `scoring_method`；自动分摊和手工分摊都只允许该方式的条目，混入其他方式返回 422。兑换可由 `fan_id` 或 `fan_name` 定位；`fan_id` 为空时按昵称匹配未关联条目，记录保留 `fan_name`。
- 网页：兑换弹窗新增“计分方式”，按方式过滤分摊条目；无 ID 条目用 `name:<昵称>` 作为兑换键，条目处仍显示“管理兑换/兑换业务”，粉丝下拉显示“按昵称”；加赠仍只对鸡腿+微店开放。生产确认 2 个无口袋ID条目：`南方有嘉木`（1 分，待兑换）、`再坏对你不好吗`（3 分，已迁移）。
- 迁移：代码部署后重跑 `POST /api/redblue/migrate-legacy-business`，结果 `created=1, skipped=0, cleared=1`；此前跳过的「再坏对你不好吗」已转为 `fan_id=""`、`fan_name` 兑换，旧业务字段清零。现生产共 17 条兑换记录、0 条旧字段，SnowYee 仍为 6-ID 合影（5+1）。
- 部署：网站 `6f3f3b9` 已推送并双端 pull；腾讯云 `snh48-web.service` 12:07:28 重启（PID `2349051`），阿里云 `snh48-aliyun.service` 12:07:27 重启（PID `3025341`）。
- 验证：53 项网站测试通过；`node --check` 通过；本地 Playwright 验证同一粉丝鸡腿/计分卡条目按方式过滤（默认鸡腿，切换计分卡只显示计分卡条目）；生产只读 Playwright 确认无 ID 昵称“再坏对你不好吗”可打开管理、编辑原业务/加赠，且无旧业务下拉。

## 2026-11-07 05:30 CST 统一业务兑换展示、支持微店加赠并迁移旧业务（双端已生效）

- 需求：兑换业务列不再同时存在“逐条业务下拉”和“兑换记录”两套模式；微店兑换需要额外叠加一个加赠业务。
- 代码：移除条目表和编辑弹窗里的旧 `selected_business`/`selected_business_bonus`/`business_done` 控件；所有业务统一走 `business_redemptions`。兑换弹窗新增“加赠业务（仅微店）”，只允许 bonus 组选项，不额外扣分，但要求分摊条目包含微店来源；条目详情、兑换列表、按昵称汇总均显示加赠。
- 导出：`business_completion_labels` 会把主食业和加赠业务一起放在拼成条目上，用 `+` 连接；贡献条目仍显示 `—`。
- 迁移：新增幂等接口 `POST /api/redblue/migrate-legacy-business`，把旧条目业务转为兑换记录并清空旧字段；生产执行结果 `created=15, skipped=1, cleared=15`。跳过的是「再坏对你不好吗」：该微店条目没有口袋48 ID，暂保留为只读“历史业务”并提示补 ID 后重新迁移。
- 部署：网站 `9896b3a`、`c09ff2a` 已推送并双端 pull；腾讯云 `snh48-web.service` 05:29:24 重启（PID `1990103`），阿里云 `snh48-aliyun.service` 05:29:23 重启（PID `2612494`）。迁移前台账备份在 `/home/snh48-fan-hub/private_handover/web_state/redblue_ledger_2026.json.bak.before_business_migration_20261107`。
- 验证：50 项网站测试通过；`node --check` 通过；临时数据 Playwright 实测自动分摊 5+1、加赠《答案之书》、完成/删除和统一“未兑换/管理兑换”显示；生产只读 Playwright 确认 SnowYee 兑换、PLANET 迁移后的“ID 合影+答案之书”、无旧业务下拉、微店加赠可选。

## 2026-11-07 05:00 CST 修复 logrotate 超大 rotate 数量导致 CPU 空转（阿里云）

- 现象：`logrotate.service` 每日 00:00 启动后持续约 3h39m 占用 100% CPU；根因是 `/etc/logrotate.d/nginx` 的 `rotate 1000000000`——logrotate 3.19 每次轮转会枚举约 10 亿个代次。对照实验：`rotate 5` 用时 0.00s，`rotate 1000000000` 20s 超时。
- 修复：`deploy/logrotate/nginx` 与已安装 `/etc/logrotate.d/nginx` 改为 `rotate 3650`（约 10 年，仍保持“不按文件数量提前删除”的意图）；`deploy/install_observability.sh` 注释同步。
- 验证：阿里云手动执行 `logrotate -v /etc/logrotate.conf` 完整跑完（rc=0），nginx 日志正常轮转并压缩，`systemctl reset-failed logrotate.service` 已清除失败状态。
- 日志清理仍由 `snh48-website-log-archive.timer`（每天 03:20）负责：COS 上传并校验后才 `unlink`，未配置 COS 时拒绝删除。

## 2026-11-07 04:42 CST 红蓝台账支持按人业务兑换与导出完成点标记（双端已生效）

- 需求：SnowYee 等粉丝可能用多条计分（如 5+3）拼一个 6 分业务；网页需显示分摊与剩余，导出按条目图只在“拼成业务”的条目写业务名，之前贡献条目写 `—`，同一条目完成多个业务用 `+` 连接。
- 数据：`redblue_ledger_2026.json` 新增顶层 `business_redemptions`（`fan_id`、`business`、`cost`、`status`、`allocations[{entry_id,score}]`、`note`）。新增 `/api/redblue/redemptions` 的 POST/PATCH/DELETE；默认按最早条目自动分摊，校验总分摊=业务分值、不超过条目可用分、不能重复使用；`completion_entry_id` 按条目时间累计到业务成本时确定。旧 `selected_business`/`business_done` 保留兼容。
- 网页：工具栏新增“业务兑换”；弹窗支持选粉丝、选业务、自动分摊、逐条改分数、标记完成/兑换中、备注、编辑/删除；条目“兑换业务”列显示 `本条 X 分 · 余 Y` 与拼成点，“业务状态”列显示兑换中/已完成；按昵称汇总显示已兑换和剩余分。
- 导出：`redblue_export._business_text()` 只在 `business_completion_labels` 存在的条目显示业务名（多个 `+`），有分摊但非完成条目显示 `—`，未参与兑换的旧项目仍按原 `selected_business` 显示；不再显示余数/分摊比例。
- 验证：`tests/test_redblue_ledger_api.py` 33 项及 identity/gift/password 合计 48 项通过；`node --check` 通过；本地临时数据（Alice 5+3）用 Playwright 实测登录、自动分摊 5+1、保存、条目显示、标记完成、删除后恢复原下拉均正常。
- 部署：网站提交 `b1bc4d1` 已推送并双端 pull；腾讯云 `snh48-web.service` 04:40:57 重启（PID `1945399`），阿里云 `snh48-aliyun.service` 04:41:05 重启（PID `2552368`，04:41:07 启动完成，QA warmup 已关闭），两端 `/api/redblue/data` 均返回 `business_redemptions` 与条目分摊字段，当前尚无兑换记录。
- 文档：`doc/website_pages.md`、`doc/shared_runtime_state.md` 已更新；未修改 fan-hub 脚本或服务。

## 2026-11-07 04:05 CST 修复直播回放链接不可用与时光轴未来场次缓存（阿里云）

- 现象：`/replay/1325592362732032000` 等新回放页显示「回放链接不可用」。根因：`replay_page` 先命中过期的 `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/summary.csv`，未找到 `live_id` 却仍执行 `break`，导致永远不会读取权威的 `live_record/live_index.csv`。
- 修复：只有命中 `live_id` 时才跳出；未命中则继续扫描后续索引。`website/main.py`。
- 时光轴：`/api/timeline/schedule`、`/live-pushes`、`/live-pushes/grouped`、`/social`、`/danmu` 增加 `Cache-Control: no-store`，避免浏览器/代理用旧缓存隐藏新公布的未来场次（现场日志显示移动端 timeline 只拉 JS、不再请求接口）。
- 验证：`/replay/1325592362732032000` 返回 `replayUrl=https://idol-vod.48.cn/...m3u8`，浏览器 HLS 成功挂载 `blob:` 媒体源；`/api/timeline/schedule` 返回 172 条，其中未来 5 条（2026-11-07 / 11-15 / 11-21 / 12-05）；`/timeline` 客户端渲染 250 个日期节点，最大 2026-12-05。新增回放查找回归测试通过（`tests/test_timeline_api_contract.py`）。
- 运行环境：阿里云内存/swap 严重不足，`snh48-aliyun` 启动时加载 QA 引擎长时间卡在 swap-in。临时把 `/home/snh48_web/.env` 的 `QA_WARMUP_ON_STARTUP` 改为 `false`（备份 `.env.bak.20261107_qa_warmup`），QA 改为首次使用时懒加载；服务已恢复监听 `127.0.0.1:8000`，PID `2492712`。内存恢复后如需恢复启动预热，把该值改回 `true` 并重启即可。
- 部署：`snh48-aliyun.service` 已重启生效；Tencent/GitHub 同步待执行。

## 2026-11-06 07:39 CST 导出图保留符号与 emoji；阿里云重启完成（两端已生效）

- 现象：红蓝/礼物导出昵称中的 `JOJO⭐`、`拾蹄悦(悦悦🌲)` 等符号和 emoji 被 `_display_text()` 按 Unicode `So` 类别直接过滤；腾讯云又没有 FreeSerif/Unifont 系统字体。
- 代码：`gift_reply_export.py` 不再无条件丢弃 `So`，改为按主字体+备用字体链逐字判断；新增 FreeSerif/Unifont/DejaVu 系统路径和 Noto Color Emoji 回退（109px 渲染后 LANCZOS 缩放到目标字号）。埃及圣书体、⭐、🌲、🐒 等均保留。
- 验证：阿里云 `_display_text` 与腾讯云 `_font_runs` 均保留 `JOJO⭐`/`拾蹄悦(悦悦🌲)`/`衡绥suí🌲🐒`/`嘉菲猫不吃鱼𓈒𓂂𓏸`；腾讯云 ⭐ 命中 `_ColorEmojiFont`；网站测试 43 项、腾讯云礼物导出测试 9 项通过。
- 部署：网站提交 `0c0e67d`、`5740868` 已推送并双端 pull；腾讯云 `snh48-web.service` 07:32:13 重启（MainPID `796621`），阿里云 `snh48-aliyun.service` 07:32:37 重启（MainPID `1599651`，07:34:48 启动完成），两端均 active。
- 性能复测：阿里云 `/api/redblue/data` 0.078–0.118s、按条目导出 0.997–1.208s；腾讯云 data 0.037–0.191s、按条目导出 0.490–0.616s、按昵称导出 0.206–0.208s；两节点均读取 `fan_identity_web.json`。

## 2026-11-06 00:05 CST 社交凭据管理增加 48 商城 Cookie（腾讯云已生效）

- 页面：`/social-credentials-admin` 新增“48商城”，SNH48 商城/GNZ48 商城两槽；状态只显示已配置/最近验证时间，不回显 Cookie；页面 200，未登录 `/api/social-credentials/status` 401。
- 桥：`scripts/web/social_credentials_admin.py` 新增 `shop48` 平台与 `validate_shop48`，分别用 `shop.48.cn`/`48.gnz48.com` 的 `GetShowBids` 验证；成功后原子写 fan-hub `config/shop48_cookie_snh.txt`/`gnz.txt`（600）。已用当前有效 Cookie 实测两槽 `validated_at=2026-11-05 23:52:02/03`，状态 configured/valid。
- 部署：网站 `da47c08`（代码）+ `2ed9062`（文档）已推送；腾讯云 `snh48-web.service` 已重启，页面与模板加载新平台；桥测试 4 项、网站 API 测试 5 项通过。阿里云已 pull，页面仍硬禁用，未重启。
- 用途：48 竞价全量归档服务读取这两个文件；用户在页面更新 Cookie 后，下一次 6 小时归档自动使用新值。

## 2026-11-05 22:47 CST 红蓝台账改用精简身份索引并加速 PNG 导出（腾讯云已生效）

- 现象：`/business/redblue2026` 登录后首个 `/api/redblue/data` 在腾讯云冷加载完整身份索引时耗时 17.8s；按条目导出约 1.7–2.1s，`PNG optimize=True` 占主要耗时。
- 页面/代码：`website/identity_index.py` 优先读取 fan-hub 生成的 `room_record/all_members/fan_identity_web.json`（2.28MB，`ID→当前昵称`、`昵称→ID`），缺失或比完整索引旧时回退 `fan_identity_index.json`；`website/redblue_export.py` 改为 `optimize=False`。
- 验证：精简索引独立加载约 0.15s / 38MB，完整索引约 2.4s / 134MB。腾讯云重启 `snh48-web.service` 后，`/api/redblue/data` 0.043–0.065s，按条目导出首次 1.09s、热请求 0.49–0.63s，按昵称导出 0.26–0.30s；`tests/test_identity_index.py`、`tests/test_redblue_ledger_api.py` 等 34 项通过。
- 部署：网站提交 `e8eb28c` 已推送并双端 pull；腾讯云 `snh48-web.service` 22:46:21 重启，MainPID `309238`。阿里云 `snh48-aliyun.service` 后于 2026-11-06 07:32:37 重启（MainPID `1599651`，07:34:48 启动完成），已切换精简索引。

## 2026-11-05 18:00 CST 红蓝台账当前昵称刷新与计分昵称换行（两端已生效）

- 现象：`/business/redblue2026` 仍有“当前昵称”过期。核对口袋ID `8189378947`：身份索引停在 `2026-10-30 06:21:33`，该粉丝在 `2026-10-30 22:00:25` 已改名为「深宅不露Zzzz」；台账两条房间计分分别在 `2026-10-24 14:39:22`、`2026-10-30 19:49:53`，当时计分昵称确实均为「至此间 我知觉流年应有限/」。
- 数据：腾讯云重跑 `scripts/live_monitor/fan_identity_exporter.py`，新索引 `generated_at=2026-11-05 17:57:39`，accounts `35,106`、nicknames `39,742`；经 `dynamic` 组同步到阿里云。两端 `_normalise_entry` 现均输出当前昵称「深宅不露Zzzz」、计分昵称「至此间 我知觉流年应有限/」。后续由 fan-hub `fan-identity-index.timer` 每小时自动重建（`d0c08007c`/`3970b352e`），不再依赖手动重跑。
- 页面：`templates/redblue_ledger_2026.html` 将「计分昵称」从 ID 同一行拆出，显示在 ID 下方单独一行；未改名条目不显示计分昵称。
- 部署：网站仓库提交 `12af20e` 已推送 GitHub，腾讯云已 peer pull；两端仅改模板，Jinja 热加载，无需重启。阿里云 `snh48-aliyun.service` PID `832`，腾讯云 `snh48-web.service` PID `3161496`。
- 验证：`tests/test_redblue_ledger_api.py` 31 项 + `tests/test_password_page_security.py` 3 项通过；`node --check` 通过；两端页面源码均为 `identityNote` 两个独立 `notice` 行。

## 2026-11-04 05:43 CST 红蓝每日柱状图支持悬停/点击查看当天明细（阿里云已生效）

- 需求：鼠标接近或点击每日柱状图的某一天，显示当天积分明细，包括时间、粉丝、来源、礼物或微店档位×数量、分数。
- 数据：`website/redblue_ledger_api.py` 的 `daily_scoring.days[]` 新增 `records`，每条含 `time`、`fan_name`、`source_label`、`scoring_method`、`score`、`note`、`sku_title`、`quantity`、`weidian_score`；仅统计非重复条目，按时间升序。
- 页面：`templates/redblue_ledger_2026.html` 新增跟随鼠标的明细浮层；底部堆叠图和弹窗内各分图/合成图共用；来源分图只显示该来源明细，6 类分图只显示该类别，合成图与底部总图显示当天全部明细；悬停显示、点击固定、点击别处关闭，长列表可滚动。
- 验证：`tests/test_redblue_ledger_api.py` 31 项通过；`node --check` 通过；jsdom 实测悬停、固定、点击外部关闭、来源范围过滤和微店档位×数量显示正常；阿里云 `/api/redblue/data` 已返回 10/30 的 7 条、10/31 的 8 条、11/01 的 15 条当天明细。
- 部署：网站仓库提交 `d9db2a7` 已推送 GitHub；阿里云 `snh48-aliyun.service` PID `3153290`（05:18:35 起），腾讯云模板已通过 peer pull 热加载，`snh48-web.service` 需重启后 `/api/redblue/data` 才会带上 `records`。

## 2026-11-04 04:52 CST 红蓝每日走势弹窗与分图/合成图下载（两端已生效）

- 需求：从“计分来源汇总”进入弹窗，查看每一个积分来源的每日走势，并支持逐张下载和合成图下载。
- 页面：`templates/redblue_ledger_2026.html` 面板头新增“查看每日走势”；弹窗支持“按来源（4：房间/直播/应援会/暗票）”和“按计分来源（6）”两种口径切换；每个来源/类别一张柱状走势卡，各自带下载按钮，底部提供当前口径的合成柱状图及“下载合成图”；导出复用 canvas，单图为 1000×440 逻辑宽 2x PNG，合成图为 1400×620 逻辑宽 2x PNG。
- 验证：`tests/test_redblue_ledger_api.py` 31 项通过；`node --check` 通过；用 jsdom 实测弹窗打开、4/6 视图切换、空数据、单图导出和合成图导出均正常；分图与合成图均按用户要求使用柱状图；阿里云本地页面和腾讯云 `https://cjy.plus/business/redblue2026` 均包含 `openDailyModalBtn`、`dailyViewCategoryBtn`、`dailyCombinedChart`。
- 部署：网站仓库提交 `ea646f4`（弹窗）和 `9115a7c`（柱状图）已推送 GitHub；两端仅改模板和文档，Jinja 模板热加载，无需重启网站服务。

## 2026-11-04 04:52 CST 微店订单页状态筛选改为分组多选（两端已部署）

- 状态筛选改为「全部状态」多选下拉，按 进行中（待付款/待发货/已发货）、已结束（已完成/已关闭）、退款/售后（退款中/已退款）分组；选项保留括号语义；移除状态图例行和「全部退款/售后」选项；多选按并集过滤。
- 部署：网站仓库 `618bd8e`；腾讯云已快进并重启 `snh48-web.service`（PID `2328133`，04:52:16 起）；阿里云模板热加载；两端页面 200。
- 验证：`tests/test_weidian_orders_template.py` 4 项 + `tests/test_weidian_orders_frontend.cjs` 通过；页面含 `statusMenu`/`STATUS_GROUPS`/`data-status-key`，无 `status-legend`、`全部退款/售后`、`statusFilter`。

## 2026-11-04 04:46 CST 微店订单页状态分组与语义说明（两端已部署）

- 状态筛选按状态模型分组：进行中（待付款/待发货/已发货）、已结束（已完成/已关闭）、退款/售后（全部/退款中/已退款）。
- 选项标签增加括号说明；新增状态图例「已完成＝交易成功；已关闭＝未付款/取消；已退款＝已付款后钱已退回买家；退款中＝退款处理中」；状态 pill 增加 title 语义。
- 部署：网站仓库 `b4702c6`（分组基础 `3ccb3c5`）；腾讯云已快进并重启 `snh48-web.service`（PID `2321175`，04:45:40 起）；阿里云模板热加载；两端页面 200。
- 验证：`tests/test_weidian_orders_template.py` 4 项 + `tests/test_weidian_orders_frontend.cjs` 通过。

## 2026-11-04 04:29 CST 微店订单页显示退款中（两端已部署）

- 依赖 fan-hub 新增的 `refund_state`：`statusPill` 在 `refunding` 时在状态下显示「退款中」，退款/售后筛选保持不变。
- 部署：网站仓库 `c487e3a`；腾讯云已快进并重启 `snh48-web.service`（PID `2305285`，04:28:32 起）；阿里云模板热加载（PID `2966893` 不变）；两端页面 200。
- 验证：`tests/test_weidian_orders_template.py` 4 项 + `tests/test_weidian_orders_frontend.cjs` 通过。

## 2026-11-04 04:05 CST 微店订单页状态筛选按 6 态拆分（两端已部署）

- 需求：已关闭与已退款不是同一状态；关闭单仍需采集并可在页面单独筛选；移除「未自动播报」筛选。
- 页面：`statusFilter` 改为 待付款/待发货/已发货/已完成/已关闭/已退款售后；新增 `.pill.closed`/`.pill.refunded`；移除 `broadcast_none` 分支。
- 数据：依赖 fan-hub 新分类（`closed`/`refunded`），当前 91 单：待发货 24、已发货 30、已完成 15、已关闭 21、已退款 1。
- 验证/部署：网站仓库 `22a1da1`；腾讯云已快进并重启 `snh48-web.service`（PID `2284189`，04:04:50 起）；阿里云模板热加载、页面 200；模板/前端测试通过。

## 2026-11-04 03:22 CST 微店订单页增加下单账号多选筛选（两端已部署）

- 需求：`/weidian-orders` 支持按下单账号筛选，且可多选；账号信息只展示脱敏字段。
- 数据：fan-hub canonical store 新增 `buyer_id`、`buyer_phone_masked`（绑定手机只保留 3+4 位），`/api/weidian-orders/data` 原样透出；完整电话/地址仍不进入 store 或页面。
- 页面：新增「全部账号」多选下拉（复选框、全选、清空），每行显示「下单账号」，关键词搜索覆盖 `buyer_id` 与脱敏手机；筛选逻辑抽成纯函数并加前端测试。
- 验证：`tests/test_weidian_orders_template.py` 3 项、`tests/test_weidian_orders_frontend.cjs` 通过；两端 `/weidian-orders` 200 且含 `id="accountMenu"`；阿里云经腾讯云 peer 返回 91 单、91 单带 `buyer_id`，测试账号标签 `177****4879 · ID 2068326847`、`852****0725 · ID 2111166808`。
- 部署：网站仓库功能提交 `568d065`，本运行快照随后单独提交；腾讯云已快进到 `568d065` 并重启 `snh48-web.service`（PID `2237177`，03:10:54 起）；阿里云 `snh48-aliyun.service` 03:10:53 重启，模型加载后 03:19:28 监听（PID `2966893`）。

## 2026-11-04 00:10 CST 红蓝台账增加每日计分来源走势图（阿里云已部署）

- 需求：`/business/redblue2026` 的“计分来源汇总”底部展示从最早记录到今天的每日计分情况，并可下载 PNG。
- 数据：`website/redblue_ledger_api.py` 的 `/api/redblue/data` 新增 `daily_scoring`，按 6 类来源逐日汇总全部非重复条目，从最早记录连续补齐到今天；不受页面筛选影响，`start`/`end`/`days`/`total_score` 一并返回。
- 页面：`templates/redblue_ledger_2026.html` 在计分来源汇总面板底部新增“每日计分走势” canvas，用 6 色堆叠柱按天显示，带图例、坐标轴、每日合计和响应式重绘；面板内“下载 PNG”按钮用同一绘制函数导出 1200×620 逻辑宽、2x 像素的 `红蓝计分_每日计分来源_YYYY-MM-DD.png`。
- 验证：`tests/test_redblue_ledger_api.py` 31 项通过；线上 `/business/redblue2026` 200 且包含 `dailyTrendChart`、`exportDailyBtn`；`/api/redblue/data` 的 `daily_scoring` 为 2026-10-24 至 2026-11-04 连续 12 天，总计 424 分、87 条，6 类 key 完整；Node 模拟画布覆盖桌面、窄屏、40 天、空数据四种绘制路径无异常。
- 部署：网站仓库提交 `7db5968` 已推送 GitHub；阿里云 `snh48-aliyun.service` PID `2795287`（23:53:52 起），腾讯云代码已通过 `peer pull` 快进到 `7db5968`，服务实际重启待腾讯云节点执行。

## 2026-11-03 19:25 CST 导出图用备用字体保留昵称装饰符号（两端）

- 需求：昵称里的特殊装饰符号（如 `嘉菲猫不吃鱼𓈒𓂂𓏸` 的埃及圣书体）要在导出图中保留显示，而不是过滤掉。
- 代码 `18a4bca`：仓库新增 `website/static/fonts/NotoSansEgyptianHieroglyphs-Regular.ttf`（含 OFL 授权文件）；`gift_reply_export.py` 新增字体分段/回退绘制，主字体缺字时自动用备用字体逐字渲染，并按主字体基线对齐；`_display_text()` 可同时接收主字体和备用字体，两者都缺字才过滤；红蓝按昵称/按条目导出和礼物回复导出的昵称均接入。`doc/website_pages.md` 同步。
- 验证：两端 `tests.test_gift_reply_export` + `tests.test_redblue_ledger_api` 共 38 项通过（断言名称含备用字体时完整保留）；阿里云文泉驿、腾讯云 Noto CJK 下 `嘉菲猫不吃鱼𓈒𓂂𓏸` 均完整显示，红蓝按条目图和礼物回复时间线/汇总图已目视确认。
- 部署：网站仓库提交 `18a4bca` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `2570835`（19:24:07 起），腾讯云 `snh48-web.service` PID `1813958`（19:25:15 起）。

## 2026-11-03 15:28 CST 导出图过滤昵称中字体不支持的装饰符号（两端）

- 现象：粉丝昵称 `嘉菲猫不吃鱼𓈒𓂂𓏸` 含埃及圣书体补充平面字符（U+13212/U+13082/U+133F8），CJK 字体无对应字形，导出 PNG 显示为方框。
- 代码 `8acff1a`：`gift_reply_export._display_text()` 新增字体感知过滤——以未分配码位的 `.notdef` 位图作基准，逐字比较并剔除字体缺失字形；礼物回复导出和红蓝按昵称/按条目导出的所有昵称、业务名调用均传入实际字体。`doc/website_pages.md` 同步。
- 验证：两端 `tests.test_gift_reply_export` + `tests.test_redblue_ledger_api` 共 38 项通过（新增 `嘉菲猫不吃鱼𓈒𓂂𓏸` → `嘉菲猫不吃鱼` 用例）；阿里云文泉驿、腾讯云 Noto CJK Bold 均能正确过滤，正常中英文昵称不变。
- 部署：网站仓库提交 `8acff1a` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `2390959`（15:27:27 起），腾讯云 `snh48-web.service` PID `1610936`（15:28:11 起）。

## 2026-11-03 14:41 CST 红蓝按条目导出粉丝昵称不截断（两端）

- 需求：`/business/redblue2026` 按条目导出图中的粉丝昵称列也不能用省略号截断，图片宽度可随最长昵称加宽。
- 代码 `e1fc3ea`：`website/redblue_export.py` 移除昵称列的 `_fit` 截断；先测量所有条目的最长昵称（含未登记 `!` 占位），动态计算昵称列宽和计分徽章起点，再结合最长业务名与最小 820px 决定图片宽度；`doc/website_pages.md` 同步。
- 验证：两端 `tests/test_redblue_ledger_api.py` 30 项通过（新增超长昵称导出宽度断言）；现网按条目导出阿里云宽 947、腾讯云宽 933，最长粉丝昵称 13 字完整显示，最长业务名 `舞蹈房半首+公演 MC 指定动作` 完整显示；无长昵称/业务名时仍保持最小 820px。
- 部署：网站仓库提交 `e1fc3ea` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `2343583`（14:39:21 起），腾讯云 `snh48-web.service` PID `1569479`（14:40:02 起）。

## 2026-11-03 14:18 CST 红蓝按条目导出按业务名动态定宽（两端）

- 需求：`/business/redblue2026` 按条目导出图中的选定业务名必须完整显示，不能用省略号截断；图片宽度可随业务名加宽。
- 代码 `a663cbe`：`website/redblue_export.py` 移除业务名的 `_fit` 截断，先测量所有条目的“分数文案 + 完整业务名”所需宽度，再与标题/筛选行、最小宽度 820px 取最大值作为导出图宽；`doc/website_pages.md` 同步。
- 验证：两端 `tests/test_redblue_ledger_api.py` 29 项通过（新增长业务名导出宽度断言）；现网按条目导出阿里云宽 878、腾讯云宽 869，最长业务名 `舞蹈房半首+公演 MC 指定动作` 完整显示；无业务名时仍保持最小 820px。
- 部署：网站仓库提交 `a663cbe` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `2314372`（14:16:35 起），腾讯云 `snh48-web.service` PID `1552332`（14:17:51 起）。

## 2026-11-02 21:56 CST 红蓝按条目导出新增选定业务名列（两端）

- 需求：`/business/redblue2026` 按条目导出的最后一列新增显示选定业务名，仅显示业务名；多个业务用 `+` 连接。
- 代码 `29bd138`：`website/redblue_export.py` 新增 `_business_text()`，从 `selected_business` / `selected_business_bonus` 去掉“分数-”前缀，按顺序去重后用 `+` 连接；按条目导出宽度 680→820，时间/昵称/计分列略左移，业务名右对齐在最后一列（18px、超长省略），无选定业务的行留空。`doc/website_pages.md` 同步。
- 验证：`tests/test_redblue_ledger_api.py` 28 项通过（新增业务名拼接/去重用例、导出宽度断言 820）。腾讯云实际导出 `/api/redblue/export/entries.png?source=weidian` 宽 820，微店条目最后列显示 `ID 合影+答案之书`；阿里云导出宽 820。
- 部署：网站仓库已推送 GitHub，腾讯云 `git pull` 到 `29bd138`。阿里云 `snh48-aliyun.service` PID `1299055`（21:56 重启，21:58:23 启动完成）；腾讯云 `snh48-web.service` PID `658471`（21:56 起），均 active。

## 2026-11-02 19:15 CST 微店播报名与台账计分昵称规则（两端）

- 需求：微店自动播报只用收货人，不用备注；`/weidian-orders` 可改播报名，改名不改拉取订单/收货人，页面同时显示播报名和收货人，改名后可手动重播相同信息、只换名称；改名后红蓝台账对应条目静态计分昵称同步更新；台账分开展示静态计分昵称和动态当前昵称。
- web 代码 `bebfe30`（含 `5b15579`、`e4ddd8c`）：`_mutator_upsert_weidian()` 的 `raw_name` 取播报名（覆盖 > 收货人），备注永不作为名称，备注中的显式数字 ID 仍可用于身份匹配；新增 `rename_weidian` mutation，`/api/weidian-orders/name` 写完播报名覆盖后立即更新台账 `raw_name`/`weidian.buyer_name`，未锁定身份时按新播报名重算当前昵称。`/api/weidian-orders/data` 同时返回 `receiver_name` 与 `display_name`，页面在两者不同时同时展示。台账主名称（当前昵称）由 `fan_id` + 身份索引 `latest_name` 动态解析，小字「计分昵称」使用静态 `raw_name`。
- fan-hub 代码 `700a4f1aa`（含 `4c6617a2c`）：自动播报只取 `receiver.buyerName`，忽略备注和覆盖名；手动重播使用 播报名覆盖 > 收货人；空值显示「匿名」。
- 验证：`tests/test_redblue_ledger_api.py` 27 项通过（含备注不得成为名称、备注数字 ID 可匹配、改播报名只更新计分昵称、当前昵称动态跟随身份索引）；fan-hub 52 项相关单测通过。腾讯云端到端改名烟测返回 `remote_synced=true`、`redblue.updated=1`，台账 revision `20261102T133345.449366Z-tencent-9fc1c37f2932`；阿里云 `/api/weidian-orders/data` 显示收货人 `杨家宜`、播报名 `EVOL笙`，`/api/redblue/data` 显示计分昵称/当前昵称均为 `EVOL笙`。
- 部署：网站仓库已推送 GitHub，腾讯云 `git pull` 到 `bebfe30`。阿里云 `snh48-aliyun.service` PID `1263908`（21:28 启动，21:33:50 uvicorn ready）；腾讯云 `snh48-web.service` PID `638240`（21:28 起），均 active。
- 存量核对：`M71` 订单 `858027865711661` 显示收货人 `M71`，备注「想要id合影业务谢谢」只保留在备注列；`杨家宜` 订单 `857863000483260` 保留 `/weidian-orders` 手动播报名 `EVOL笙`，收货人仍为 `杨家宜`，`identity_locked=false`。
- 边界：自动播报永远使用收货人；播报名覆盖只影响手动重播和红蓝静态计分昵称，不修改拉取订单。后续昵称变化只影响当前昵称，不改静态计分昵称。

## 2026-11-02 17:31 CST 红蓝台账鸡腿条目双业务选择与微店档位备注（两端）

- 需求：计分方式为鸡腿的条目，“选定的业务”列提供回馈、加赠两个下拉；微店条目备注列改为显示“SKU 档位 × 件数”，不再显示订单号和发货状态。
- 代码：`website/redblue_ledger_api.py` 新增 `selected_business_bonus` 字段（甲鱼回馈存 `selected_business`，鸡腿加赠存 `selected_business_bonus`，分别按 card/bonus 组校验）；微店状态新增 `sku_title`，变更检测补充 `sku_title`/`quantity`。`templates/redblue_ledger_2026.html` 鸡腿行渲染“回馈/加赠”两个下拉，编辑弹窗按计分方式显示加赠下拉；微店备注使用 `sku_title × quantity`，缺 `sku_title` 时用 `score / quantity` 推导档位。
- 部署：网站仓库提交 `b3e0ee1` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `988315`（17:27:51 起），腾讯云 `snh48-web.service` PID `465616`（17:31:17 起）。
- 验证：两端 `tests/test_redblue_ledger_api.py` 23 项通过（含鸡腿加赠字段、微店 SKU 档位变更检测）；两端 `/business/redblue2026` 200，页面包含 `data-business-bonus-select` 和“鸡腿加赠业务”。

## 2026-11-02 17:08 CST 红蓝台账新增“选定的业务”下拉列（两端）

- 需求：`/business/redblue2026` 条目表增加“选定的业务”列，可直接从预设业务中选择，选项命名为“分数-业务名”；可选业务以 2026-10-30 最终交付业务图为准。
- 代码：`website/redblue_ledger_api.py` 新增 `BUSINESS_OPTION_GROUPS` / `BUSINESS_OPTIONS`（甲鱼回馈 22 项、鸡腿计分加赠 7 项，共 29 项），`/api/redblue/data` 返回 `business_options`；条目新增并校验 `selected_business` 字段，新增/编辑/行内 PATCH 均可保存，非法值清空。`templates/redblue_ledger_2026.html` 表格新增“选定的业务”下拉列（按甲鱼回馈/鸡腿加赠分组），编辑弹窗同步增加下拉；表格最小宽度 1120→1280px。
- 部署：网站仓库提交 `3cc0b54` 已推送 GitHub；腾讯云经安全桥对端拉取。阿里云 `snh48-aliyun.service` PID `944427`（16:53:37 起），腾讯云 `snh48-web.service` PID `448365`（17:08:10 起）。
- 验证：两端 `tests/test_redblue_ledger_api.py` 22 项通过（新增业务选项、保存与非法值校验用例）；两端 `/business/redblue2026` 200，页面包含“选定的业务”和 `business-select`；`/api/redblue/data` 的 `business_options` 命名均为“分数-业务名”。

## 2026-11-01 07:14 CST 修复翻牌账号管理特权桥拒绝维护者 ACL 脚本（腾讯云）

- 现象：`https://cjy.plus/flip` 的账号管理接口返回 503「账号管理服务暂时不可用」，`journalctl` 显示 `snh48-web.service` 对 `account-management/latest-job`、`send-sms` 返回 503，特权桥仅记录 `privileged bridge request failed: service=flip`。
- 根因：2026-10-31 00:45 维护者 ACL 给 `cjy-sync`、`codex-feishu` 授予源码 `rwx`，ACL mask 令 `scripts/web/flip_account_admin.py` 的 `st_mode` 变为 `674`；特权桥原信任校验一律拒绝 group 写位，导致 root 侧脚本未执行，网页端把空响应转成 503。`social_credentials_admin.py` 同样受影响。
- 修复：提交 `ddad403` 将桥的信任校验改为「root 所有 + `other` 不可写」，带 group 写位时解析 `system.posix_acl_access`，只允许 root 与受信维护者 `codex-feishu`、`cjy-sync` 的具名写权限，拒绝组条目、`other` 和未知 UID；不再要求回收维护者 ACL 写权限。新增 ACL 解析单测。
- 部署：腾讯云安装新 `/usr/local/libexec/snh48-privileged-bridge-server`（`root:root 0755`）并重启两个桥，`snh48-privileged-bridge-flip.service` PID `3014152`、`snh48-privileged-bridge-social.service` PID `3014153`（均 07:13:16 起）；`snh48-web.service` PID `2967722` 未重启。阿里云不运行这两个桥，仅同步源码。
- 验证：两端 `tests/test_privileged_bridge.py` 6 项通过；以 `snh48-web` 经 Unix Socket 调用 `flip latest-job` 和 `social status` 均返回 `ok:true`；腾讯云 `GET /api/flip-cards/account-management/latest-job?account_id=172884074` 由 503 恢复为 200。真实短信未重复触发。

## 2026-10-31 00:36 CST 红蓝汇总按达成时间排序并改用计分页分布样式（两端）

- 需求：按昵称汇总同分时按“到达该总分的时间”从早到晚排序；网页的计分来源汇总和按昵称汇总仿照计分页礼物分布/送礼用户分布条形样式；不增加 Excel 导出，把“导出按昵称汇总”移到按昵称汇总面板头。
- 排序：`website/redblue_ledger_api.py` 的 `_fan_summary` 新增 `reached_at`（该昵称最后一条计分条目时间），并改为总分降序 → `reached_at` 升序 → 昵称；网页和导出图共用该顺序，不影响条目明细分。
- 页面：`templates/redblue_ledger_2026.html` 两个汇总区改为 `analytics-grid` + `bar-list/bar-row`；计分来源汇总显示 6 类来源分数条，按昵称汇总显示前 10、带进度条和“全部”弹窗；面板头显示人数、`导出按昵称汇总` 和 `全部`，顶部栏只保留“导出按条目”；页面标题仍为“红蓝计分台账 2026”。
- 部署：按红蓝台账未跟踪生产文件现有做法两端直接更新 `website/redblue_ledger_api.py`、`templates/redblue_ledger_2026.html`、`tests/test_redblue_ledger_api.py` 和 `doc/website_pages.md`；阿里云 `snh48-aliyun.service` PID `1592327`（00:36:40 起），腾讯云 `snh48-web.service` PID `1527766`（00:36:42 起）。
- 验证：两端 `tests/test_redblue_ledger_api.py` 20 项 + `tests/test_password_page_security.py` 3 项通过；`/api/redblue/data` 的 36 人 `fan_summary` 同分 `reached_at` 非递减；两端 `/business/redblue2026` 200，包含 `analytics-grid`、`fanModal` 和面板头导出按钮；导出烟测阿里云汇总 699x1802、腾讯云 690x1802，按条目均为 680x2958。

## 2026-10-30 20:02 CST 红蓝台账导出图收窄并改名（两端）

- 需求：按昵称汇总图不再显示已投/待投；卡片保持两列但按最长昵称动态定宽、不截断昵称；按条目图去掉右侧多余空白；导出图标题/页脚/下载名改为“红蓝计分汇总”，按人汇总改称按昵称汇总。
- 代码：`website/redblue_export.py` 按昵称汇总改为两列动态卡片宽度（当前数据 699px 图宽、卡片约 319px、高 76px），移除已投/待投行，名字不再 `_fit` 截断；按条目宽度 820->680、列位重排；导出标题/页脚改为“红蓝计分汇总”。`templates/redblue_ledger_2026.html` 的按钮、面板和状态文案改为“按昵称汇总”，下载文件名改为 `红蓝计分汇总_*`，页面标题保持“红蓝计分台账 2026”。
- 部署：按红蓝台账未跟踪生产文件现有做法两端直接更新 `website/redblue_export.py`、`templates/redblue_ledger_2026.html`、`tests/test_redblue_ledger_api.py` 和 `doc/website_pages.md`；阿里云 `snh48-aliyun.service` PID `1264823`（20:02:24 起），腾讯云 `snh48-web.service` PID `1330889`（20:02:25 起）。
- 验证：两端 `tests/test_redblue_ledger_api.py` 19 项通过；两端 `/business/redblue2026` 200，页面包含“导出按昵称汇总”和新下载名；按昵称汇总导出为动态宽度（阿里云 699x1802、腾讯云 690x1802），按条目均为 680x2958，标题/页脚为“红蓝计分汇总”。

## 2026-10-30 06:38 CST 修正身份索引最新昵称并重建（两端）

- 根因：`scripts/live_monitor/fan_identity_exporter.py` 的 `merge_sender_identity` 把所有历史昵称都按账号级 `latest_seen` 写入，导致同一账号多个昵称并列最新；`latest_name` 又按写入顺序取最后一个，于是 Miyosa 被错标成「无糖芬达yp」。另外台账旧 `aliases` 会覆盖身份索引，进一步放大错误。
- 修复：身份索引改为按每个昵称自己的 `latest_seen` 计算，并用「时间 + 权威最新优先级 + 出现次数」比较；`redblue_ledger_api._resolve_identity` 改为身份索引优先、alias 只在索引缺失时兜底，避免旧 alias 覆盖新昵称。
- 重建：腾讯云已重跑身份索引，覆盖到 2026-10-30，accounts `29,039`、nicknames `32,036`；文件经 `dynamic` 组同步到阿里云。Miyosa（ID `166789134`）最新昵称恢复为 `Miyosa`；当前仅剩 `拾蹄悦(悦悦🌲)` → `拾蹄悦(悦悦)` 这一处真实改名。
- 部署：腾讯云 `snh48-web.service` PID `737080`、阿里云 `snh48-aliyun.service` PID `486540`（均 06:37 起）。
- 验证：`tests/test_fan_identity_exporter.py` 2 项、网站 `tests/test_redblue_ledger_api.py` 19 项 + `tests/test_score_gifts_sender_export.py` 4 项通过；两端两个页面 200，Miyosa 在 score 页和 redblue 页均显示为 Miyosa。

## 2026-10-30 05:53 CST 计分页与红蓝台账统一使用最新口袋昵称（两端）

- 现象：`/score/2026-winter` 与 `/business/redblue2026` 名单看起来不一致；核对后 31 个口袋ID完全一致，差异是 score 页显示计分时昵称（如「等雨晴_」），红蓝台账显示身份索引里的最新昵称（如「茉莉雨_」），并非名单缺失或错人。
- 口径：两个页面主名称统一显示最新口袋昵称；计分时昵称不同时，在昵称下方/汇总卡备注「计分昵称」，导出同时保留「当前昵称 / 计分昵称」两列。
- 代码：`website/score_gifts_api.py` 新增身份索引缓存和 `current_sender_name`，详情、送礼用户分布、`/summary` 和导出均带最新昵称；`sender` 筛选同时匹配最新昵称、计分昵称和口袋ID。`templates/score_gifts.html` 主名称改用 `current_sender_name` 并备注计分昵称。`website/redblue_ledger_api.py` 的按人汇总新增 `score_names` / `score_name`，`templates/redblue_ledger_2026.html` 在 ID 行和汇总卡备注计分昵称。
- 部署：腾讯云 `snh48-web.service` PID `703592`、阿里云 `snh48-aliyun.service` PID `361693`（均 05:52 起）。
- 验证：`tests/test_redblue_ledger_api.py` 19 项、`tests/test_score_gifts_sender_export.py` 4 项通过；两端 `/score/2026-winter`、`/business/redblue2026` 200；score 页 41 条，分布中「等雨晴_」显示为「茉莉雨_」并备注计分昵称，红蓝台账同样备注；筛选 `茉莉雨_` 和 `等雨晴_` 都能命中同一人。

## 2026-10-30 05:01 CST 红蓝台账 6 类计分来源汇总与鸡腿礼物识别（两端）

- 需求：房间/直播在 11/11–15（及后续鸡腿窗口）可投带计分属性的红蓝鸡腿礼物；网页显示 6 类“来源×方式”汇总；导出图不再标来源，只按计分卡/鸡腿标记并按人汇总。
- 口径：房间/直播默认计分卡；官方鸡腿礼物名可能不含“鸡腿”，改为按“口袋48鸡腿价格 > 0 且有计分属性”识别（读 `score_gift_authority.json` 的 `melee`/`money`，不再写死 350），礼物名含“鸡腿”或命中 `REDBLUE_CHICKEN_GIFT_NAMES`/`IDS` 也直接记鸡腿；弦月回响等计分卡礼物保持计分卡；应援会/微店=鸡腿，暗票=计分卡。
- 代码：`website/config.py` 新增 `REDBLUE_CHICKEN_GIFT_NAMES` / `REDBLUE_CHICKEN_GIFT_KEYWORDS`；`redblue_ledger_api.py` 为条目保存/派生 `scoring_method`，同步时按礼物名判定，`_fan_summary` 新增 `scoring` 汇总；`templates/redblue_ledger_2026.html` 新增 6 类汇总面板；`redblue_export.py` 两类导出图只显示计分方式并按人汇总计分卡/鸡腿；按条目图移除右侧业务状态列，宽度从 1000px 收窄到 820px。
- 部署：腾讯云 `snh48-web.service` PID `667513`（05:00 起），阿里云 `snh48-aliyun.service` PID `308712`（05:00 起，模型加载后监听 8000）；未跟踪生产文件按现有做法两端直接更新。
- 验证：两端 `tests/test_redblue_ledger_api.py` 18 项通过；fan-hub `tests/test_all_members_score_exporter.py` 6 项通过；两端 `/business/redblue2026` 200，按条目导出 820px、按人 1000px；现网 44 条仍为房间/直播计分卡、微店鸡腿；腾讯云已重建权威清单并保留 `melee`/`money`，阿里云已重跑 2026-winter score 数据（41 条、弦月回响 73 分），`/score/2026-winter` 200。

## 2026-10-30 04:25 CST 红蓝台账新增计分方式列与导出来源细化（两端）

- 需求：`/business/redblue2026` 需要区分条目是鸡腿还是计分卡计分；导出两类 PNG 的来源标签要细化为「房间·计分卡」「直播·计分卡」「应援会·鸡腿」「暗票·计分卡」。
- 口径：微店/应援会=鸡腿；房间/直播=计分卡（弦月回响）；暗票按用户确认统一=计分卡。计分方式由 `source` 派生，不新增台账存储字段，历史条目自动生效。
- 代码：`website/redblue_ledger_api.py` 新增 `SCORING_METHOD_LABELS` / `SCORING_SOURCE_LABELS`，`_normalise_entry` 输出 `scoring_method` 和 `source_scoring_label`，导出筛选文案同步细化；`website/templates/redblue_ledger_2026.html` 表格新增「计分方式」列，按人汇总来源文案同步；`website/redblue_export.py` 两类 PNG 的来源徽章改为细化标签。
- 部署：按红蓝台账未跟踪生产文件现有做法两端直接更新 API/导出/模板/测试；腾讯云 `snh48-web.service` PID `640597`（04:24:19 起），阿里云 `snh48-aliyun.service` PID `267753`（04:24:19 起，模型加载后 04:24:47 左右监听 8000）。
- 验证：两端 `tests/test_redblue_ledger_api.py` 14 项通过；两端 `/business/redblue2026` 200；`/api/redblue/data` 44 条，房间 33 / 直播 8 全部 `计分卡`，微店 3 全部 `鸡腿`，标签集合与预期一致；本地渲染两类 PNG 无重叠（1000px 宽）。

## 2026-10-27 01:05 CST 红蓝台账导出重做与页面轻量化（两端）

- 导出字体过大的根因：`website/redblue_export.py` 复用了 `gift_reply_export._font()`，该函数内部固定 `SCALE=2`，但 redblue 画布只有 860px 且未按 2x 缩放，所有字体被放大 2 倍并互相重叠。`gift_reply_export._font()` 增加可选 `scale` 参数（默认仍为 2），redblue 导出显式使用 1x。
- 重做版式：`redblue_export.py` 改为 1000px 逻辑宽、单栏时间线、标题 50px、正文 20–27px，浅紫底/白卡片/紫色标题，对齐交接包 `礼物回复时间线_近三周_20261021.png` 的观感；按人汇总同步修正字号。导出的“按条目”图从 512KB / 约 6s（cjy.plus）降到 334KB / 约 1.2–1.4s，本地生成约 0.55s。
- 未登记昵称：不再使用红色昵称；名字统一 `NAME` 色和同字号，只在名字后保留低对比度圆圈 `!`（浅紫圆 + 灰紫叹号）。底部说明同步保留。
- 页面：移除 `.topbar` 的 `backdrop-filter: blur(12px)`，减少华为 ArkWeb 等浏览器的高开销合成；导出按钮点击后显示“生成中…”并写入状态栏，避免误以为卡死。
- 登录态：`_COOKIE_SECRET` 从每次启动随机改为 600 权限持久密钥文件 `private_handover/web_state/redblue_ledger_cookie_secret`，网站重启后红蓝台账 Cookie 不再失效；首次登录创建，密钥不进 Git、不打印。`REDBLUE_COOKIE_SECRET_PATH` 可覆盖默认路径。
- 部署：按红蓝台账/网站未跟踪生产文件做法两端直接更新 `website/redblue_export.py`、`redblue_ledger_api.py`、`config.py`、`gift_reply_export.py`、`templates/redblue_ledger_2026.html` 和测试；腾讯云 `snh48-web.service` PID `1348424`（00:58:36 起），阿里云 `snh48-aliyun.service` PID `38119`（00:59:00 起，01:02:42 完成监听）。两端密钥文件均为 `snh48-web:snh48-web 0600`。
- 验证：`tests/test_redblue_ledger_api.py` 13 项、`tests/test_gift_reply_export.py` 7 项通过（腾讯云合并跑 20 项通过）；两端 `/business/redblue2026` 200；导出图均为 1000px 宽 PNG（按条目约 334KB、按人汇总约 172KB）。
- 注意：本次重启前签发的旧红蓝 Cookie 会失效一次；重新登录后，后续重启将保留登录态。

## 2026-10-26 23:56 CST 红蓝台账微店计分按档位×份数修正（两端）

- 问题：`/business/redblue2026` 的微店条目把订单 `quantity` 直接当分数；`99份×1`、总价 `2598.75` 的订单只记 1 分，应为 99 分（或总价 ÷ 26.25）。
- 修复：`website/redblue_ledger_api.py` 新增 `_weidian_order_score`——优先用 worker 输出的 `score`（SKU 档位数字 × 购买份数），否则订单总价 ÷ `REDBLUE_WEIDIAN_UNIT_PRICE`（默认 26.25），最后回退 `quantity`；`_mutator_upsert_weidian` 写入台账和 `_weidian_changed` 变更检测共用该口径。`website/config.py` 增加 `REDBLUE_WEIDIAN_UNIT_PRICE`；fan-hub `redblue_worker.py` 同步新增 `sku_title` / `score`。
- 部署：按红蓝台账现有“未跟踪生产文件两端直接更新”做法，直接同步 API/config/测试到腾讯云；重启腾讯云 `snh48-web.service`（PID `1295537`，23:48:04 起）和阿里云 `snh48-aliyun.service`（PID `4153546`，23:47:57 起，模型加载完成后 23:55:18 监听 8000）。
- 台账修正：腾讯云微店同步 job `5441f61e973d4dc9a3700764ae248cac` apply 返回 `updated=2`、`replicated=true`；两节点台账南方有嘉木 `1.0`、徐某人 `99.0`。`/api/redblue/data`：`entry_count=29`、`total_score=141.0`、`settled_score=42.0`、`pending_score=99.0`。
- 验证：`tests/test_redblue_ledger_api.py` 12 项、fan-hub `tests/test_redblue_worker.py` 4 项，两端通过；两端 `/business/redblue2026` 200。
- 源文件状态：`website/redblue_ledger_api.py`、`website/config.py`、测试文件仍按现有红蓝台账做法作为未跟踪生产文件两端直接更新；本运行快照按节点本地维护。

## 2026-10-25 04:57 CST 红蓝台账密码改为 HttpOnly Cookie，移除浏览器密码缓存

- 问题：`/business/redblue2026` 前端把明文管理密码写入 `sessionStorage("redblue_ledger_password_2026")`，刷新自动复用；密码框使用 `autocomplete="current-password"`，且 `REDBLUE_LEDGER_PASSWORD` 默认复用业务管理/礼物回复密码，浏览器存储泄露会连带多个后台页。
- 修复：后端新增 `POST /api/redblue/login`、`POST /api/redblue/logout`；登录成功签发 `HttpOnly; Secure; SameSite=Strict; Path=/api/redblue` 的 HMAC Cookie（24h），`/verify`、数据、导出、轮询、同步均支持 Cookie；`X-Redblue-Password` 保留旧客户端兼容。前端登录改为提交 JSON 到 `/login`，启动时用 `/verify` 检查 Cookie，401/403 回登录，登出调用服务端接口；删除 sessionStorage 写入并在启动时清理旧 key，密码框改 `autocomplete="new-password"`。
- 加固：新增 `doc/security/password_page_best_practices.md` 和 `tests/test_password_page_security.py`（禁止 `current-password`、禁止 Web Storage 保存密码、检查 redblue 使用 `/login`）；`AGENTS.md`、`doc/website_pages.md`、`doc/security/security_baseline.md` 已更新。旧 `tests/test_password_login_feedback.py` 中“记忆页应从 localStorage 读取密码”的过期断言已改为只允许 `removeItem` 清理。
- 验证：临时工作区和两端定向单测通过（redblue 10 项；密码页静态/反馈 7 项）；两端公网烟测：页面 200、源码无 `sessionStorage.setItem`、未登录 `/api/redblue/data` 401、登录 200 且 Set-Cookie 含 HttpOnly/Secure/SameSite=strict/Path=/api/redblue、verify/data/export 200、logout 200、登出后 401；阿里云 04:56:44 自动同步 `/api/redblue/sync/room-live` 仍 200（旧请求头兼容）。
- 部署：腾讯云 `snh48-web.service` PID `3483721`，04:54:43 启动，NRestarts=0；阿里云 `snh48-aliyun.service` PID `1456413`，04:55:35 启动，NRestarts=3（首次重启因 unit 的 `ReadWritePaths` 指向缺失的 `/home/snh48_web/transcript_analyze/logs_backup` 失败，已按 `deploy/harden_aliyun_runtime_permissions.sh` 规则创建 `snh48-web:snh48-web 0700` 目录后恢复）。两端页面模板改动由 Jinja 自动重载，除服务重启外无需额外构建。
- 注意：旧版本用户浏览器里可能仍有 `redblue_ledger_password_2026`，新页面首次加载会删除该 key；因 Cookie 为新会话，用户需重新输入一次密码。
- 源文件状态：`website/redblue_ledger_api.py`、`website/templates/redblue_ledger_2026.html`、`tests/test_redblue_ledger_api.py` 仍是未跟踪生产文件，按现有红蓝台账做法两端直接更新；最佳实践文档、静态护栏、AGENTS 和基线文档已纳入 GitHub；本运行快照按节点本地维护。

## 2026-10-25 03:57 CST 礼物回复导出改为 2x 渲染（长图放大更清晰）

- 背景：上一版已把时间线改回单栏、回复情况保持双栏并对齐本地字号，但导出仍是 1000px 位图；长图在手机相册/聊天里被整体缩小后仍不清楚。
- 修复：`website/gift_reply_export.py` 改为逻辑 1000px 布局 + 2x 像素密度绘制，输出 2000px 宽；字体、间距、徽标全部按 2x 渲染，版式与本地图保持一致。
- 稳定性：新增 105MP 安全像素预算（`MAX_EXPORT_PIXELS`），超出时返回 413“导出图过长，请缩小日期范围或增加筛选条件后重试”，避免超长图拖垮腾讯云小内存节点；`gift_replies_api.py` 已把该异常转成 413。
- 验证：7 项单测两端通过；腾讯云 60 天时间线（461 条）实测 `2000×50808`、6.6MB、14.4 秒、峰值 RSS 475MB，无 swap；阿里云同等数据 17.5 秒通过；90 天范围按预算返回 413。2x 模式下按当前送礼密度约 60 天以内可单张导出。
- 部署：两端同步 `website/gift_reply_export.py`、`website/gift_replies_api.py`、测试与文档；阿里云重启 `snh48-aliyun.service`（PID `1374884`，03:56:47 启动），腾讯云重启 `snh48-web.service`（PID `3436561`，03:56:48 启动）。

## 2026-10-25 03:35 CST 礼物回复导出改回本地版式（时间线单栏、字号对齐）

- 问题：10/23 上线的导出文件在工作区被改成时间线双栏、正文字号 11–16px；与交接包本地图（时间线单栏、正文 20–24px、标题 50px）相比同宽 1000px 下内容被压缩，看起来明显更小更糊；回复情况虽仍为双栏，但字号也偏小。
- 修复：`website/gift_reply_export.py` 时间线恢复单栏并按本地 HTML 字号重排（标题 50、日期 27、正文 24、时间/徽标 20）；回复情况保持双栏，把姓名/正文/时间/徽标字号提升到 28/24/20；表头、分区标题、页脚和卡片间距同步对齐本地图。
- 验证：`tests/test_gift_reply_export.py` 新增单栏与双栏回归用例，6 项在两端通过；两端接口实测 200，时间线 `1000×5478`、回复情况 `1000×4773`（2026-10-18 至 10-25 筛选）。
- 部署：两端 `website/gift_reply_export.py` 与测试文件为未提交生产改动，直接单文件更新；阿里云重启 `snh48-aliyun.service`（PID `1349301`，03:34:07 启动），腾讯云重启 `snh48-web.service`（PID `3419293`，03:34:08 启动）。
- 文档：`doc/website_pages.md` 已注明时间线导出单栏、回复情况导出双栏及 1000px/正文 20–24px 版式。

## 2026-10-25 02:12 CST 红蓝台账微店商品名同步（两端）

- 问题：微店订单 `itemName` 是下单快照，商品改名后不会回写；台账同步未比较 `item_name`，旧商品名会长期留在台账 JSON。
- 修复：`website/redblue_ledger_api.py` 的 `_weidian_changed` 增加 `item_name` 比较；fan-hub `redblue_worker.py` 同步订单时用 `item.getInfo` 当前商品名覆盖快照，获取失败时任务报错、不回退旧名。两处文件当前仍是未跟踪生产文件，按节点直接更新。
- 部署：腾讯云重启 `snh48-web.service`（PID `3354246`），阿里云重启 `snh48-aliyun.service`（PID `1259393`）；腾讯云触发微店同步 + apply，台账 revision `20261024T180914.805163Z-tencent-effa785b5ca0`，阿里云副本已同步。
- 验证：`tests/test_redblue_ledger_api.py` 7 项通过；两端 `/business/redblue2026` 返回 200，`/api/redblue/data` 的微店条目商品名为 `【陈嘉仪·红蓝歌会】75折红蓝1分鸡腿礼物`。

## 2026-10-23 19:35 CST 礼物回复页新增 PNG 导出（两端）

- 功能：`/room/gifts` 新增「导出时间线图」，按当前已应用的筛选（回复状态/礼物/用户/回复类型/日期）导出逐条时间线 PNG；`/room/gift-senders` 新增「导出回复情况图」，按当前筛选导出按送礼人聚合的两列卡片 PNG。两页导出都不受分页影响，按钮显示生成中/失败/已开始下载。
- 接口：`GET /api/gift-replies/export/timeline`、`GET /api/gift-replies/export/senders`，沿用 `X-Gift-Replies-Password`；时间线上限 1500 条、回复情况上限 3000 条礼物，超限返回 413 并提示缩小日期；进程内单飞锁，避免并发大图渲染。
- 渲染：`website/gift_reply_export.py` 使用 Pillow（新增依赖 `Pillow==12.2.0`）+ 系统 CJK 字体（阿里云文泉驿、腾讯云 Noto），红=待回/绿=已回；非陈嘉仪媒体不下载；emoji/组合符号在导出前清理，避免方框。
- 部署：网站提交 `1ab2399` 已推送，两端 `git pull --ff-only`；两端网站 venv 已安装 Pillow 12.2.0；腾讯云 `snh48-web.service` PID `2133643`、`19:33:30` 启动，阿里云 `snh48-aliyun.service` PID `1596481`、`19:33:58` 启动，均 active/running、`NRestarts=0`。
- 烟测：两端本机 8000 端口未带密码均 401；带密码请求时间线/回复情况均 200 `image/png`（阿里云 968,871 / 819,985 字节；腾讯云回复情况 810,999 字节）。`tests/test_gift_reply_export.py` 4 项、原有 `tests/test_gift_replies_api.py` 10 项全部通过；两页模板内联 JS 通过 `node --check`。
- 文档：`doc/website_pages.md` 已登记两个导出接口与条数上限。

## 2026-10-20 飞书操作阿里云本地化：同步组移除通知中继与 xlsx outbox

- 用户决策废除"阿里云经腾讯云 relay 代执行飞书操作"：安全桥 Bot 与通知转发 Bot 凭据已部署阿里云本地（600/700 权限，scp 直传），阿里云的通知推送与 xlsx 云文档推送均由本机直推（阿里云新增 `feishu-notification-forwarder.service`，以腾讯云投递状态为种子启动）。
- 同步变更：正向 `hub` 组移除通知中心三件套（`notification_center.md`/`notification_state.json`/`notification_events.jsonl`，此前腾讯云权威覆盖阿里云，2026-10-20 起两端各自维护本机副本、互不同步）；反向 `notify` 组移除 `notification_events.jsonl` 中继（落地 `aliyun_relay/`）与 `xlsx_push_request.json` outbox，仅保留 `notifications/codex_runs/`。改动文件：`deploy/sync-from-tencent.sh`、`deploy/sync-from-aliyun.sh`、`deploy/sync-from-aliyun-if-changed.sh`。
- 腾讯云侧 `aliyun-notification-relay.timer` 与 `xlsx-push-relay.timer` 已 `disable --now`（脚本/unit 保留作兜底）；relay 停前已确认无 in-flight（relay offset=源文件大小、腾讯云 forwarder 无 pending）。
- 验证：阿里云 `push_xlsx_to_cloud()` 实测 returncode 0 直推云文档成功；阿里云写入 severity=info 测试通知由本机 forwarder 直推成功（腾讯云 events 与该通知投递记录均为 0 命中，无双推），测后已 resolve。

## 2026-10-16 fan-hub 数据加工迁移阿里云，同步拓扑改为双向

- 背景：fan-hub 数据加工/AI 生成迁到阿里云（`root@8.210.188.184`），采集留腾讯云。派生数据路径不变，产地变为阿里云。
- 正向（腾讯云→阿里云，阿里云 cron 每分钟 `sync-from-tencent-if-changed.sh` 不变）：`core` 移除 `schedule_record` 三个 CSV；`dynamic` 移除 `gift_replies/`、`audio_transcripts/`、`score_gifts/` 与 `flip_data/{web,audio,video}/`（转为阿里云产出，继续正拉会覆盖新数据）；新增 `hub` 组投递 fan-hub 自动化输入（`social_record/weibo/*.jsonl`、`social_record/bilibili/*.csv`、`notifications/admin_feedback_center.md`、`notifications/codex_social_event_queue.json`、`config/accounts.json`、`config/koudai_token.json`、`private_handover/移交包/行程组/`）。hub 组含 Token/账号配置，保持源端 root 权限，不套用网站组只读接收参数；行程组正向用 `--update` 防旧副本回滚。
- 反向（阿里云→腾讯云）：新增 `deploy/sync-from-aliyun.sh` 与 `deploy/sync-from-aliyun-if-changed.sh`，腾讯云 root cron 每分钟运行，日志 `/var/log/snh48/sync-from-aliyun.log`。`derived` 组回流行程 CSV 与 `schedule_record/backups/`、`gift_replies/`、`audio_transcripts/`、`score_gifts/`、`room_record/pk_scores/`、`flip_data/{web,audio,video}/`、`assistant_schedule_draft_state.json`、`移交包/行程组/`（2026-10-16 起阿里云权威，腾讯云不再写）；`notify` 组回流 `notifications/codex_runs/`（供 COS 归档）与 `notification_events.jsonl`（落地 `notifications/aliyun_relay/notification_events.jsonl`，绝不覆盖腾讯云本地同名文件）。
- 反向所有目录不用 `--delete`、rsync 统一加 `--update` 防回滚（迁移窗口内腾讯云本地文件更新时不被阿里云旧副本覆盖）、源缺失只跳过不删本地文件；`score_gifts` 仍排除 `live_business_fulfillments.json` 与 `.*.lock`（可写业务状态走腾讯云权威版本化复制）；`flip_data/web` 反向保留 `accounts.json` 最后原子提交（本地更新时保留本地）。
- 部署：阿里云 `/home/snh48_web/deploy/` 原正向脚本备份为 `.bak.premigration` 后经 GitHub 对齐；腾讯云 crontab 新增反向行，既有条目全部保留。两端分组清单快照存 `/root/.config/server-migration/20261016_tencent_to_aliyun/w5a_sync_topology.log`。

## 2026-10-16 房间消息页切换 jsonl 事实表，messages_shards 分片退役

- 网站提交 `53359e5`：房间消息 API 数据源优先级改为 jsonl 事实表（fan-hub `metadata/messages.jsonl` 主文件 + `messages_YYYY-MM.jsonl` 月封存）→ 历史分片 → 退役 CSV；新增 `ROOM_MESSAGES_METADATA_DIR` 与 `ROOM_MESSAGES_REBUILD_MIN_INTERVAL_SECONDS`（默认 20s 最小重建间隔，防实时逐条写入引发重建抖动）；jsonl-only 类型（DELETE/PRESENT/QCHAT_* 等）不进网站视图。
- 同步脚本：`sync-from-tencent.sh` 移除 messages_shards 同步步骤与建目录项（jsonl 事实表已由 core 组"房间原始数据"覆盖）；`sync-from-tencent-if-changed.sh` 指纹清单移除 `messages.csv`（已退役删除）和 `messages_shards`。
- 分片退役：腾讯云 root crontab 的 `shard_exporter_guard.sh` 行已删除、watch 进程已停止；两端 `messages_shards/` 本地副本已删除；最终快照归档 COS `raw/backups/critical/2026-10-16/messages_shards_final_20261016.tar.gz`（同目录另有 `messages_final_20261016.csv.gz`）。
- 部署：腾讯云 `snh48-web.service` 重启后 `/room-messages` 200、API 401（密码保护正常）；阿里云经 `deploy.py deploy aliyun` 到 `53359e5`，`metadata/` 12 个月文件与主文件已在阿里云就位，`/api/room-messages/verify` 401 正常。
- `doc/security/security_baseline.md` 无分片/房间消息同步条目，本次无需变更；数据契约详见 fan-hub `doc/room_messages_data_contract.md`。

## 2026-10-11 口袋48榜单快照同步

- `dynamic` 组新增 `pocket48_ranks/陈嘉仪_161808449/`（陈嘉仪口袋48榜单快照：粉丝鸡腿贡献榜、鸡腿年榜等，公开只读小 JSONL，排除 `.collector.lock`）；指纹脚本 `sync-from-tencent-if-changed.sh` 同步加入该目录。
- 数据源为腾讯云 fan-hub 新增的 `pocket48-rank-collector.timer`（每小时一次）；采集器注册表和运行快照见 fan-hub `doc/codex/project_profile.md` 与 `doc/running_status.md`。
- 未新增网页/API/公开入口，网站服务无需重启；阿里云 cron 拉取机制不变。

## 2026-10-08 公演互动文本同步

- 同步实现提交 `22e688a` 已推送，阿里云通过GitHub fast-forward更新，原每分钟主动拉取cron保持不变；未重启网站服务。
- core组新增 `performance_record/陈嘉仪_161808449/` 文本白名单，238文件、189,202字节，腾讯云/阿里云逐文件SHA-256清单汇总一致：`ffc9fbfdff57fdc41af3afb9e069256ea5fe44bee511d21516fb6e5723c40f1f`。历史元数据79场；公演视频、配置、凭据、collector状态和PK诊断不进入同步。
- shell语法与Git差异检查通过；同步日志 `/tmp/pocket48-performance-sync-20261008.log`。没有新增网页/API/公开入口，前端构建和站点重启不适用。采集器、COS和飞书投递的详细快照在fan-hub `doc/running_status.md`，避免重复维护PID。


更新日期：2026-09-13 CST +0800

2026-09-13 08:45:02 CST 腾讯云验收后，阿里云通过 GitHub 部署网站提交 `9690c08`，`snh48-aliyun.service` 定向重启后 PID `639411`、`active/running`、`NRestarts=0`。阿里云主动同步已完成，根索引 `live_record/live_index.csv` 与网站所需场次元数据、官方弹幕、封面及其他网站数据均已更新；跨云同步排除本地 `live.ts`/`live.capture.ts` 大型备份文件。公网 `https://cjy.xn--6qq986b3xl/api/timeline/live-pushes?limit=1` 返回最新场次 `1305673277881782272`、时间 `2026-09-12 23:19:28`、回放和弹幕均可用；同步日志显示 08:44:02 完成、08:45:02 后无源变更。网站部署烟测全部通过。

2026-09-13 08:12:11 CST 腾讯云先行部署网站提交 `a2648b5`：统一直播索引中 `push_bj` 为空的场次改用 `live_ctime_bj`、`start_bj` 回退，最新场次 `1305673277881782272` 已出现在 `/api/timeline/live-pushes` 首条并带有回放、弹幕和封面；回放页日期同样支持回退。跨云 core 同步补充根目录 `live_record/live_index.csv`，避免阿里云索引停留在旧版本。网站相关 108 项 unittest、Python 编译、同步脚本语法检查和 diff 检查通过；`snh48-web.service` 定向重启后 PID `409594`、`active/running`、`NRestarts=0`，本机 `/timeline`、最新回放页和直播 API 均返回 200。阿里云尚未同步，等待腾讯云页面验收后再执行。

2026-09-11 08:53:20 CST 用户确认后，阿里云通过 `python3 deploy/deploy.py deploy aliyun` 从 `6a4ac81` 快进到 `e0b63be`（包含电台展示 `b48c5c9` 和本地弹幕路径修复 `d0ecf47`）。`snh48-aliyun.service` 于 08:47:54 定向重启，PID `546579`、active/running、`NRestarts=0`，启动后的 warning..emerg 日志为空；QA 返回 `ready=true`、`loading=false`。公网 8/22 回放为直播/1556 条弹幕，9/9 回放为电台/2522 条弹幕，HTML 播放模式均匹配；以阿里云实际网站账号在禁止网络和缓存回退的检查中，两份本地 LRC 均可直接读取。部署标准页面/API/图片代理烟测全部通过；TLS 证书有效至 2026-11-01，`certbot.timer` active，未调整证书或 Nginx。阿里云工作树保持干净；本轮未主动执行跨云数据同步，使用现有自动拉取的数据。腾讯云同期完成用户授权的 swap 12→4 GiB 调整，根盘可用约 16.63 GiB，网站 PID `2787612` 未变；配置与详细恢复记录见 fan-hub `doc/running_status.md`。网站 profile 和资源迁移说明已更新，未改变数据拓扑、QA 节点策略或应用健康检查范围。

2026-09-11 08:37:54 CST 腾讯云先行部署 `b48c5c9`、`d0ecf47`：时间轴按 `live_type=2` 标记电台并提供“收听回放”；回放页以封面承载同步弹幕。修复 `danmu_local_path` 相对 fan-hub 根目录时重复拼接 `live_push_replays`，两场回放以 `snh48-web` 账号在禁止远端请求/缓存回退的验证中均直接读取本地 LRC。`snh48-web.service` 于 08:31:21 定向重启，PID `2787612`、`active/running`、`NRestarts=0`；QA 继续关闭。公网时间轴、两场回放及弹幕 API 返回 200，2026-08-22 为直播/1556 条弹幕，2026-09-09 为电台/2522 条弹幕；`/qa` 为 503、`/api/qa/status` 为 404。3 项 Python 契约测试、时间轴标签前端回归、源与产物 JS/内联脚本语法检查及构建通过；使用兼容音频样本驱动真实弹幕的浏览器验证通过播放、暂停、弹幕开关和 390px 移动布局，无页面 JS 错误。本机 Chromium 不支持原媒体的 AAC SourceBuffer，因此原 HLS 实际声音等待用户浏览器试听，未宣称机器端真实媒体播放通过。阿里云未部署，等待腾讯云用户验收。页面说明和 profile 已同步；未新增服务、调度器、路径或改变拓扑/健康检查范围。

2026-09-10 13:10:40 阿里云完成网站提交 `33b7f29` 部署：通过 `python3 deploy/deploy.py deploy aliyun` 从 GitHub 快进并定向重启 `snh48-aliyun.service`。阿里云主 PID `453606`，`active/running`、`NRestarts=0`，`ActiveEnterTimestamp=2026-09-10 13:07:38 CST`；启动日志显示 QA 知识库正常加载并完成启动，无新增 warning..emerg 异常。公网 `https://cjy.xn--6qq986b3xl/memories` 返回 200，未带密码数据接口返回 401，错误密码返回 403；页面登录框可见且内容区初始隐藏。腾讯云先行版本保持不变。

2026-09-10 12:33:37 腾讯云先行部署网站提交 `77ab96f`：记忆页恢复进入访问密码，`/api/memories/data` 和 `/api/memories/submit` 均要求 `X-Memories-Password`；通过阿里云现有跨云 SSH 通道完成腾讯云 `git pull` 和 `snh48-web.service` 定向重启。腾讯云主 PID `2069716`，`active/running`、`NRestarts=0`，`ActiveEnterTimestamp=2026-09-10 12:32:34 CST`；启动日志仅有既有 FastAPI `on_event` 弃用提示，无新增 warning..emerg 异常。公网 `https://cjy.plus/memories` 返回 200，未带密码数据接口返回 401，错误密码返回 403，正确密码返回 200；页面登录框可见且内容区初始隐藏。阿里云中文域名尚未同步本提交，仍待腾讯云验收后确认再发布。


2026-09-05 03:31 迁移计划调整：阿里云公开站继续保留现网观察至 2026-10-01，迁移实施窗口调整为 2026-10-01 至 2026-10-05，共五天。新主机物理内存不再预设为某个固定值，10 月 1 日依据连续访问/资源数据、QA 冷启动峰值、并发问答体验、OOM 事件和 swap I/O，从云厂商可购买的最低档逐级验证，选择通过全部门槛的最小档位；必要的 swap 作为操作系统单独配置，不计入云主机内存规格。五天窗口完成后旧阿里云仍保留 48--72 小时回滚观察。

2026-09-05 03:26 双服务器容量观察期确认：阿里云公开站迁移暂缓，保留现网并观察 2026-09-05 至 2026-10-05 的连续数据。网站仓库提交 `16a6eee` / `c1ab409` 已推送并部署到两端；`snh48-website-metrics.timer` 每 5 分钟继续运行，快照新增网站服务 RSS、启动以来峰值 RSS（`VmHWM`）、进程 swap、虚拟内存和线程数，网站主服务未重启。当前阿里云 `snh48-aliyun.service` QA 为 ready、RSS 约 1.05 GiB、启动以来 HWM 约 2.32 GiB、无 swap；腾讯云 `snh48-web.service` RSS 约 7 MiB、进程 swap 约 43 MiB，主机 12 GiB swap 已用约 2.5 GiB。迁移和降配均等待一个月数据及 QA 冷启动验收；本次未修改 DNS、QA 开关或业务同步拓扑。

2026-09-05 02:38:53 双服务器单文件删除同步修复完成：网站仓库提交 `3a3eeeb` 已由腾讯云和阿里云快进到同一版本。腾讯云 `snh48-web.service`、阿里云 `snh48-aliyun.service` 以及两端 `snh48-website-metrics.timer`、`snh48-website-log-archive.timer` 均为 `active`；阿里云执行 `bash deploy/sync-from-tencent.sh core` 成功，事件主 CSV、兼容副本和社交时间轴均完成拉取。已确认 `website/data/manual_events.csv` 是旧时间轴端点遗留文件，内容已由 fan-hub 权威事件 CSV 接管，阿里云副本已删除。三个 core 单文件现在在源端确认删除后会删除阿里云副本，SSH 检查失败则不执行删除；目录同步继续使用 `--delete`/manifest 延迟清理。网站服务无需重启。

2026-09-04 22:58 双服务器观测告警和可读服务别名部署完成：网站提交 `b3d4c55` 已由腾讯云和阿里云拉取；腾讯云 `snh48-web.service` / `snh48-web-tencent-private.service` 主 PID `1432070`、`active/running`、`NRestarts=0`，阿里云 `snh48-aliyun.service` / `snh48-web-aliyun-public.service` 主 PID `3946438`、`active/running`、`NRestarts=0`。两端观测 metrics/log-archive timer 均 enabled、active；最近归档检查分别成功且日志约 893 KiB / 2.3 MiB，远低于 1 GiB，未删除文件。归档 fail-closed 告警改为 root 仅通过 `snh48-web` 所有权写入本地 action-inbox/outbox，不读取网站 `.env` 或直接使用 root SSH；阿里云故障/恢复烟测事件已复制到腾讯云，`feishu-feedback-chat-forwarder.service` PID `1432193` 仍 `active/running`，成功发送 1 条告警和 1 条恢复卡片，当前状态计数 `sent=20`。阿里云首页、时间轴和 `/api/qa/status` 返回 200；旧 unit 名称继续作为兼容入口，可读别名不产生第二个进程。

2026-09-04 04:07 双服务器观测与日志留存机制上线：网站提交 `ae517a9` 已部署到阿里云公开站，观测实现（CPU 基线与小时峰值）提交 `d934a95`、文档收尾提交 `576bc02` / `957ce3e` / `dac05e6` 已由两端拉取；`snh48-aliyun` 主 PID `3844437`、`active/running`、`NRestarts=0`，腾讯云 `snh48-web` 主 PID `3994901`、`active/running`、`NRestarts=0`。两端均启用并启动 `snh48-website-metrics.timer`（每 5 分钟）和 `snh48-website-log-archive.timer`（每日 03:20），最近一次 metrics/archive oneshot 均 `Result=success`。统计分别写入 `/var/lib/snh48-web/metrics/tencent/` 和 `/var/lib/snh48-web/metrics/aliyun/`；最终快照显示腾讯云 2 逻辑 CPU、约 1.92 GiB 内存、根盘 50 GiB 已用 89.53%（可用约 5.23 GiB），阿里云 4 逻辑 CPU、约 7.10 GiB 内存、根盘 68.53 GiB 已用 44.09%（可用约 35.33 GiB）。当前 Nginx 日志总量腾讯云约 587 KiB、阿里云约 1.34 MiB，均未达到 1 GiB 归档阈值，未删除文件；腾讯云可使用 fan-hub 私有 COS 配置，阿里云因不复制敏感凭据保持 fail-closed。观测脚本、systemd unit、logrotate 十亿份高保留规则和两种迁移边界文档已提交；阿里云首页、时间轴及部署标准烟测返回 200，预先存在的未跟踪运行文件保持原样。

2026-09-03 04:35 腾讯云先验部署网站提交 `6ee2077`：通过阿里云现有跨云 SSH 通道确认腾讯云工作树只保留既有未跟踪 `website/data/runtime_backups/`，未覆盖运行数据；腾讯云 `snh48-web.service` 定向重启后主 PID `3994901`、`active/running`、`NRestarts=0`，共享状态复制线程正常启动，`SITE_MAINTENANCE_MODE=false`（默认不改变线上写入）。本机首页和时间轴返回 200，公网 `https://cjy.plus/`、`/timeline`、`/score-gifts`、`/memories`、`/ob` 均返回 200，启动后 warning..emerg 日志为空。网站新增迁移维护守卫、节点显示名配置和迁移/容量记录文档；本地虚拟环境全量 97 项 unittest 通过。阿里云尚未部署，等待腾讯云用户验证后再同步。

2026-08-26 06:41 阿里云 QA 长期修复完成：网站提交 `242c514` 已由 `python3 deploy/deploy.py deploy aliyun` 通过 GitHub 快进部署并重启 `snh48-aliyun.service`。此前 `/api/qa/status` 长期停留在 loading，根因为 Chroma/Pydantic 在导入时按当前工作目录读取项目 `.env`，而生产 `.env` 按安全基线为 `root:root 0600`，导致 `snh48-web` 进程导入 QA 依赖时报 `PermissionError`；早期后台线程还会把该失败表现为不可恢复的 loading。当前 QA 初始化改为服务启动阶段执行，并在导入 Chroma 时切换到服务账号可访问的 HOME，同时关闭 Chroma 后续 dotenv 探测，失败会记录 traceback 并返回可重试状态；懒加载仍有超时、代次保护和阶段状态。阿里云模型缓存保持在 `/var/lib/snh48-web/.cache/huggingface`，未修改 `.env` 权限或输出任何密钥。

线上复核：阿里云 checkout `242c514`，PID `2779192`，`active/running`、`NRestarts=0`，启动时间 06:40:38；本机和公网 `/api/qa/status` 均返回 `ready=true`、`loading=false`、`segment_count=292700`，首页、`/qa`、时间轴、Room、礼物、上麦回放、翻牌、计分礼物、静态资源、时间轴 API 和图片代理 smoke tests 全部通过。腾讯云未重启，继续按 `QA_ENABLED=false` 停用 QA；阿里云既有未跟踪运行文件保持原样。

2026-08-25 01:42 用户确认腾讯云后，阿里云网站通过 GitHub 从 `1dae795` 快进部署到 `358a65b`，重启 `snh48-aliyun.service` 后 PID `2625375`、active/running、`NRestarts=0`，01:41:27 启动，warning..emerg 日志为空；既有未跟踪 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 原样保留。部署工具的首页、时间轴、Room 礼物、综合回礼、上麦回放、翻牌、计分礼物、静态资源、时间轴 API、QA 和图片代理烟测全部通过。阿里云翻牌账号管理仍为 200/disabled，没有安装腾讯云专用账号桥、转录 venv 或敏感凭据；鉴权后账号 `172884074` 返回 373 条记录、341 条转录，媒体 1-byte Range 为 206，腾讯云与阿里云 `accounts.json` 和账号 JSON SHA-256 分别一致。阿里云安全基线全部通过。公网和本机 Certbot 证书均有效至 2026-11-01，约剩 68 天，`certbot.timer` 与月度提醒 cron 正常，本轮未修改证书或 Nginx。

2026-08-25 01:27 腾讯云修复网页验证码登录后的翻牌刷新失败，并完成用户本次账号任务。根因不是登录或 Token：任务已成功拉取 373 条记录和 10 个新语音，随后因 2026-08-24 网站虚拟环境精简后不再含 PyTorch 而在转录阶段退出；隔离桥又先后暴露出系统 `/tmp` 只读下 PyTorch 临时目录和账号清单提交锁未放行。fan-hub 提交 `892210b5`、`cae965c8`、`d12f0937`、`5c3be361` 建立 `/home/snh48-fan-hub/venv-transcription` 专用 CPU 转录环境，将翻牌和房间语音任务从网站 venv 解耦，通过 root-only 共享锁串行加载本地 `whisper-base`，并让失败提示包含具体阶段、重试时清除旧错误。网站提交 `2466aaf`、`d9d2a32`、`eaa2c62`、`6eff9c5` 保持桥服务系统 `/tmp` 只读，只精确放行短信限速、翻牌更新、转录串行化和账号清单提交四个 `root:root 0600` 锁，并把 PyTorch 临时文件限定到 `notifications/flip_web_admin/tmp` 私有目录；Hugging Face 强制离线，不上传音频或下载模型。

同轮重跑任务 `afe1f1bf1177067f575f0c80638de0a3` 最终为 200/completed：账号 `172884074` 更新为总计 373、已回复 347、待回复 7、退款 19，新增 10 条语音全部转录成功，语音转录达到 341/341；`accounts.json`、账号 JSON 和兼容副本于 01:23 同批提交。公网登录、最新任务和数据接口均为 200。受同一依赖漂移影响的 `room-audio-transcripts.timer` 已切到专用环境并恢复 active/waiting，积压 7/7 条补齐，最近 oneshot 为 success。fan-hub 15 项、网站 Python 12 项和前端 1 项专项测试通过；三个网站/桥服务 active、`NRestarts=0`、warning..emerg 日志为空，社交凭据桥仍返回微博/抖音/B站已配置状态且不含 Cookie，腾讯云安全基线全通过。阿里云代码未部署，本轮未手动触发跨云数据同步，等待腾讯云用户验收。

2026-08-25 00:40 腾讯云修复翻牌网页发送验证码返回 `操作失败（OSError）`：根因为 `snh48-privileged-bridge-flip.service` 的 `ProtectSystem=strict` 令 `/tmp` 只读，而短信限速和后台刷新仍需打开 fan-hub 的两个宿主机共享锁。提交 `aa6ac92` 在加固脚本中预创建并收紧 `/tmp/snh48-fan-hub-flip-web-rate.lock`、`/tmp/snh48-fan-hub-flip-update.lock` 为 `root:root 0600`，服务单元仅把这两个文件精确挂载为可写，没有开放整个 `/tmp`，网站进程的挂载仍为只读。两个锁在翻牌桥命名空间内均通过与生产脚本相同的 `open("a+")` 和 `flock` 验证；三个服务均 enabled、active/running、`NRestarts=0` 且重启后 warning..emerg 日志为空。公网翻牌登录、账号管理状态、最近任务接口分别为 200、200/enabled、200/completed；未重复触发真实短信。Python 12 项、前端 1 项专项测试、shell/systemd 语法和腾讯云主机安全基线全部通过。阿里云未同步，继续等待腾讯云用户验收。

2026-08-25 00:11 腾讯云翻牌账号与社交 Cookie 管理桥完成安全隔离修复：提交 `7197232` 将原先从 `snh48-web.service` 内调用的两个 sudo 包装器替换为 `snh48-privileged-bridge-flip.service` 和 `snh48-privileged-bridge-social.service`。两个 root 服务只通过 `root:snh48-web 0660` Unix Socket 接受固定命令并校验对端 UID；网页进程恢复 `NoNewPrivileges=yes`、空 capability、`ProtectHome=read-only`，在实际 mount namespace 中看到 fan-hub `config/` 和 `flip_data/` 为只读，只有对应桥服务看到明确列出的运行目录为可写。新桥启动并切换网站成功后，生产 `/etc/sudoers.d/snh48-web` 和旧包装器已删除，旧配置仅保存在 root `0700` 的 `/var/lib/snh48-web/bridge-migration-backup-20260825/` 供紧急回滚。

同轮线上验收中，三个服务均为 enabled、active/running、`NRestarts=0`，启动后 warning..emerg 日志为空；腾讯云翻牌管理能力为 true，最近任务从原先 503 恢复为 200/completed，账号 `172884074` 仍为 365 条记录；社交凭据状态从 503 恢复为 200，返回微博、抖音、B站配置槽位且不含 Cookie。真实 Cookie 替换和短信发送未用伪值触发，避免改变外部账号状态；固定命令、敏感值不进入 argv/响应、Socket 端到端传输和两个 API 的 14 项专项测试全部通过。全量 85 项测试通过 83 项，剩余 2 项为主分支既有礼物页模板文案/结构断言不一致，本次未修改对应文件。手机端翻牌“跳到最新”常驻条件同时恢复并通过前端测试。主机安全基线全部通过；阿里云尚未同步，等待腾讯云用户验收。

2026-08-24 19:37 腾讯云网站完成无 QA 运行时精简：提交 `9d9bd33` 将 `website/requirements.txt` 收敛为基础网站依赖，并让部署目标通过 `qa_enabled` 决定是否克隆知识库和安装 QA 依赖；腾讯云 systemd 写路径不再引用 `transcript_analyze/`，阿里云配置和运行环境未改。61 MiB 精简 venv 先在独立 18080 端口验证，再于最终 `/home/snh48_web/venv` 路径重建并只重启 `snh48-web.service`；当前 PID `257039`、`NRestarts=0`，`pip` 解释器路径与依赖完整性检查通过。本机和公网首页、`/timeline` 为 200，`/qa` 为本机 503，`/api/qa/status` 为 404，QA 页面不含阿里云域名或 IP；进程未加载 Torch、ChromaDB、sentence-transformers 或知识库模块。确认阿里云 QA 状态接口仍为 200 后，腾讯云删除 5.3 GiB 旧 venv 和 2.1 GiB `transcript_analyze/`，保留空 gitlink 目录以维持主仓库状态干净；全量 81 项 unittest 中 78 项通过，3 项为既有翻牌/礼物模板断言不一致。

2026-08-24 18:39 跨云回放安全遗留项完成：网站提交 `ce5fbf1` 增加独立只读监控 Token、stdin-only 原子密钥写入工具、双服务器迁移加固手册和只读基线验证器；提交 `5b8756c` 进一步修复阿里云同步后只读副本的权限漂移。Token 只保存在阿里云 `/home/snh48_web/.env` 与腾讯云 `/etc/snh48/room-voice-cross-cloud-health.env`，均为 root `0600`，没有写入 Git、日志或文档；页面密码仍可各自独立，监控 Token 不能登录或签发 Cookie。阿里云只为加载新环境变量重启 `snh48-aliyun.service`，当前 PID `2588462`、`2026-08-24 18:28:50` 启动、`NRestarts=0`；图片代理 PID `2523186` 保持不变。部署同步脚本和权限修复时没有再次重启网站或其他服务，没有重启整机，也没有订阅 Ubuntu Pro。

同轮确认旧版 root rsync 原子替换会把 `room_voice_replays/manifest.json` 恢复为网站账号不可读的 `root:root 0640`，这是认证修复后跨云检查一度报告“阿里云尚未出现最新会话”的原因。拉取与手动推送脚本现对每个接收操作强制 `root:snh48-web`、目录 `0750`、文件 `0640`；执行一次现有树修复后，18:39 的自动 cron 再次完整拉取 `core,dynamic`，清单仍为 `root:snh48-web 0640` 且 `snh48-web` 可读。跨云检查返回 `ok=true`，最新会话 `rv_20260821_235512_main_36376935_f22821` 的消息、兼容版和原始音质版均通过鉴权与 1-byte Range 校验；腾讯云总健康检查返回 `ok=true`、`missing=[]`。双服务器只读基线验证器均通过；从腾讯云独立探测阿里云 8000/8899 均超时，密码专用 SSH 仍被 `Permission denied (publickey)` 拒绝。

2026-08-24 06:07 最终复核：`snh48-aliyun.service` 当前 PID `2526577`、05:48:12 启动、`NRestarts=0`；journal 显示前一进程正常完成 application shutdown，新进程启动后标准页面/API 烟测通过，无崩溃重启。图片代理 PID 仍为 `2523186`、`NRestarts=0`。`sshd -T` 再次确认仅公钥认证；未知 HTTP/HTTPS Host 均为空响应，公网直连 8000/8899 均超时。最终文档快进到阿里云时未重启任何服务。

2026-08-24 05:38:42 阿里云安全整改完成：安全代码基线 `c066bc0`，既有未跟踪运行文件 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 均保留。`snh48-aliyun.service` enabled、active/running，PID `2523593`，05:24:49 启动，实际以 `snh48-web` UID/GID `998` 运行，`NoNewPrivs=1`、`UMask=0077`，FastAPI 只监听 `127.0.0.1:8000`；`snh48-weibo-img-proxy.service` enabled、active/running，PID `2523186`，05:22:26 启动，使用 systemd `DynamicUser`、`NoNewPrivs=1`，只监听 `127.0.0.1:8899`。运行数据目录/文件全部通过 0700/0600 检查，`.env` 为 root 0600，`/var/log/snh48` 为 root 0700 且内部文件均 0600。共享状态 outbox 为 0，action inbox 为 13 个已有事件。

同轮安全验收：笔记本、台式机公钥登录均在修改前成功；阿里云 sshd 已改为 `AuthenticationMethods publickey`，密码专用回归被 `Permission denied (publickey)` 拒绝。网站专用跨云公钥指纹 `SHA256:3ZfFX2P7LY0ElfIRQe3BPqZ3kHl5xXYF8yptL6ATqKE` 在腾讯云绑定 `mutate inbox-put` 强制命令，交互 shell 探测被 403 拒绝。Nginx `nginx -t` 通过并已 reload，未知 HTTP/HTTPS Host 均返回 444 空响应，服务头仅显示 `nginx` 而无版本号；裸域名、`www`、`/complaint` 为 200，`/openapi.json` 为 404。真实微博图片首次代理为 `MISS`、第二次为 `HIT`，公网直连 8000/8899 均超时。FastAPI 依赖已对齐 `fastapi 0.141.1`、`starlette 1.6.0`、`Jinja2 3.1.6`、`python-multipart 0.0.32`，`pip check` 通过。Ubuntu Main/Restricted 无待 unattended 安全更新；22 项 Universe/Multiverse ESM 需 Ubuntu Pro，本轮未绑定；既往 `libc6` 更新仍留有 reboot-required 标记，本轮未重启整机。

2026-08-24 06:01 腾讯云总健康检查除既有“房间上麦回放跨云同步”外全部健康；该项因阿里云业务接口 HTTP 403 连续失败 11 次。它早于本轮整改存在，阿里云网站、图片代理和公网烟测正常，作为独立跨云业务鉴权遗留项处理。

2026-08-24 04:20 腾讯云 QA 已停用并清理本地知识库：网站功能提交 `8fe2171` 通过节点级 `QA_ENABLED=false` 不再注册 `/api/qa/*`、不执行 QA 归档维护或模型预热；`/qa` 只返回本机 503 未启用页面，响应中不含阿里云域名、IP 或跳转，两个网站没有 QA 互链。腾讯云只重启 `snh48-web.service`，PID `3814128`、`active/running`、`NRestarts=0`；公网首页和 `/timeline` 为 200，`/qa` 为 503，`/api/qa/config`、`/api/qa/status` 为 404。确认阿里云 `snh48-aliyun` 仍为 `active/running`、PID `2512204`、`NRestarts=0` 且 QA 配置接口为 200 后，删除腾讯云 `chroma_db` 约 2.8G、`segment_store.json` 约 265M、`kb_description.txt` 和 root 旧嵌入模型缓存约 391M；磁盘可用空间从 2.9G 增至 6.3G。腾讯云 94 份历史问答归档约 92M 经内容清单前后校验一致，独有转录、下载记录、子项目源码和 Git 历史均保留；阿里云未重启、未删数据。目标 unittest 与编译检查通过；全量 76 项 unittest 中另有 3 项既有翻牌/礼物模板断言失败，与本次 QA 文件无关。

2026-08-24 00:49 Room 与礼物页筛选、最新定位和移动导航完成双云无中断发布：功能提交 `311061b` 已在腾讯云和阿里云生效。Room、礼物明细和综合回礼页把日期输入值与已应用值分离，只有点击“筛选”才提交日期；无新数据时“跳到最新”只平滑滚动，有新数据时才提示并加载；Room 按钮层级高于消息卡片，两个礼物页移动端互链固定在右上、筛选位于右侧第二行，综合回礼客服入口固定右下。本地 Playwright 390×844 视口确认 Room 点击 80ms 时仍在滚动、最终精确到列表底部，礼物两页无新数据点击不发 API 请求且导航无重叠。腾讯云 checkout 为 `311061b`，screen `3479202.snh48`、Python PID `3479212` 保持运行；阿里云执行 `python3 deploy/deploy.py deploy aliyun --no-restart` 快进到 `311061b`，`snh48-aliyun` 保持 `active/running`，PID `2485782`、`NRestarts=0`。两端 `/room`、`/room/gifts`、`/room/gift-senders` 均返回 200，部署工具标准烟测全部通过；未修改 Python、环境变量、Nginx、后台服务、数据同步拓扑或健康检查范围，既有运行文件与并行中的 OB 模板编辑保持原样。

2026-08-23 22:55 Room 日期筛选与移动端最新导航完成双云无中断发布：功能提交 `c9517ad` 已在腾讯云和阿里云生效。腾讯云通过阿里云既有免密链路复核时已位于目标提交，保留 screen `3352583.snh48` 与 Python PID `3352588`；阿里云执行 `python3 deploy/deploy.py deploy aliyun --no-restart` 从 `fe2d153` 快进到目标提交，`snh48-aliyun` 保持 `active/running`，PID `2468260`、`NRestarts=0`。两端公网 `/room`、`/room/gift-senders` 均返回 200，页面源码包含日期只暂存到点击“筛选”后再请求、Room 明确滚动到消息底部、送礼人页移动端顶部操作重排及固定客服入口；部署工具的首页、时间轴、礼物、上麦回放、翻牌、计分礼物、静态资源和关键 API 烟测全部通过。未修改 Python、环境变量、Nginx、后台服务、数据同步拓扑或健康检查范围；阿里云既有未跟踪运行文件保持原样。

2026-08-23 23:51 OB 3D IP 关系图完成阿里云部署：用户确认腾讯云阶段体验后，`python3 deploy/deploy.py deploy aliyun` 通过 GitHub 将网站快进到提交 `238aa0a`，重启 `snh48-aliyun`，主 PID `2485782`、状态 `active`。公网 `/ob` 返回 200，页面包含 Three.js `0.159.0`、`ForceGraph3D`、3D Canvas 与二维回退；鉴权 `/api/ob/data` 返回 1304 个成员组、583 个 IP 节点、49 条共享成员边，统计为 37 个稳定档案、1267 个旧会话和 172 条逐次访问。部署工具标准烟测、服务日志复核和公网 HTTPS 证书检查均通过，证书至 2026-11-01 有效；未修改 Nginx、环境变量或数据同步拓扑，阿里云既有未跟踪运行文件保持原样。

2026-08-23 23:40 OB 3D IP 关系图完成腾讯云阶段发布：网站提交 `0d59e6f` 已由腾讯云本机 `git pull --ff-only` 加载并重启 screen `3479202.snh48`，Python PID `3479212`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。`/api/ob/data` 新增 `ip_network_graph`，当前返回 193 个 IP 节点、19 条共享成员边，边权按共同浏览器档案/旧会话数量计算，历史关联保留低置信度标记；稳定档案、旧会话和逐次访问统计不变。公网 `/ob` 返回 200，页面包含 Three.js/`ForceGraph3D`、3D Canvas 和二维回退；`/timeline` 返回 200。本地 Playwright 桌面 1440×1000 与手机 390×844 均确认 Canvas 创建且截图非空；阿里云尚未同步，等待用户体验腾讯云后确认。

2026-08-23 20:36 OB 交互式 IP 网络图完成阿里云部署：用户确认腾讯云验收后，`python3 deploy/deploy.py deploy aliyun` 已将网站同步到提交 `5c37569`，重启 `snh48-aliyun`，远端主 PID `2468260`、状态 `active`。公网页面 `/ob` 返回 200，包含网络图节点、人物成员视图和会话悬浮逻辑；鉴权 `/api/ob/data` 返回 1302 个原始成员、542 个 IP 关联组，统计为 35 个稳定档案、1267 个旧会话和 164 条逐次访问。首页、时间轴、Room、礼物、上麦回放、翻牌、计分礼物、静态资源及关键 API 均通过部署工具烟测。证书公网检查为 OK，证书至 2026-11-01 有效，未修改证书或 Nginx；阿里云既有未跟踪运行文件保持原样。

2026-08-23 20:32 上麦回放 iPhone 播放态与顶部导航完成双云发布：网站提交 `3207f8c`（切换会话/分段前显式 `audio.pause()`，避免 iPhone Safari 保留旧的“正在播放”外观）和 `282309a`（移除顶部“退出”，改为 `/room` 的“返回 Room”链接）已推送。腾讯云通过阿里云既有免密链路快进并重启 screen `3352583.snh48`，Python PID `3352588`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`；阿里云由 `python3 deploy/deploy.py deploy aliyun` 快进并重启 `snh48-aliyun`，PID `2466759`，`active/running`、`NRestarts=0`，20:32:34 启动。两端公网 `/radio` 返回 200、未登录 `/api/room-voice-replays/sessions` 返回 401，页面均包含 `roomPageLink` 和 `pauseBeforeMediaChange`，不再包含 `logoutBtn`；阿里云既有未跟踪运行文件保持原样。桌面端布局未改动，移动端筛选仍默认收起。

2026-08-23 19:45 OB 交互式 IP 网络图完成腾讯云阶段发布：网站提交 `549acc5` 已推送并由腾讯云本机 `git pull --ff-only` 加载；现有 screen `3300763.snh48`、Python PID `3300772` 保持运行，无需重启。OB 默认显示按 IP 节点大小表达关联成员数的网络图，点击节点显示浏览器档案/旧会话人物视图，悬停成员或会话显示访问摘要；原关联组列表保留为切换视图。公网 `/ob` 返回 200，页面包含 `networkVisualization`、`ipNetworkSvg` 和会话悬浮逻辑；鉴权 `/api/ob/data` 返回 702 个原始成员、180 个 IP 关联组，统计为 99 个稳定档案、603 个旧会话和 216 条逐次访问；`/timeline` 返回 200。未加入城市、坐标、主动指纹或轨迹分析；阿里云尚未同步，等待用户确认腾讯云效果。

2026-08-23 19:31 OB IP 关联组展示完成腾讯云阶段发布：网站提交 `bb6ca36` 已推送并加载到腾讯云 screen `3300763.snh48`、Python PID `3300772`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。OB 新增仅用于整理展示的 `association_groups`，按稳定浏览器档案和旧会话共享 IP 的传递关系生成组，不改变估计访客数、稳定档案数、旧会话数或逐次访问记录；旧会话使用历史 IP 参与并明确标记限制。公网 `/ob` 返回 200，鉴权 `/api/ob/data` 返回 702 个原始成员、180 个关联组，统计仍为 99 个稳定档案、603 个旧会话和 215 条逐次访问；`/timeline` 返回 200。前端已改为默认收起的关联组总览，展开后显示成员行并可进入原详情弹窗。阿里云尚未同步，等待腾讯云验收。

2026-08-23 18:42:44 阿里云上麦回放页面完成部署复核：`python3 deploy/deploy.py deploy aliyun` 已完成 Git 快进、`snh48-aliyun` 重启和目标页面烟测；远端随后自动合并文档提交，当前 checkout 为 `33f37be`，其中保留上麦回放移动端 `filterPanel` 改动。阿里云 PID `2454218`，`active/running`、`NRestarts=0`，18:41:01 启动；公网页面 `/radio` 返回 200、未登录 `/api/room-voice-replays/sessions` 返回 401。远端既有未跟踪运行文件保持原样。

2026-08-23 18:39:59 阿里云部署网站提交 `778161a`：修复移动端日期筛选首次选择卡死风险，统一受保护页面的初始鉴权错误状态，并为 Room、礼物明细、送礼人和翻牌页调整“跳到最新”显示逻辑。`python3 deploy/deploy.py deploy aliyun` 已完成 Git 快进、`snh48-aliyun` 重启和首页、时间轴、礼物、上麦、翻牌、静态资源及关键 API 烟测；阿里云 PID `2453662`，`active/running`，`NRestarts=0`。远端既有未跟踪的 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 保持原样；腾讯云未重启。

2026-08-23 18:11:33 腾讯云阶段发布上麦回放移动端筛选收纳：网站提交 `6e0cfaf` 已加载并重启 screen `3233514.snh48`，Python PID `3233519`；腾讯云 `/radio` 返回 200，未登录 `/api/room-voice-replays/sessions` 返回 401，页面已包含移动端默认关闭的 `filterPanel`。桌面端仍保留左侧会话列表；阿里云尚未同步，等待腾讯云验收。

2026-08-23 17:49 修复 Room 筛选弹窗打开后背景消息持续上滑：网站提交 `8957188` 已部署到阿里云并重启 `snh48-aliyun`。筛选锁定期间暂停全局滚动触发的前后页加载和填充视口任务，关闭弹窗恢复滚动位置期间抑制一帧误触发；线上 390×844 移动视口打开弹窗等待 2 秒，消息数保持 100，新增数据请求为 0，关闭后滚动位置从 0 恢复到原位置 5000。阿里云 PID `2448602`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 17:37 Room 页移动端导航位置与筛选滚动边界完成阿里云发布：网站提交 `d49590e` 已重启 `snh48-aliyun`。`综合回礼`、`上麦回放`位于顶部第一行，`筛选`位于统计行；390×844 移动视口测量分别为 `y=10` 与 `y=52`。打开筛选后背景 `window.scrollY` 锁定为 0，遮罩阻止触摸穿透，筛选卡片内部保持可滚动。阿里云 PID `2446857`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 17:19 修复 Room 页面移动端顶部栏消失：网站提交 `e1ebd96` 已部署到阿里云并重启 `snh48-aliyun`。移动端改为仅由 `html` 承担文档滚动，`body` 保持 `overflow: visible`，避免 `sticky` 顶部栏绑定到不实际滚动的 body 容器；390×844 移动视口登录后页面滚到底部时，顶部栏实际 `y=0`、`position: sticky`，线上截图和 DOM 计算样式复核通过。阿里云 PID `2444525`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 16:55 阿里云完成网站导航、移动端固定顶部栏、筛选弹窗和公开记忆页改造部署：网站提交 `ed020aa` 已由 `python3 deploy/deploy.py deploy aliyun` 快进并重启 `snh48-aliyun`。阿里云主 PID `2441690`，`active/running`、`NRestarts=0`；首页、`/timeline`、`/room/gifts`、`/room/gift-senders`、`/room-voice-replays`、`/flip-cards`、`/score-gifts`、静态资源、时间轴/QA/图片代理接口均通过部署烟测，公开 `/memories` 与 `/api/memories/data` 返回 200，公开记录不包含内部审核字段或 `platform_id`。阿里云既有未跟踪 `website/data/manual_events.csv`、`website/data/runtime_backups/` 与 `website/static/js/timeline.js.bak` 保持原样；本次未同步 `snh48-fan-hub` 数据、Cookie、Token、`.env` 或其他密钥。腾讯云未重启，继续运行其现有 screen 进程。

2026-08-23 16:44 观察页设备识别改为服务器签发档案 Cookie 并完成双服务器发布：网站提交 `9c3afec` 已推送。tracker 不再从浏览器存储生成或提交 `visitor_id`；首次 `page_view` 由服务端签发 HMAC 校验的 `ob_device_profile` HttpOnly Cookie，后续由服务端读取，仍只记录页面、当时 IP 和粗粒度 User-Agent 设备标签，不加入主动指纹、城市或经纬度。腾讯云因本机回连公网 SSH 无可用密钥，按既有方式确认本地 checkout 为 `9c3afec` 后重启 screen `3152206.snh48`、Python PID `3152211`，公网 `/ob`、`/timeline` 和事件接口通过；阿里云由部署工具拉取同一提交并重启 `snh48-aliyun`，PID `2440328`、active/running。两端首次事件均返回带 `HttpOnly`、`Secure` 的 `ob_device_profile`，带回同一 Cookie 的第二次事件不重新签发；两端 `/ob` 均为 200，静态 tracker 均不含 `localStorage`。

2026-08-23 10:48 社交凭据管理完成双服务器运行复核：功能提交 `149a8ca` 和非主节点隐藏修复 `437d0d6` 已部署。腾讯云 screen `2878064.snh48`、Python PID `2878066` 于 10:46:43 重启；公网 `https://cjy.plus/social-credentials-admin` 返回 200，密码登录及鉴权状态接口通过，只返回微博、抖音、B站各槽位状态，不回显 Cookie；页面与 API 使用 `no-store`，页面设置 `noindex/nofollow` 且没有站内入口。严格桥接脚本只允许腾讯云主节点在验证新 Cookie 成功后原子替换。阿里云 `snh48-aliyun`、PID `2407221` 于 10:47:48 重启，隐藏页面返回 404、API 返回 403，不能读取或更新凭据。两端 `/api/timeline/schedule` 均为 130 条，并确认不返回 2026-08-23 错误行程。

2026-08-23 10:36 客服聊天长等待更新完成双服务器发布：网站提交 `369e4e0` 已推送，两端 Gift Senders 与 OB 客服从固定 1 秒轮询改为最多约 25 秒的可恢复长等待请求，新事件通常在服务端 200 毫秒检查周期内返回；隔离 HTTP 烟测从发消息到等待请求返回约 247 毫秒。腾讯云 screen `2867975.snh48`、Python PID `2867981` 于 10:35:40 重启；阿里云 `snh48-aliyun`、PID `2405889` 于 10:36:43 重启，均已通过 `/room`、`/room/gift-senders`、`/ob` 和新客服接口烟测。飞书反馈转发服务不受网站接口实现变化影响，保持 PID `2613036`、active/running、`NRestarts=0`，未重启。

2026-08-22 19:45 翻牌成员筛选、独立更新状态和底部合并刷新入口完成腾讯云阶段发布：网站提交 `64e3d7f`、fan-hub 提交 `5309e0a` 已推送，腾讯云 screen 重启为 `2303857.snh48`、Python PID `2303871`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。账号 `172884074 / xxgg2333` 的 19:05 网页登录刷新任务已于 19:11 成功完成，Token 安全复查有效；公网账号数据为 schema v4 共 365 条、331 条语音转录，成员为陈嘉仪 364 条和闫娜 1 条，默认成员键为陈嘉仪 `161808449`。页面顶部旧“最新”按钮已移除；筛选默认陈嘉仪，逐条头像为“嘉仪”或其他成员完整姓名；独立更新状态弹窗可收起并恢复，底部按钮同时重新加载数据和跳到最新。受保护数据版本和最近任务 API、媒体 Range 206、伪造跨站 POST 403、账号清单无手机号/Token/验证码字段均通过。阿里云代码尚未部署，等待用户验收腾讯云后再同步同一提交。

2026-08-22 18:48 翻牌多账号与腾讯云网页验证码登录完成腾讯云阶段发布：网站功能提交 `24e7f7b`、空配置修复 `a5246d7`、fan-hub 提交 `24f4ddc` 已推送，腾讯云 screen 重启为 `2255530.snh48`、Python PID `2255534`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。公网 `/flip-cards` 已包含账号选择器和统一管理弹窗；受保护 API 返回默认账号 `172884074 / xxgg2333`、schema v3 共 338 条、312 条语音转录，账号级媒体 Range 为 206；腾讯云账号管理能力为 true，伪造跨站 POST 为 403。现有单账号运行产物已只复制迁移到账号目录，旧文件保留。阿里云代码和同步脚本尚未部署，等待用户验收腾讯云；最终两端使用同一代码和弹窗，阿里云能力开关为 false 且不提供跨站跳转。

2026-08-22 15:20 管理员行程/事件统一入口完成腾讯云阶段发布：功能提交 `c6f2302` 已由 `cjy.plus` 加载，旧 `/api/timeline/manual-events` 返回 404，原手工文件中的“加入 SNH48 二十三期生”和“Mini Live”已迁入统一行程 CSV，并补充“陈嘉仪出道首演”里程碑。腾讯云 `/api/timeline/schedule` 当前返回 131 条。阿里云的必要行程数据已由既有 cron 自动拉到 131 条，但网站 checkout 仍为 `72d1cd1`，旧手工接口仍返回 200；这说明数据副本已更新、统一接口代码尚未部署，等待用户验收腾讯云后再发布代码。

2026-08-22 时光轴行程/事件拆分、微博/抖音统一数据、抖音稳定作品链接和微博日常去重改造已完成腾讯云验收，并按用户确认部署到阿里云；本次补处理新助手 `182321334` 的 8/16、8/17 行程后，两端 `/api/timeline/schedule` 均返回 128 条有效记录（无 `event_type=日常`），新增 8/19、8/28、8/30 行程；社交时间轴两端仍返回微博 25 条、抖音 36 条，出道 300 天仅保留一条。

抖音稳定作品链接、微博日常去重与 300 天事件合并专项复核：2026-08-22 CST +0800

观察页浏览器档案聚合腾讯云阶段发布专项复核：2026-08-16 03:18 CST +0800

计分礼物送礼用户 Excel 导出腾讯云阶段发布专项复核：2026-08-08 20:15 CST +0800

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

陈嘉仪/曾雪婷房间计分 PK 腾讯云发布专项复核：2026-08-08 18:07 CST +0800

本文件记录 `/home/snh48_web` 的长期运行方式和腾讯云到阿里云的数据同步口径。进程 PID 会随重启变化，排查时以文中的命令实时查询为准。

## 当前运行方式

| 环境 | 网站服务 | 监听 | 说明 |
|------|----------|------|------|
| 腾讯云 `cjy.plus` | `systemd` 服务 `snh48-web` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前运行功能基线为 `8fe2171`。PID `3814128`，active/running、`NRestarts=0`；私有 `.env` 设置 `QA_ENABLED=false`，QA API 不注册，本机不保留知识库索引或嵌入模型缓存 |
| 阿里云香港 `cjy.我爱你` | `systemd` 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前 checkout 为 `13d4c46`。PID `2512204`，active/running、`NRestarts=0`；QA 保持启用并独立运行，腾讯云没有到该站的 QA 跳转或互链 |

## 常用状态命令

腾讯云：

```bash
systemctl status snh48-web
journalctl -u snh48-web --no-pager -n 80
ss -ltnp | grep ':8000'
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

2026-07-17 本次重启发现既有 `/api/qa/status` 会在模型尚未加载时启动后台预热；模型加载线程会在当前小规格主机上短时占用 GIL，导致全站请求等待。当时用 `QA_WARMUP_ON_STARTUP=false` 临时规避。该问题已于 2026-08-24 通过腾讯云 `QA_ENABLED=false` 完整解决：QA 路由和预热均不加载，本地知识库与模型缓存已删除。

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

## 腾讯云与阿里云之间的双向数据同步任务

2026-10-16 起生产自动同步为双向：正向"阿里云主动拉取腾讯云"（采集与网站数据），反向"腾讯云主动拉取阿里云"（阿里云产出的派生数据）。腾讯云主动推送（`sync-to-aliyun*`）仍是退役兜底，不应恢复。

### 正向（腾讯云→阿里云）

> 2026-08-16 03:18 观察页浏览器档案聚合腾讯云阶段发布：功能提交 `3d7cf5e` 已推送并由腾讯云 screen 加载。`/ob` 不再按 IP 合并旧会话；上线后的访问使用本域浏览器档案估算访客，可把同一浏览器切换 IP 后的访问合并，并逐次显示粗粒度设备、IP 和页面。实现不查询城市、经纬度，不保存完整 User-Agent，也不使用 Canvas、字体、GPU 等主动指纹。603 条旧会话保留为单独历史记录但不计入估算人数，稳定档案从上线后的真实浏览器访问开始累积。公网 `/ob` 返回 200，未授权 `/api/ob/data` 返回 401，服务器内鉴权接口返回 200、`Cache-Control: no-store`，数据字段检查未发现城市、经纬度或完整 UA。项目部署工具因腾讯云本机回连公网 SSH 无可用密钥而未执行远端步骤，随后直接核对本机 checkout 并重启 `snh48` screen；首次按标准命令启动触发既有 QA 预热导致短时等待，最终恢复既有 `QA_WARMUP_ON_STARTUP=false` 覆盖后本机和公网 `/ob` 分别约 0.04 秒和 0.05 秒返回。阿里云尚未部署，等待用户验收腾讯云页面后再继续。

> 2026-08-08 20:15 计分礼物送礼用户 Excel 导出腾讯云阶段发布：功能提交 `f423a38` 已推送并由腾讯云 screen 加载。`/score-gifts` 的“送礼用户分布”新增导出入口，新接口沿用当前来源、礼物、用户和日期筛选，返回“送礼用户汇总”与“投分明细”两个工作表；明细按用户分组，保留送礼时间、房间/直播来源、礼物、数量、单个分值和对应分数。真实 `score_gifts.json` 共 2098 条记录的导出为 542585 bytes，ZIP 完整性检查无错误。公网页面为 200、未授权新接口为 401、服务器内鉴权新接口为 200。项目部署工具因腾讯云本机回连公网 SSH 无可用密钥而未执行远端步骤，随后直接核对本机 checkout 为目标提交并仅重启 `snh48` screen；阿里云尚未部署，等待用户验收腾讯云页面后再继续。

> 2026-08-08 18:07 房间计分 PK 腾讯云阶段发布：网站功能提交 `d369a16` 和响应性修复 `8f09eb9` 已推送并由腾讯云 screen 加载。公网 `/pk` 返回 200，未授权数据 API 返回 401，服务器内鉴权请求返回 200；采样数据为陈嘉仪新增 `3847.9`、累计 `14544.0`，曾雪婷新增 `5595.6`、累计 `19214.4`。首次按默认命令重启时，既有 QA 启动预热再次使普通页面超时，随后按本文既有处置临时覆盖 `QA_WARMUP_ON_STARTUP=false` 恢复，PK 文件直接读取耗时约 0.001 秒。阿里云尚未部署网页，也未同步 `room_record/pk_scores/`；等待用户验收腾讯云页面后再单独确认，现有阿里云同步脚本未改动。

> 2026-07-21 15:31 翻牌网站 HTML 移除专项复核：网站仓库功能提交 `35a4134` 已推送并部署，随后文档提交 `9b0bce4` 以 `--no-restart` 快进到两端。腾讯云网站 screen 重启为 `1407658.snh48`、PID `1407675`；阿里云 `snh48-aliyun` 重启为 PID `3257540`。两端 `/flip-cards` 均为 200，旧 `/api/flip-cards/html` 均为 404，未登录 `/api/flip-cards/status` 均为 401，页面源码不再包含 `downloadHtmlLink`、`/api/flip-cards/html` 或“下载版”。阿里云旧 `/home/snh48-fan-hub/flip_chat.html` 副本已删除；已部署的动态同步脚本和 `deploy.py` 不再引用 `flip_chat.html`，后续 cron 不会重新拉取该 HTML。腾讯云 fan-hub 的 `flip_chat.html` 仍保留为本地下载查看产物，不作为网站同步项。

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
| 状态文件 | `/tmp/snh48_sync_from_tencent.state.core`、`/tmp/snh48_sync_from_tencent.state.dynamic`、`/tmp/snh48_sync_from_tencent.state.hub` |
| 锁文件 | `/tmp/snh48_sync_from_tencent_change.lock`、`/tmp/snh48_sync_from_tencent.lock` |
| 同步日志 | `/var/log/snh48/sync-from-tencent.log` |
| 源服务器 | 腾讯云 `root@124.222.72.203` |
| 目标服务器 | 阿里云本机 |

脚本逻辑：

1. 阿里云每分钟 SSH 到腾讯云，分别计算 `core`、`dynamic`、`hub` 三组源数据指纹。
2. 三组指纹都没有变化时只写入 `no source changes, skipped`。
3. 某组指纹变化时调用 `sync-from-tencent.sh <group>`，在一次同步内复用同一条 SSH ControlMaster 连接并用 `rsync` 拉取对应分组。
4. 同步成功后更新 `/tmp/snh48_sync_from_tencent.state.<group>`。

### 反向（阿里云→腾讯云，2026-10-16 新增）

| 项 | 当前值 |
|----|--------|
| 自动任务所在服务器 | 腾讯云 |
| cron | `* * * * * bash /home/snh48_web/deploy/sync-from-aliyun-if-changed.sh >> /var/log/snh48/sync-from-aliyun.log 2>&1` |
| 轻量检查脚本 | `/home/snh48_web/deploy/sync-from-aliyun-if-changed.sh` |
| 实际拉取脚本 | `/home/snh48_web/deploy/sync-from-aliyun.sh` |
| 状态文件 | `/tmp/snh48_sync_from_aliyun.state.derived`、`/tmp/snh48_sync_from_aliyun.state.notify` |
| 锁文件 | `/tmp/snh48_sync_from_aliyun_change.lock`、`/tmp/snh48_sync_from_aliyun.lock` |
| 同步日志 | `/var/log/snh48/sync-from-aliyun.log` |
| 源服务器 | 阿里云 `root@8.210.188.184` |
| 目标服务器 | 腾讯云本机 |

反向脚本逻辑与正向镜像（分组指纹 + flock + ControlMaster 复用 rsync），差异规则：

- 所有目录同步不用 `--delete`，rsync 统一加 `--update` 防回滚；源文件/目录缺失只跳过，绝不删除腾讯云本地文件。
- ~~`notifications/notification_events.jsonl` 落地为腾讯云 `notifications/aliyun_relay/`~~（2026-10-20 飞书本地化起移除：两端各自直推飞书，事件不再回流）。
- `private_handover/移交包/行程组/` 为阿里云权威、腾讯云不再写；正向 hub 组对该目录用 `--update` 防回滚。
- `score_gifts` 排除 `live_business_fulfillments.json` 与 `.*.lock`（可写业务状态走腾讯云权威版本化复制）；全局排除 `*.lock`/`*.tmp`/`.*.sync.*`。
- `flip_data/web` 反向保留发布顺序：先 payload，最后 `accounts.json` 临时文件原子改名。

同步内容：

| 路径 | 方向 | 说明 |
|------|------|------|
| `/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv` | 阿里云→腾讯云 | 事件/行程主文件，2026-10-16 起阿里云产出 |
| `/home/snh48-fan-hub/schedule_record/chenjiayi_milestones.csv` | 阿里云→腾讯云 | 里程碑独立文件，列结构同主文件 |
| `/home/snh48-fan-hub/schedule_record/schedule.csv` | 阿里云→腾讯云 | 兼容副本 |
| `/home/snh48-fan-hub/schedule_record/backups/` | 阿里云→腾讯云 | 行程自动维护备份回流归档 |
| `/home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json` | 腾讯云→阿里云 | 微博/抖音已过滤的轻量时间轴数据；不包含原始社交 CSV、Cookie 或采集器 |
| `/home/snh48-fan-hub/live_record/live_index.csv` 与 `live_record/陈嘉仪_161808449/` | 腾讯云→阿里云 | 直播回放汇总与录像索引；排除 `live.ts`/`live.capture.ts` 大文件 |
| `/home/snh48-fan-hub/performance_record/陈嘉仪_161808449/` | 腾讯云→阿里云 | 公演公开互动文本白名单（json/jsonl/csv/lrc） |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 腾讯云→阿里云 | 直播封面 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/` 房间原始数据 | 腾讯云→阿里云 | metadata/messages*.jsonl 事实表与月封存、房间媒体；排除 `cross_room/`、qchat 排障文件、`metadata/backups/`、锁/临时文件及派生子目录 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 阿里云→腾讯云 | 礼物回复派生小数据，2026-10-16 起阿里云产出 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 阿里云→腾讯云 | 语音转录文本数据，2026-10-16 起阿里云产出 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 腾讯云→阿里云 | 密码保护的上麦回放发布包；manifest 原子提交顺序不变，原始 FLV 不同步 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 阿里云→腾讯云 | 计分礼物只读派生文件，2026-10-16 起阿里云产出；两个方向都排除 `live_business_fulfillments.json` 和 `.*.lock`，可写业务状态走版本化共享状态 |
| `/home/snh48-fan-hub/room_record/pk_scores/` | 阿里云→腾讯云 | 房间计分 PK 派生小数据，2026-10-16 起阿里云产出 |
| `/home/snh48-fan-hub/flip_data/web/` | 阿里云→腾讯云 | 脱敏账号清单与账号 JSON，2026-10-16 起阿里云产出；`accounts.json` 最后原子提交，不含手机号、Token 或完整 metadata |
| `/home/snh48-fan-hub/flip_data/audio/`、`/home/snh48-fan-hub/flip_data/video/` | 阿里云→腾讯云 | 账号级翻牌音视频依赖，2026-10-16 起阿里云产出；不含 `metadata/`、`transcripts/`、登录会话或任务日志 |
| `/home/snh48-fan-hub/social_record/fan_counts/` | 腾讯云→阿里云 | 粉丝数记录页公开只读小数据 |
| `/home/snh48-fan-hub/pocket48_ranks/陈嘉仪_161808449/` | 腾讯云→阿里云 | 口袋48榜单快照公开只读小数据（排除采集锁） |
| `/home/snh48-fan-hub/social_record/weibo/*.jsonl`、`social_record/bilibili/*.csv` | 腾讯云→阿里云（hub） | fan-hub 自动化监控清单输入；目录内转发器状态文件不同步 |
| `/home/snh48-fan-hub/notifications/admin_feedback_center.md`、`codex_social_event_queue.json` | 腾讯云→阿里云（hub） | 管理员反馈中心与社交事件队列，供阿里云侧自动化消费 |
| `/home/snh48-fan-hub/config/accounts.json`、`config/koudai_token.json` | 腾讯云→阿里云（hub） | 口袋48账号配置，保持 root-only 权限，不套网站组 |
| `/home/snh48-fan-hub/private_handover/移交包/行程组/` | 双向但阿里云权威 | 2026-10-16 起阿里云权威、腾讯云不再写；正向 hub 仅迁移窗口初始投递且 `--update` 防回滚，更新经反向回流 |
| `/home/snh48-fan-hub/notifications/assistant_schedule_draft_state.json` | 阿里云→腾讯云 | 小助理行程草稿状态回流 |
| `/home/snh48-fan-hub/notifications/codex_runs/` | 阿里云→腾讯云 | 阿里云 codex 运行记录，回流供腾讯云侧 COS 归档 |
| ~~`/home/snh48-fan-hub/notifications/notification_events.jsonl`~~ | ~~阿里云→腾讯云~~ | 2026-10-20 飞书本地化起移除：两端各自直推飞书，不再中继 |

同步分组：

| 分组 | 方向 | 内容 | 典型频率 |
|------|------|------|----------|
| `core` | 腾讯云→阿里云 | 社交时间轴、直播回放汇总与录像索引、公演互动文本、直播封面、房间原始数据白名单 | 直播/房间消息更新时变化 |
| `dynamic` | 腾讯云→阿里云 | 成员房间上麦回放发布包、粉丝数记录、口袋48榜单快照 | 上麦会话结束或采集更新时变化 |
| `hub` | 腾讯云→阿里云 | 微博/B站监控清单、管理员反馈中心、社交事件队列、口袋48账号配置、行程组初始投递 | 监控更新或管理员反馈时变化 |
| `derived` | 阿里云→腾讯云 | 行程 CSV 与 backups、礼物回复、语音转录、计分礼物只读派生、pk_scores、翻牌三组产物、小助理草稿状态、行程组回流 | 阿里云派生服务更新时变化 |
| `notify` | 阿里云→腾讯云 | codex_runs（2026-10-20 前还含 notification_events.jsonl 中继，飞书本地化后移除） | codex 运行时变化 |

不作为常规同步项：

- `schedule_record/images/`：图片通过网站 `/image-proxy/` 访问。
- 完整原始房间消息、普通语音原文件、上麦原始 FLV、Cookie、`.env`、日志和缓存。Token/账号配置仅限 hub 组两个 `config/` 清单文件按 root-only 权限正向投递，不进入其他任何分组。
- 首页背景词、房间忽略、计分业务和记忆页是非 Git 版本化共享状态；腾讯云和阿里云均已启用统一提交、历史和 outbox。不得用普通 rsync 或 Git 覆盖这四个当前文件；腾讯云 outbox 如果短时保留待补发文件，应按共享状态工具排查，不要手工覆盖阿里云。
- 2026-10-16 起阿里云承担 fan-hub 数据加工/AI 生成（派生数据产地），腾讯云保留采集与全量归档；除 `移交包/行程组/`（阿里云权威、只反向）外，两个方向不同步任何相同路径。

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
- `ps` 不应长期出现 `sync-to-aliyun-loop.sh` 或推送方向的 `rsync`；2026-10-16 起腾讯云连接阿里云 `8.210.188.184` 的 `sync-from-aliyun*` 反向拉取进程属正常运行。

2026-07-03 排查结论：

- 腾讯云 `sync-to-aliyun.sh` cron 已注释。
- 腾讯云没有发现 `sync-to-aliyun` 常驻进程。
- 旧推送日志最后更新时间停在 `2026-07-03 02:45:04 +0800`。
- 阿里云 `sync-from-tencent.log` 持续出现成功记录，说明新方案已经接管自动同步。

## 排查注意

- 正向 `source changed groups=dynamic, pulling...` 每分钟出现不一定异常；上麦发布包、粉丝数或榜单快照更新时动态组指纹会变化。2026-10-16 起礼物回复、语音转录、计分礼物和翻牌产物不再走正向，改在阿里云产出并由反向 `derived` 组回流，腾讯云侧 `/var/log/snh48/sync-from-aliyun.log` 每分钟出现 `groups=derived, pulling...` 同理属预期。
- `source changed groups=core,dynamic,hub, pulling...` 如果长期每分钟出现，需要确认这些组是否真的持续变化；否则检查状态文件是否被删除或无法写入。
- 稳定文件如 `chenjiayi_events.csv`、`chenjiayi_milestones.csv`、`schedule.csv` 和社交时间轴 JSON 应可以用 `sha256sum` 严格比对（行程 CSV 以阿里云为源、腾讯云为副本）；四个可写共享状态改为核对 `_state.revision` 和 outbox，不能用普通 rsync 修复。
- 动态目录只能按同步日志、mtime 和 1 到 2 分钟延迟判断，不要要求瞬时 hash 完全一致。
- 修改同步目录、同步方向或云服务器 IP 时，必须同步更新 `doc/codex/project_profile.md`、`doc/daily_website_check.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`。
- 如果新增同步目标或更换阿里云 IP，需要提醒用户更新腾讯云登录风险白名单。
2026-09-14 21:30 腾讯云社交凭据页修复：登录提交显示“正在登录并验证权限…”及加载失败原因；口袋48验证码输入框始终可见，发送短信成功后启用提交按钮。此前用户遇到的 `操作失败（OSError）` 来自翻牌账号特权桥长期进程状态异常，已重启 `snh48-privileged-bridge-flip.service` 后通过实际 `send-sms` 烟测；`snh48-web.service` active/running。微博当前主/备用 Cookie 检查均失败，抖音主/备用均为有效，B站 Cookie 验证通过。
2026-09-14 社交凭据管理页增强：微博/抖音槽位显示脱敏手机号，更新 Cookie 时可填写或修改手机号，并可将备用槽位设为主槽位；口袋48手机号、验证码和安全验证集中在同一登录区域。特权桥新增 `set-primary` 命令并已重启，网站服务 active/running。
