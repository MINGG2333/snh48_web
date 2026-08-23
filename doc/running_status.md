# /home/snh48_web 后台运行与同步状态

更新日期：2026-08-23 CST +0800

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
| 腾讯云 `cjy.plus` | screen 会话运行 `python -m website.main` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前运行代码为 `9c3afec`。screen `3152206.snh48`、Python PID `3152211`，2026-08-23 16:44 重启并继续临时覆盖 `QA_WARMUP_ON_STARTUP=false`；观察页服务器签发浏览器档案 Cookie 已生效，客服聊天长等待和仅腾讯云可写的隐藏社交凭据管理均已生效 |
| 阿里云香港 `cjy.我爱你` | systemd 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前运行代码为 `8957188`。2026-08-23 17:47:55 CST 重启，PID `2448602`，active/running、`NRestarts=0`；Room 移动端顶部栏、导航位置、筛选弹窗触摸边界和背景分页锁定均已复核；既有未跟踪 `website/data/manual_events.csv`、`website/data/runtime_backups/` 与 `website/static/js/timeline.js.bak` 保持原样 |

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
| `/home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json` | 同路径 | 微博/抖音已过滤的轻量时间轴数据；不包含原始社交 CSV、Cookie 或采集器 |
| `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/` | 同路径 | 直播回放汇总 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 同路径 | 直播封面 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 同路径 | 礼物回复派生小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/` | 同路径 | 房间消息分片小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 同路径 | 语音转录文本数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 同路径 | 密码保护的上麦回放发布包；包含兼容版/原始音质版派生 M4A、元数据和同期消息，原始 FLV 不同步 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 同路径 | 计分礼物只读派生文件；排除 `live_business_fulfillments.json` 和 `.*.lock`，可写业务状态走版本化共享状态 |
| `/home/snh48-fan-hub/flip_data/web/` | 同路径 | 脱敏账号清单、schema v4 账号 JSON 和默认兼容副本；逐条包含回复成员身份，`accounts.json` 最后原子提交，不含手机号、Token 或完整 metadata |
| `/home/snh48-fan-hub/flip_data/audio/{account_id}/`、`/home/snh48-fan-hub/flip_data/video/{account_id}/` | 同路径 | 账号级翻牌音视频依赖；不含 `metadata/`、`transcripts/`、登录会话或任务日志 |

同步分组：

| 分组 | 内容 | 典型频率 |
|------|------|----------|
| `core` | 统一事件/行程 CSV、社交时间轴、直播回放汇总、直播封面 | 低频或人工更新 |
| `dynamic` | 礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物只读派生文件、脱敏翻牌 `web/`、账号级翻牌音视频 | 后台导出、上麦会话结束或翻牌批处理更新时变化 |

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
- 稳定单向文件如 `chenjiayi_events.csv`、`schedule.csv` 和社交时间轴 JSON 应可以用 `sha256sum` 严格比对；四个可写共享状态改为核对 `_state.revision` 和 outbox，不能用普通 rsync 修复。
- 动态目录只能按同步日志、mtime 和 1 到 2 分钟延迟判断，不要要求瞬时 hash 完全一致。
- 修改同步目录、同步方向或云服务器 IP 时，必须同步更新 `doc/codex/project_profile.md`、`doc/daily_website_check.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`。
- 如果新增同步目标或更换阿里云 IP，需要提醒用户更新腾讯云登录风险白名单。
