# 网站页面清单

> 最后更新：2026-08-24

本文记录当前网站所有前端页面入口、可见性、鉴权方式和主要代码位置。新增、删除、改名页面，或新增短入口、改变密码策略时，需要同步更新本文。

页面路由的代码源头是 `website/main.py`；模板位于 `website/templates/`；静态脚本和样式位于 `website/static/`。

## 维护规则

- 公开导航、页脚入口、仅 URL 访问的管理页都要登记。
- 管理页必须写明密码来源和 API 请求头。
- 新增短入口时保留清晰主入口，并在本文同时登记。
- 新增页面或重要交互时必须按 `doc/codex/page_tracking_best_practices.md` 接入用户行为追踪；继承 `base.html` 的页面确认自动加载 tracker，独立模板必须显式加载 `/static/js/tracker.js`。
- 用户可见页面改动部署时，默认先在腾讯云 `https://cjy.plus` 验证，等用户手动确认后再同步阿里云。
- 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs`，并提交 `website/static/js-dist/`、`website/static/css-dist/`。

### 移动端筛选弹窗标准

- 日期筛选输入默认保持空值；不要在 HTML 或初始化脚本中预选“今天”。针对 iOS/Safari 打开空日期控件时短暂写入今天的行为，统一使用 `currentBeijingDate()` + `installDateInputGuard()` 清除合成值。
- 日期控件只更新待提交的表单值，不在 `change` 事件中请求数据；查询参数必须读取独立的“已应用日期”，只有用户点击“筛选”才把输入值提交为已应用值。后台轮询、滚动补载和其他筛选项变化不得提前应用尚未提交的日期。弹窗打开期间不得执行背景列表的滚动定位、前后页补载或“填满视口”任务，避免原生日期选择器尚未关闭时同步重绘列表导致页面卡死。
- 弹窗外层使用固定视口和遮罩，卡片宽度使用 `min(460px, calc(100vw - 24px))`，内部滚动区使用 `minmax(0, 1fr)`、`min-width: 0` 和 `max-width: 100%`；日期控件固定高度、`overflow: hidden`，并通过 `::-webkit-date-and-time-value` 左对齐，避免内容撑出卡片。
- 页面内容采用文档滚动，顶栏用 `position: sticky; top: 0`；只有弹窗打开时锁定 `html/body` 滚动。这样手机地址栏收起时，页面仍能下滑并保持顶栏和内容关系稳定。
- “跳到最新”按钮只在当前内容不在最新位置时显示：翻牌页以记录列表底部为最新，Room 页以消息列表底部为最新，礼物明细和送礼人页以第 1 页且文档滚动位置接近顶部为最新。没有新数据时点击只做平滑滚动，不请求数据；检测到新数据时按钮才改为“有新记录/数据，点击加载最新”，点击后加载数据并定位到最新位置。按钮层级必须高于普通列表和消息卡片、低于筛选弹窗。

### 带密码页面的初始鉴权状态

- 登录遮罩初始错误区域必须为空且隐藏，不能在 HTML 中预填“密码错误”。页面加载时不得因为复用 Cookie、状态探测或空密码请求直接展示密码错误。
- 使用 Cookie 或旧会话自动尝试加载时，`401/403` 只负责恢复登录表单并清除错误文案；只有用户实际提交密码，或此前已验证的会话后来失效，才显示“密码错误/密码已失效”。
- 验证成功后的数据请求失败应显示可重试的“密码正确，但数据加载失败”，不得把普通网络、数据或服务端错误转换为密码错误。

## 公开页面

| 页面 | 路由 | 入口位置 | 模板 | 主要脚本/API | 备注 |
|------|------|----------|------|--------------|------|
| 首页 | `/` | 公开首页 | `website/templates/index.html` | `website/static/js/main.js`、`website/static/js/scroller.js`、`website/static/js/celebration.js`、`/api/scroller/texts`、`/api/balance` | 全屏背景和飘动文字；从出道第300天起，每逢整百天展示8天庆祝动画，已达到的整百天祝福永久进入飘屏 |
| 关于 | `/about` | 公开导航 | `website/templates/about.html` | `website/static/js/about.js` | 站点介绍 |
| AI 问答 | `/qa` | 公开导航 | `website/templates/qa.html` | `website/static/js/qa.js`、`/api/qa/*` | `QA_ENABLED=true` 的节点提供问答并要求 `SITE_PASSWORD`；关闭节点返回本机 503 页面且不注册 API，不跨站跳转 |
| 时光轴 | `/timeline` | 公开导航 | `website/templates/timeline.html` | `website/static/js/timeline.js`、`/api/timeline/*` | 行程、直播、回放、记忆和地图入口；整百天里程碑到达后自动加入并永久保留 |
| 记忆 | `/memories` | 从时光轴进入 | `website/templates/memories.html`、`website/static/js/memories.js` | `/api/memories/data`、`/api/memories/submit`；管理模式使用 `/api/memories/manage`、`/api/memories/review` | 公开记录可直接浏览和提交（仍受提交开关、基础审核和 IP 限速约束）；应援会模式使用 `MEMORIES_FANCLUB_PASSWORD` / `X-Memories-Fanclub-Password`，本人模式使用 `MEMORIES_IDOL_PASSWORD` / `X-Memories-Idol-Password`；不向普通访客返回平台 ID |
| 直播回放 | `/replay/{live_id}` | 由时光轴/直播卡片进入 | `website/templates/replay.html` | 回放数据来自 `LIVE_PUSH_REPLAY_ROOT` | `live_id` 为动态参数 |
| 服务条款 | `/terms` | 页脚 | `website/templates/terms.html` | 无专用脚本 | 法务页面 |
| 隐私政策 | `/privacy` | 页脚 | `website/templates/privacy.html` | 无专用脚本 | 法务页面 |
| 投诉举报 | `/complaint` | 页脚 | `website/templates/complaint.html` | `/api/complaint/submit` | 含验证码和提交限速 |

## 管理和仅 URL 页面

这些页面不进入公开导航。除公开记忆页外，页面本身通常可打开但数据 API 需要密码；密码不要写入代码或文档明文，只放在服务器 `.env`。

| 页面 | 主路由 | 短入口 | 模板 | API | 鉴权/请求头 | 数据来源 |
|------|--------|--------|------|-----|-------------|----------|
| 背景词管理 | `/scroller-admin` | 无 | `website/templates/scroller_admin.html` | `/api/scroller/*` | `SCROLLER_PASSWORD`；`X-Scroller-Password` 或登录 Cookie | `website/data/scroller_texts.json`；非 Git 版本化共享状态 |
| 观察页 | `/ob` | 无 | `website/templates/ob.html` | `/api/ob/verify`、`/api/ob/summary`、`/api/ob/data`、`/api/ob/mark-read`、`/api/ob/inbox/status`、`/api/feedback-chat/conversations`、`/api/feedback-chat/admin-history`、`/api/feedback-chat/admin-watch`、`/api/feedback-chat/reply` | `OB_PASSWORD`；`X-Ob-Password` | 本节点访问日志按服务器签发的第一方 HttpOnly 浏览器档案 Cookie 估算访客，同一浏览器可跨标签页和 IP 聚合；`/api/ob/data` 另返回不参与统计的 IP 关联组和 `ip_network_graph`，3D IP 球包含成员档案/旧会话，IP 对按共同成员数量计算边权；逐次页面访问显示粗粒度设备与当时 IP，不保存地区或经纬度；经鉴权读取时可由本机 DB-IP Lite MMDB 临时生成 IP 粗略地区标签，只用于地区筛选、IP 节点和历史 IP 摘要，不生成地区时间线；旧记录按会话单列并降低历史关联置信度；用户记录可按页面路径、日期、设备类型、系统、浏览器、档案类型、地区和历史 IP 筛选；`/api/ob/summary` 只用于自动检查版本变化，发现新数据时提示管理员，必须点击“加载最新”才替换当前记录；通知中心、默认折叠的双服务器可靠待处理箱和客服聊天保留来源标签；客服会话通过可恢复的长等待请求接收新消息 |
| 房间礼物与综合回礼 | 逐条明细 `/room/gifts`；按送礼人综合回礼 `/room/gift-senders` | 无 | `website/templates/gift_replies.html`、`website/templates/gift_reply_senders.html` | `/api/gift-replies/verify`、`/api/gift-replies/data`、`/api/gift-replies/summary`、`/api/gift-replies/senders`、`/api/gift-replies/sender-history`、`/api/feedback-chat/history`、`/api/feedback-chat/watch`、`/api/feedback-chat/message` | `GIFT_REPLIES_PASSWORD`；`X-Gift-Replies-Password` | `GIFT_REPLIES_DIR`，默认 fan-hub `gift_replies/`；综合回礼默认从 `2026-05-30` 起显示全部送礼人，可筛选“有未回复/已全部回复”；一次列出全部匹配送礼人且默认折叠，展开时按需读取个人历史；两个页面都只轮询轻量摘要，检测到数据变化后提示用户点击加载，不自动替换当前列表；无新数据时“跳到最新”只滚动，日期只在点击筛选后应用；移动端把页面互链放在右上、筛选放在右侧第二行，综合回礼页客服入口固定在稳定大视口约 `80vh` 的右侧位置，不随浏览器地址栏收起而跳动；旧 `/gift-replies*` 和 `/gr` 已废弃并返回 404 |
| 房间消息管理 | `/room-messages` | `/room` | `website/templates/room_messages.html` | `/api/room-messages/verify`、`/api/room-messages/data`、`/api/room-messages/summary`、`/api/room-messages/ignore-latest-batch`、`/api/room-messages/undo-ignore` | `ROOM_MESSAGES_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Room-Messages-Password` | 消息读取路径不变；忽略状态是由腾讯云统一提交、带历史版本和 outbox 的非 Git 共享状态 |
| 成员房间上麦回放 | `/room-voice-replays` | `/radio` | `website/templates/room_voice_replays.html` | `/api/room-voice-replays/login`、`/sessions`、`/sessions/{session_id}`、`/segments/{filename}` | `ROOM_VOICE_REPLAYS_PASSWORD`，默认复用 `ROOM_MESSAGES_PASSWORD`；HttpOnly Cookie 或 `X-Room-Voice-Replays-Password` | `ROOM_VOICE_REPLAYS_DIR`，默认 fan-hub `room_voice_replays/`；公开房间/小房间独立会话，默认播放 AAC-LC 单声道兼容版，可切换源 AAC 原始音质版并保持时间位置；桌面端保留左侧会话列表，移动端将房间类型和会话列表放入默认收起的“筛选回放”面板，选择会话后自动收起；进度跳转和缓冲有可见状态；每场回放详情可返回 Room，并携带同期第一条消息 ID 精确定位；音频分段和同期消息用 `session_id` 归为整体；设置 `noindex,nofollow` |
| 翻牌记录 | `/flip-cards` | `/flip` | `website/templates/flip_cards.html` | `/api/flip-cards/login`、`/accounts`、`/data?account_id=...`、账号级媒体和 `/account-management/*` | `FLIP_CARDS_PASSWORD`，默认复用 `OB_PASSWORD`；HttpOnly Cookie 或 `X-Flip-Cards-Password` | 读取 fan-hub 脱敏账号清单、schema v4 账号数据和账号级媒体；两端页面/代码一致，腾讯云允许手机号验证码登录并后台刷新，阿里云账号管理弹窗只显示当前节点不开放操作且无跳转；成员筛选默认陈嘉仪，其他成员显示完整姓名；首次渲染最新 50 条并向上渐进加载，音频不预载；账号管理与可收起的更新状态分离，底部按钮重新加载并跳到最新记录；转录、问题状态 Tag 和双向 4 秒高亮保留；设置 `noindex,nofollow` |
| 社交凭据管理 | `/social-credentials-admin` | 无 | `website/templates/social_credentials_admin.html` | `/api/social-credentials/login`、`/status`、`/update`、`/logout` | `SOCIAL_CREDENTIALS_ADMIN_PASSWORD`，迁移期留空复用 `OB_PASSWORD`；短时路径限定 HttpOnly Cookie；更新 POST 必须同源 | 不读取或返回原 Cookie；微博/抖音显示主备槽位，B站显示主槽位，新值由 fan-hub 严格桥实时验证成功后原子替换。只允许腾讯云主节点写入，阿里云硬禁用；不进入导航并设置 `noindex,nofollow` |
| 计分礼物管理 | `/score-gifts` | `/score` | `website/templates/score_gifts.html` | `/api/score-gifts/verify`、`/api/score-gifts/data`、`/api/score-gifts/summary`、`/api/score-gifts/export.xlsx`、`/api/score-gifts/sender-export.xlsx`、`/api/score-gifts/business-review` | `SCORE_GIFTS_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Score-Gifts-Password`；页面可跳转计分 PK | `score_gifts.json` 为派生展示数据；送礼用户导出包含用户汇总与逐笔投分明细；`live_business_fulfillments.json` 为版本化共享业务状态；`/score` 继续保留为兼容入口 |
| 房间计分 PK | `/score-pk` | 无 | `website/templates/pk_score.html` | `/api/pk-score/verify`、`/api/pk-score/data` | 复用 `SCORE_GIFTS_PASSWORD`；`X-PK-Score-Password`；页面可跳转计分礼物 | fan-hub `room_record/pk_scores/current.json`；展示双方 17:15 后新增分、基础分、累计分、差值和明细 |

直接使用请求头密码的管理页先调用轻量 `/verify` 接口，再读取完整数据；使用登录 Cookie 的翻牌与上麦回放页在 `/login` 成功后再读取数据。前端必须分别显示“正在验证”和“密码正确，正在加载”；若只是数据加载失败，应允许直接重试，不得误报为密码错误或要求重输密码。

## 非页面入口

| 路由 | 类型 | 说明 |
|------|------|------|
| `/favicon.ico` | 静态资源响应 | 从 `website/static/images/favicons/` 随机返回 favicon |
| `/static/*` | 静态资源 | JS、CSS、图片等；生产环境可能映射到 `js-dist`、`css-dist` |
| `/live-covers/*` | 静态资源 | 直播封面目录挂载，目录由 `LIVE_PUSH_REPLAY_ROOT` 和服务器 fan-hub 路径决定 |
| `/api/*` | API | 不作为页面登记；页面对应 API 已在上表列出 |

## 页面烟测清单

腾讯云：

```bash
curl -sS -D - -o /dev/null https://cjy.plus/
curl -sS -D - -o /dev/null https://cjy.plus/about
test "$(curl -sS -o /dev/null -w '%{http_code}' https://cjy.plus/qa)" = 503
test "$(curl -sS -o /dev/null -w '%{http_code}' https://cjy.plus/api/qa/status)" = 404
curl -sS -D - -o /dev/null https://cjy.plus/timeline
curl -sS -D - -o /dev/null https://cjy.plus/terms
curl -sS -D - -o /dev/null https://cjy.plus/privacy
curl -sS -D - -o /dev/null https://cjy.plus/complaint
curl -sS -D - -o /dev/null https://cjy.plus/scroller-admin
curl -sS -D - -o /dev/null https://cjy.plus/ob
curl -sS -D - -o /dev/null https://cjy.plus/room/gifts
curl -sS -D - -o /dev/null https://cjy.plus/room/gift-senders
curl -sS -D - -o /dev/null https://cjy.plus/room-messages
curl -sS -D - -o /dev/null https://cjy.plus/room
curl -sS -D - -o /dev/null https://cjy.plus/room-voice-replays
curl -sS -D - -o /dev/null https://cjy.plus/radio
curl -sS -D - -o /dev/null https://cjy.plus/flip-cards
curl -sS -D - -o /dev/null https://cjy.plus/flip
curl -sS -D - -o /dev/null https://cjy.plus/score-gifts
curl -sS -D - -o /dev/null https://cjy.plus/score
curl -sS -D - -o /dev/null https://cjy.plus/score-pk
curl -sS -D - -o /dev/null https://cjy.plus/memories
curl -sS -D - -o /dev/null https://cjy.plus/memory
```

阿里云在用户确认腾讯云手动验证通过后再测，对应域名为 `https://cjy.xn--6qq986b3xl`。
