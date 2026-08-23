# 网站页面清单

> 最后更新：2026-08-23

本文记录当前网站所有前端页面入口、可见性、鉴权方式和主要代码位置。新增、删除、改名页面，或新增短入口、改变密码策略时，需要同步更新本文。

页面路由的代码源头是 `website/main.py`；模板位于 `website/templates/`；静态脚本和样式位于 `website/static/`。

## 维护规则

- 公开导航、页脚入口、仅 URL 访问的管理页都要登记。
- 管理页必须写明密码来源和 API 请求头。
- 新增短入口时保留清晰主入口，并在本文同时登记。
- 新增页面或重要交互时必须按 `doc/codex/page_tracking_best_practices.md` 接入用户行为追踪；继承 `base.html` 的页面确认自动加载 tracker，独立模板必须显式加载 `/static/js/tracker.js`。
- 用户可见页面改动部署时，默认先在腾讯云 `https://cjy.plus` 验证，等用户手动确认后再同步阿里云。
- 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs`，并提交 `website/static/js-dist/`、`website/static/css-dist/`。

## 公开页面

| 页面 | 路由 | 入口位置 | 模板 | 主要脚本/API | 备注 |
|------|------|----------|------|--------------|------|
| 首页 | `/` | 公开首页 | `website/templates/index.html` | `website/static/js/main.js`、`website/static/js/scroller.js`、`website/static/js/celebration.js`、`/api/scroller/texts`、`/api/balance` | 全屏背景和飘动文字；从出道第300天起，每逢整百天展示8天庆祝动画，已达到的整百天祝福永久进入飘屏 |
| 关于 | `/about` | 公开导航 | `website/templates/about.html` | `website/static/js/about.js` | 站点介绍 |
| AI 问答 | `/qa` | 公开导航 | `website/templates/qa.html` | `website/static/js/qa.js`、`/api/qa/*` | 页面可访问；问答能力需要 `SITE_PASSWORD` |
| 时光轴 | `/timeline` | 公开导航 | `website/templates/timeline.html` | `website/static/js/timeline.js`、`/api/timeline/*` | 行程、直播、回放和地图入口；整百天里程碑到达后自动加入并永久保留 |
| 直播回放 | `/replay/{live_id}` | 由时光轴/直播卡片进入 | `website/templates/replay.html` | 回放数据来自 `LIVE_PUSH_REPLAY_ROOT` | `live_id` 为动态参数 |
| 服务条款 | `/terms` | 页脚 | `website/templates/terms.html` | 无专用脚本 | 法务页面 |
| 隐私政策 | `/privacy` | 页脚 | `website/templates/privacy.html` | 无专用脚本 | 法务页面 |
| 投诉举报 | `/complaint` | 页脚 | `website/templates/complaint.html` | `/api/complaint/submit` | 含验证码和提交限速 |

## 管理和仅 URL 页面

这些页面不进入公开导航。页面本身通常可打开，但数据 API 需要密码；密码不要写入代码或文档明文，只放在服务器 `.env`。

| 页面 | 主路由 | 短入口 | 模板 | API | 鉴权/请求头 | 数据来源 |
|------|--------|--------|------|-----|-------------|----------|
| 背景词管理 | `/scroller-admin` | 无 | `website/templates/scroller_admin.html` | `/api/scroller/*` | `SCROLLER_PASSWORD`；`X-Scroller-Password` 或登录 Cookie | `website/data/scroller_texts.json`；非 Git 版本化共享状态 |
| 观察页 | `/ob` | 无 | `website/templates/ob.html` | `/api/ob/verify`、`/api/ob/data`、`/api/ob/mark-read`、`/api/ob/inbox/status`、`/api/feedback-chat/conversations`、`/api/feedback-chat/admin-history`、`/api/feedback-chat/admin-watch`、`/api/feedback-chat/reply` | `OB_PASSWORD`；`X-Ob-Password` | 本节点访问日志按第一方浏览器档案估算访客，同一浏览器可跨标签页和 IP 聚合；逐次页面访问显示粗粒度设备与当时 IP，不查询城市/经纬度；旧记录按会话单列；用户记录可按页面路径筛选；通知中心、默认折叠的双服务器可靠待处理箱和客服聊天保留来源标签；客服会话通过可恢复的长等待请求接收新消息 |
| 房间礼物与综合回礼 | 逐条明细 `/room/gifts`；按送礼人综合回礼 `/room/gift-senders` | 无 | `website/templates/gift_replies.html`、`website/templates/gift_reply_senders.html` | `/api/gift-replies/verify`、`/api/gift-replies/data`、`/api/gift-replies/summary`、`/api/gift-replies/senders`、`/api/gift-replies/sender-history`、`/api/feedback-chat/history`、`/api/feedback-chat/watch`、`/api/feedback-chat/message` | `GIFT_REPLIES_PASSWORD`；`X-Gift-Replies-Password` | `GIFT_REPLIES_DIR`，默认 fan-hub `gift_replies/`；综合回礼默认从 `2026-05-30` 起显示全部送礼人，可筛选“有未回复/已全部回复”；一次列出全部匹配送礼人且默认折叠，展开时按需读取个人历史；页面只轮询轻量摘要，检测到数据变化后提示用户点击刷新，不自动替换当前列表；页面右下角客服按钮打开按用户识别码保存历史的聊天框，识别码以 SHA-256 生成内部会话编号，同时仅在受保护的管理员事件中保存并展示用户自定义识别码；聊天框通过可恢复的长等待请求接收新消息；旧 `/gift-replies*` 和 `/gr` 已废弃并返回 404 |
| 房间消息管理 | `/room-messages` | `/room` | `website/templates/room_messages.html` | `/api/room-messages/verify`、`/api/room-messages/data`、`/api/room-messages/summary`、`/api/room-messages/ignore-latest-batch`、`/api/room-messages/undo-ignore` | `ROOM_MESSAGES_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Room-Messages-Password` | 消息读取路径不变；忽略状态是由腾讯云统一提交、带历史版本和 outbox 的非 Git 共享状态 |
| 成员房间上麦回放 | `/room-voice-replays` | `/radio`；兼容 `/radio-replays` | `website/templates/room_voice_replays.html` | `/api/room-voice-replays/login`、`/sessions`、`/sessions/{session_id}`、`/segments/{filename}` | `ROOM_VOICE_REPLAYS_PASSWORD`，默认复用 `ROOM_MESSAGES_PASSWORD`；HttpOnly Cookie 或 `X-Room-Voice-Replays-Password` | `ROOM_VOICE_REPLAYS_DIR`，默认 fan-hub `room_voice_replays/`；公开房间/小房间独立会话，默认播放 AAC-LC 单声道兼容版，可切换源 AAC 原始音质版并保持时间位置；进度跳转和缓冲有可见状态；有录音覆盖的消息整行可点击或用键盘跳转到对应时间；音频分段和同期消息用 `session_id` 归为整体；设置 `noindex,nofollow` |
| 翻牌记录 | `/flip-cards` | `/flip` | `website/templates/flip_cards.html` | `/api/flip-cards/login`、`/accounts`、`/data?account_id=...`、账号级媒体和 `/account-management/*` | `FLIP_CARDS_PASSWORD`，默认复用 `OB_PASSWORD`；HttpOnly Cookie 或 `X-Flip-Cards-Password` | 读取 fan-hub 脱敏账号清单、schema v4 账号数据和账号级媒体；两端页面/代码一致，腾讯云允许手机号验证码登录并后台刷新，阿里云账号管理弹窗只显示当前节点不开放操作且无跳转；成员筛选默认陈嘉仪，其他成员显示完整姓名；首次渲染最新 50 条并向上渐进加载，音频不预载；账号管理与可收起的更新状态分离，底部按钮重新加载并跳到最新记录；转录、问题状态 Tag 和双向 4 秒高亮保留；设置 `noindex,nofollow` |
| 社交凭据管理 | `/social-credentials-admin` | 无 | `website/templates/social_credentials_admin.html` | `/api/social-credentials/login`、`/status`、`/update`、`/logout` | `SOCIAL_CREDENTIALS_ADMIN_PASSWORD`，迁移期留空复用 `OB_PASSWORD`；短时路径限定 HttpOnly Cookie；更新 POST 必须同源 | 不读取或返回原 Cookie；微博/抖音显示主备槽位，B站显示主槽位，新值由 fan-hub 严格桥实时验证成功后原子替换。只允许腾讯云主节点写入，阿里云硬禁用；不进入导航并设置 `noindex,nofollow` |
| 计分礼物管理 | `/score-gifts` | `/sg` | `website/templates/score_gifts.html` | `/api/score-gifts/verify`、`/api/score-gifts/data`、`/api/score-gifts/summary`、`/api/score-gifts/export.xlsx`、`/api/score-gifts/sender-export.xlsx`、`/api/score-gifts/business-review` | `SCORE_GIFTS_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Score-Gifts-Password` | `score_gifts.json` 为派生展示数据；送礼用户导出包含用户汇总与逐笔投分明细；`live_business_fulfillments.json` 为版本化共享业务状态 |
| 房间计分 PK | `/score-pk` | `/pk` | `website/templates/pk_score.html` | `/api/pk-score/verify`、`/api/pk-score/data` | 复用 `SCORE_GIFTS_PASSWORD`；`X-PK-Score-Password` | fan-hub `room_record/pk_scores/current.json`；展示双方 17:15 后新增分、基础分、累计分、差值和明细；首轮只发布腾讯云，阿里云数据同步待腾讯云页面验收 |
| 记忆页 | `/memories` | `/memory` | `website/templates/memories.html` | `/api/memories/verify`、`/api/memories/data`、`/api/memories/submit`、`/api/memories/manage`、`/api/memories/review` | `MEMORIES_VIEW_PASSWORD`；`X-Memories-Password`。应援会模式使用 `MEMORIES_FANCLUB_PASSWORD` / `X-Memories-Fanclub-Password`；本人模式使用 `MEMORIES_IDOL_PASSWORD` / `X-Memories-Idol-Password` | `MEMORIES_DATA_PATH`，默认 `website/data/memories/memories.json`；格式示例见 `website/data/memories/memories.example.json`；初始数据可由 `script/build_memories_seed.py` 从 fan-hub 派生 |

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
curl -sS -D - -o /dev/null https://cjy.plus/qa
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
curl -sS -D - -o /dev/null https://cjy.plus/sg
curl -sS -D - -o /dev/null https://cjy.plus/pk
curl -sS -D - -o /dev/null https://cjy.plus/score-pk
curl -sS -D - -o /dev/null https://cjy.plus/memories
curl -sS -D - -o /dev/null https://cjy.plus/memory
```

阿里云在用户确认腾讯云手动验证通过后再测，对应域名为 `https://cjy.xn--6qq986b3xl`。
