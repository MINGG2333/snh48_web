# 网站页面清单

> 最后更新：2026-06-25

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
| 首页 | `/` | 公开首页 | `website/templates/index.html` | `website/static/js/main.js`、`website/static/js/scroller.js`、`/api/scroller/texts`、`/api/balance` | 全屏背景和飘动文字 |
| 关于 | `/about` | 公开导航 | `website/templates/about.html` | `website/static/js/about.js` | 站点介绍 |
| AI 问答 | `/qa` | 公开导航 | `website/templates/qa.html` | `website/static/js/qa.js`、`/api/qa/*` | 页面可访问；问答能力需要 `SITE_PASSWORD` |
| 时光轴 | `/timeline` | 公开导航 | `website/templates/timeline.html` | `website/static/js/timeline.js`、`/api/timeline/*` | 行程、直播、回放和地图入口 |
| 直播回放 | `/replay/{live_id}` | 由时光轴/直播卡片进入 | `website/templates/replay.html` | 回放数据来自 `LIVE_PUSH_REPLAY_ROOT` | `live_id` 为动态参数 |
| 服务条款 | `/terms` | 页脚 | `website/templates/terms.html` | 无专用脚本 | 法务页面 |
| 隐私政策 | `/privacy` | 页脚 | `website/templates/privacy.html` | 无专用脚本 | 法务页面 |
| 投诉举报 | `/complaint` | 页脚 | `website/templates/complaint.html` | `/api/complaint/submit` | 含验证码和提交限速 |

## 管理和仅 URL 页面

这些页面不进入公开导航。页面本身通常可打开，但数据 API 需要密码；密码不要写入代码或文档明文，只放在服务器 `.env`。

| 页面 | 主路由 | 短入口 | 模板 | API | 鉴权/请求头 | 数据来源 |
|------|--------|--------|------|-----|-------------|----------|
| 背景词管理 | `/scroller-admin` | 无 | `website/templates/scroller_admin.html` | `/api/scroller/*` | `SCROLLER_PASSWORD`；`X-Scroller-Password` 或登录 Cookie | `website/data/scroller_texts.json` |
| 观察页 | `/ob` | 无 | `website/templates/ob.html` | `/api/ob/data`、`/api/ob/mark-read` | `OB_PASSWORD`；`X-Ob-Password` | 访问日志、通知中心数据 |
| 礼物回复管理 | `/gift-replies` | `/gr` | `website/templates/gift_replies.html` | `/api/gift-replies/data`、`/api/gift-replies/summary` | `GIFT_REPLIES_PASSWORD`；`X-Gift-Replies-Password` | `GIFT_REPLIES_DIR`，默认 fan-hub `gift_replies/` |
| 房间消息管理 | `/room-messages` | `/room` | `website/templates/room_messages.html` | `/api/room-messages/data`、`/api/room-messages/summary`、`/api/room-messages/ignore-latest-batch`、`/api/room-messages/undo-ignore` | `ROOM_MESSAGES_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Room-Messages-Password` | `ROOM_MESSAGES_CSV_PATH`，默认 fan-hub `messages.csv`；`ROOM_AUDIO_TRANSCRIPTS_PATH`，默认 fan-hub `audio_transcripts/room_audio_transcripts.jsonl`；`ROOM_MESSAGES_IGNORE_PATH`，默认 `website/data/room_messages_ignored_batches.json`；`ROOM_MESSAGES_IGNORE_DIRECT_*` 用于两台网站服务器直连同步忽略状态 |
| 计分礼物管理 | `/score-gifts` | `/sg` | `website/templates/score_gifts.html` | `/api/score-gifts/data`、`/api/score-gifts/summary` | `SCORE_GIFTS_PASSWORD`，默认复用 `GIFT_REPLIES_PASSWORD`；`X-Score-Gifts-Password` | `SCORE_GIFTS_DATA_PATH`，默认 fan-hub `score_gifts.json` |

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
curl -sS -D - -o /dev/null https://cjy.plus/gift-replies
curl -sS -D - -o /dev/null https://cjy.plus/gr
curl -sS -D - -o /dev/null https://cjy.plus/room-messages
curl -sS -D - -o /dev/null https://cjy.plus/room
curl -sS -D - -o /dev/null https://cjy.plus/score-gifts
curl -sS -D - -o /dev/null https://cjy.plus/sg
```

阿里云在用户确认腾讯云手动验证通过后再测，对应域名为 `https://cjy.xn--6qq986b3xl`。
