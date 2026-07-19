# 页面行为追踪最佳实践

本文记录网站页面开发时的用户行为追踪要求。新增页面、管理页、短入口或重要交互时，应在开发阶段同步设计追踪，不要等页面上线后再补。

## 2026-06-26 管理页追踪改造记录

目标：

- 让新建的计分礼物页、房间消息页、礼物回复页和观察页像 QA 页面一样记录用户操作。
- 管理员能在 `website/data/interaction_logs/session_*/user_events.jsonl` 和 `user_*_events.md` 中看到页面访问、登录尝试、筛选、导出、弹窗和状态更新。
- 追踪数据不进入业务数据，不记录密码、消息正文、关键词正文或其他敏感明文。

实施范围：

- 公共页面：已通过 `website/templates/base.html` 自动加载 `/static/js/tracker.js`。
- 独立模板：`score_gifts.html`、`room_messages.html`、`room_voice_replays.html`、`flip_cards.html`、`gift_replies.html`、`ob.html` 手动补充 tracker 引用。
- 后端标签：在 `website/user_events.py` 增加 `admin_filter`、`admin_export`、`admin_update`、`admin_modal`。

关键过程：

1. 先确认 `website/static/js/tracker.js` 的行为：自动记录 `page_view`，支持 `data-track` 点击记录，暴露 `window._trackEvent(eventType, data)`。
2. 检查哪些页面不继承 `base.html`，避免误以为所有页面都已加载 tracker。
3. 给独立管理页添加 tracker script，并封装 `trackAdminEvent()`，统一写入 `area` 字段。
4. 对每个管理页按用户操作分类补事件：
   - `login_attempt`：提交、成功、失败。
   - `admin_filter`：筛选、日期跳转、来源切换、加载目标记录。
   - `admin_export`：Excel 导出成功或失败。
   - `admin_update`：忽略批次、撤销忽略、标记已读、业务核实保存。
   - `admin_modal`：打开用户分布、业务核实、观察页详情弹窗。
5. 用 `node` 对模板内联脚本做语法检查，用 `curl` 检查页面 200 和渲染出的 HTML 是否包含 tracker 与事件调用。
6. 部署腾讯云后手动操作验证日志落盘，再同步部署阿里云并重复验证。

验证结果：

- 腾讯云和阿里云均能记录 `/score`、`/room` 等管理页的 `page_view`、登录尝试和 `admin_*` 操作。
- `admin_*` 事件只写用户操作日志，不推送通知中心；通知中心仍只推送 `new_user`、`qa_submit`、`email_submit`、`complaint_submit` 等需要处理的事件。
- 同一访问来源在不同浏览器环境、隐私模式或本地存储隔离时，可能生成多个匿名 `client_id`；可通过服务器端 `website/data/ip_clients.json` 辅助判断来源。

## 新页面开发检查清单

新增或改造页面时，先判断模板类型：

- 继承 `base.html`：默认已加载 tracker，通常只需给重要按钮加 `data-track` 或手动调用 `window._trackEvent()`。
- 独立 HTML 模板：必须显式加入：

```html
<script src="/static/js/tracker.js?v={{ static_version('js/tracker.js') }}"></script>
```

放置位置：页面主逻辑 `<script>` 之前。

每个新页面至少确认：

- 页面访问能产生 `page_view`。
- 表单提交、导出、保存、删除、筛选、日期跳转、弹窗打开等关键操作有追踪。
- 管理页登录记录提交、成功和失败，但不记录密码。
- 追踪 payload 只写状态、类型、数量、日期、布尔值、ID 等必要元数据，不写正文、密码、token、Cookie、邮箱以外的敏感数据。
- 新增事件类型时同步更新 `website/user_events.py` 的 `EVENT_TYPES`，并确认 `/ob` 页面能显示合适图标。
- 新增页面或短入口时同步更新 `doc/website_pages.md`。

## 推荐事件类型

| 场景 | 事件类型 | 说明 |
|------|----------|------|
| 页面访问 | `page_view` | tracker 自动发送 |
| 普通按钮点击 | `click` | 使用 `data-track` |
| 登录 | `login_attempt` | 写 `action` 和 `result`，不写密码 |
| 管理页筛选/跳转 | `admin_filter` | 写筛选状态、日期、来源、结果规模 |
| 管理页导出 | `admin_export` | 写导出类型、结果、行数 |
| 管理页状态修改 | `admin_update` | 写操作类型、结果、记录 ID 或批次规模 |
| 管理页弹窗 | `admin_modal` | 写弹窗类型和计数，不写正文 |

如果已有事件类型能表达，不要随意新增类型。新增类型应当有稳定含义，便于以后统计。

## 代码模式

独立管理页推荐封装：

```js
function trackAdminEvent(eventType, data) {
  if (!window._trackEvent) return;
  window._trackEvent(eventType, Object.assign({
    area: "page_area_name"
  }, data || {}));
}
```

筛选 payload 推荐封装成函数，避免每个事件临时拼字段：

```js
function filterPayload(action) {
  return {
    action: action || "apply_filters",
    has_keyword_query: Boolean(keywordInput.value.trim()),
    date_from: dateFromInput.value || "",
    date_to: dateToInput.value || "",
    limit: limitSelect.value || "100"
  };
}
```

注意：

- 不要把密码输入值、搜索关键词正文、用户弹幕正文或房间消息正文放入 payload。
- 对关键词和用户搜索条件只记录 `has_*_query` 这类布尔值。
- 对导出记录行数、批次数量、结果状态可以记录。
- 对单条业务记录可记录内部 `item_id`、`message_id` 或批次 ID，但不要记录正文内容。

## 验证命令

模板和 Python 检查：

```bash
PYTHONPYCACHEPREFIX=/tmp/snh48_web_pycache /home/snh48_web/venv/bin/python -m py_compile website/user_events.py
git diff --check
```

检查模板内联脚本语法：

```bash
awk '/<script>/{flag=1; next} /<\/script>/{flag=0} flag {print}' website/templates/score_gifts.html \
  | node -e "let s=''; process.stdin.on('data', d => s += d); process.stdin.on('end', () => { new Function(s); });"
```

本地或服务器页面烟测：

```bash
curl -fsS -o /tmp/page.html -w "%{http_code}\n" http://127.0.0.1:8000/score
rg -n "tracker\.js|admin_filter|admin_export|admin_update|admin_modal" /tmp/page.html
```

上线后确认日志：

```bash
ls -lt website/data/interaction_logs | sed -n '1,10p'
tail -n 80 website/data/interaction_logs/session_*/user_events.jsonl
tail -n 80 website/data/interaction_logs/session_*/user_*_events.md
```

腾讯云和阿里云都要各自验证一次，因为交互日志只写本机 `website/data/interaction_logs/`，不会自动跨服务器合并。

## 部署注意

- 只改模板和 `user_events.py` 时，需要重启 Python 服务，让新事件标签和模板生效。
- 只改公共静态 JS/CSS 源文件时，必须运行 `node script/obfuscate_js.cjs` 并提交 dist。
- 管理操作追踪不需要跑腾讯云到阿里云的数据同步脚本；那只同步网站必要运行数据，不部署代码。
- 用户可见页面改动仍遵守先腾讯云验证、再阿里云同步的发布顺序。
