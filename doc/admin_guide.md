# 🛡️ 网站管理员指南

> 本文档面向网站管理员，说明如何查看和管理网站的用户行为日志、通知中心及相关功能。

---

## 📂 日志文件总览

### 什么是"会话"？

**会话（Session）** 是指一次后端服务从启动到关闭的完整运行周期。每次重启后端服务（例如执行 `uvicorn website.main:app` 或重启 Docker 容器），都会自动创建一个新的会话目录。

会话目录的命名格式为 `session_{启动时间戳}`，例如：
- `session_20260521_033000` — 表示 2026 年 5 月 21 日 03:30:00 启动的会话

> 💡 **注意：** 每次重启后端都会新建会话目录，旧会话的日志不会丢失，但新的事件会写入新会话目录中。

### 会话目录在哪？

所有日志文件位于 `website/data/interaction_logs/` 目录下，按会话组织：

```
website/data/interaction_logs/
├── session_20260521_033000/    ← 一个会话目录
│   ├── notification_center.md  ← 通知中心（重要事件汇总，有事件时才生成）
│   ├── user_events.jsonl       ← 用户行为日志（所有用户混合，JSONL）
│   ├── user_xxx_events.jsonl   ← 按用户分开的行为日志（JSONL）
│   ├── user_xxx_events.md      ← 按用户分开的行为日志（Markdown，人类可读）
│   ├── email_requests.md       ← 邮箱请求汇总
│   ├── complaints/             ← 投诉记录目录
│   ├── combined.jsonl          ← 所有用户的 QA 交互日志
│   ├── combined_llm.jsonl      ← 所有用户的 LLM 调用日志
│   ├── user_xxx.jsonl          ← 特定用户的 QA 交互日志
│   └── user_xxx_llm.jsonl      ← 特定用户的 LLM 调用日志
├── session_20260520_120000/    ← 上一个会话（旧日志）
├── _all_notifications.md       ← 总通知中心（跨所有会话）
└── ...
```

### 核心文件

| 文件 | 说明 | 查看方式 |
|------|------|----------|
| `notification_center.md` | **通知中心** — 所有需要管理员关注的事件汇总（有事件时才生成） | 直接打开 Markdown 文件 |
| `user_events.jsonl` | 所有用户行为的机器可读日志（JSONL 格式，所有用户混合） | 可用 `cat`、`less` 或脚本分析 |
| `user_{client_id}_events.jsonl` | 按用户分开的机器可读日志（每个用户一个文件） | 可用 `cat`、`less` 或脚本分析 |
| `user_{client_id}_events.md` | 按用户分开的人类可读 Markdown 汇总（每个用户一个文件） | 直接打开 Markdown 文件 |
| `email_requests.md` | 用户邮箱请求汇总（由 QA 问答系统生成） | 直接打开 Markdown 文件 |

### 其他相关目录

| 路径 | 说明 |
|------|------|
| `complaints/` | 用户投诉记录目录，每条投诉一个文件 |
| `transcript_analyze/video_knowledge_db/qa_archive/` | QA 问答存档目录，每次问答的完整记录（JSON 格式） |

---

## 🔔 通知中心

### 通知中心是什么？

通知中心是网站所有**需要管理员关注的事件**的统一汇总页面。当用户进行以下操作时，会自动生成一条通知：
- 🆕 **新用户登入**（new_user）— 新用户首次访问网站（自动检测）
- 🤖 **提交问答**（qa_submit）— 用户向 AI 提问
- 🤖 **问答完成**（qa_complete）— AI 返回了回答
- 🤖 **问答超时**（qa_timeout）— 问题处理超时
- 📧 **提交邮箱**（email_submit）— 用户留下邮箱等待结果
- 📋 **提交投诉**（complaint_submit）— 用户提交投诉举报
- 🔑 **登录尝试**（login_attempt）— 用户尝试登录（含成功/失败）
- 📸 **截图保存**（screenshot）— 用户保存了问答截图

### 通知何时产生？

通知不是在会话启动时产生的，而是在**用户实际操作时**实时生成的。例如：
- 用户在 Q&A 页面点击"提交"按钮 → 前端 `tracker.js` 发送 `qa_submit` 事件 → 后端 `track_api` 接收 → 写入通知中心
- 用户提交投诉 → 前端发送 `complaint_submit` 事件 → 写入通知中心
- 用户尝试登录 → 前端发送 `login_attempt` 事件 → 写入通知中心

也就是说，**只有用户进行了相关操作，通知中心才会有内容**。如果没有任何用户操作，通知中心文件仅包含使用说明，没有待处理事件。

### 通知中心在哪？

通知中心有两个层级：

#### 1. 会话级通知中心（per-session）

每个会话目录下都有一个 `notification_center.md`，仅包含**当前会话**的通知。

```
website/data/interaction_logs/
├── session_20260521_033000/
│   └── notification_center.md    ← 当前会话的通知
├── session_20260520_120000/
│   └── notification_center.md    ← 上一个会话的通知
└── ...
```

#### 2. 总通知中心（global，跨会话）

所有会话的通知汇总在一个文件中，按会话分章节，方便跨会话查看。

```
website/data/interaction_logs/
└── _all_notifications.md          ← 总通知中心（跨所有会话）
```

**快速定位：**
```bash
# 进入项目根目录
cd /mnt/zhitainew/snh48_web

# 查看最近的会话目录
ls -lt website/data/interaction_logs/ | head -5

# 打开当前会话的通知中心
cat website/data/interaction_logs/$(ls -t website/data/interaction_logs/ | head -1)/notification_center.md

# 打开总通知中心（跨所有会话）
cat website/data/interaction_logs/_all_notifications.md

# 或者用 less 分页查看
less website/data/interaction_logs/_all_notifications.md
```

### 通知中心包含什么？

通知中心汇总了所有**需要管理员关注的事件**，按时间倒序排列（最新事件在最上面）。每条通知包含：

```
### EVT-20260521-033000-abc123

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-21 03:30:00 |
| **类型** | 🤖 问答提交 |
| **用户** | `user_a1b2c3d4_xyz789` |
| **页面** | `/qa` |
| **问题** | 陈嘉仪最近有什么活动？ |
| **邮箱** | `user@example.com` |
| **处理状态** | ⏳ 待处理 |
| **处理备注** | |
```

### 哪些事件会出现在通知中心？

| 事件类型 | 触发条件 | 建议处理方式 |
|----------|----------|-------------|
| 🆕 **新用户登入** | 新用户首次访问网站（自动检测） | 查看该用户的操作记录 `user_{client_id}_events.md` |
| 🤖 **问答提交** | 用户向 AI 提问 | 关注问题内容，如有违规及时处理 |
| 🤖 **问答完成** | AI 返回了回答 | 检查回答质量，如有问题可手动修正 |
| 🤖 **问答超时** | 问题处理超过 5 分钟 | 检查服务器负载，确认 LLM 服务正常 |
| 📧 **邮箱提交** | 用户留下邮箱等待结果 | 及时通过邮箱回复用户 |
| 📋 **投诉提交** | 用户提交投诉举报 | **优先处理**，参考 `complaints/` 目录下的详细记录 |
| 🔑 **登录尝试** | 用户尝试登录（成功/失败） | 关注频繁失败的情况，可能存在暴力破解 |
| 📸 **截图保存** | 用户保存了问答截图 | 无需特别处理，了解用户使用情况 |

### 处理流程

1. **打开通知中心** — 找到最新的 `notification_center.md`
2. **浏览通知列表** — 从最新事件开始，逐一查看
3. **标记处理状态** — 在 Markdown 文件中直接编辑：
   - `⏳ 待处理` → `✅ 已处理`（已处理完成）
   - `⏳ 待处理` → `❌ 已忽略`（无需处理）
4. **填写处理备注** — 在 `处理备注` 中记录处理结果
5. **处理邮箱请求** — 如果用户留下了邮箱，请及时回复
6. **处理投诉** — 投诉事件请参考 `complaints/` 目录下的详细投诉记录

> 💡 **建议：** 每天查看一次通知中心，及时处理用户请求和投诉。

---

## 📊 用户行为日志

### user_events.jsonl（机器可读）

每行一个 JSON 对象，适合用脚本分析：

```bash
# 进入项目根目录
cd /mnt/zhitainew/snh48_web

# 找到最新会话目录
SESSION_DIR=$(ls -t website/data/interaction_logs/ | head -1)

# 查看最新事件
tail -5 "website/data/interaction_logs/$SESSION_DIR/user_events.jsonl" | python -m json.tool

# 统计事件类型分布
cat "website/data/interaction_logs/$SESSION_DIR/user_events.jsonl" | python -c "
import json, sys, collections
counts = collections.Counter()
for line in sys.stdin:
    try:
        event = json.loads(line)
        counts[event['event_type']] += 1
    except: pass
for k, v in counts.most_common():
    print(f'{k}: {v}')
"

# 查看所有 QA 问题
cat "website/data/interaction_logs/$SESSION_DIR/user_events.jsonl" | python -c "
import json, sys
for line in sys.stdin:
    try:
        event = json.loads(line)
        if event['event_type'] == 'qa_submit':
            print(event['data'].get('question', ''))
    except: pass
"
```

### user_{client_id}_events.md（按用户分开的人类可读日志）

每个用户一个 Markdown 文件，按时间倒序排列该用户的所有事件。方便查看特定用户的行为记录。

```bash
# 进入项目根目录
cd /mnt/zhitainew/snh48_web

# 找到最新会话目录
SESSION_DIR=$(ls -t website/data/interaction_logs/ | head -1)

# 查看特定用户的行为记录（替换 client_id 为实际值）
less "website/data/interaction_logs/$SESSION_DIR/user_xxx_events.md"

# 列出所有用户的 Markdown 日志文件
ls "website/data/interaction_logs/$SESSION_DIR/"*_events.md
```

---

## 📧 邮箱请求管理

`email_requests.md` 文件记录了用户留下的邮箱请求，包括：
- 超时后用户留下的邮箱（等待结果）
- 全面性不足时用户留下的邮箱（请求更全面回答）
- 内容安全审核时用户留下的邮箱（等待审核通过）

**处理方式：**
1. 打开 `email_requests.md` 查看所有待处理的邮箱请求
2. 根据请求类型（超时/全面性/安全审核）准备回复内容
3. 通过邮箱回复用户
4. 在文件中标记已处理

---

## 📋 投诉管理

投诉记录存储在 `complaints/` 目录下，每条投诉一个文件。

**处理流程：**
1. 查看通知中心中的投诉通知
2. 打开 `complaints/` 目录找到对应的投诉记录
3. 根据投诉内容进行调查和处理
4. 如有邮箱，通过邮箱回复处理结果
5. 在通知中心中标记已处理

---

## 🔐 安全注意事项

1. **日志文件包含用户信息**（邮箱、IP 地址等），请妥善保管，不要公开分享
2. **定期清理旧日志**，避免磁盘空间不足
3. **关注登录尝试日志**，如有大量失败记录，可能存在暴力破解攻击
4. **投诉信息需保密处理**，不得泄露投诉人信息

---

## 🚀 快速命令参考

```bash
# 进入项目根目录
cd /mnt/zhitainew/snh48_web

# 找到最新的会话目录
SESSION_DIR=$(ls -t website/data/interaction_logs/ | head -1)
echo "当前会话: $SESSION_DIR"

# 查看通知中心
less "website/data/interaction_logs/$SESSION_DIR/notification_center.md"

# 查看邮箱请求
less "website/data/interaction_logs/$SESSION_DIR/email_requests.md"

# 查看用户事件日志（最新 20 条）
tail -20 "website/data/interaction_logs/$SESSION_DIR/user_events.jsonl" | python -m json.tool

# 查看投诉记录
ls -la "website/data/interaction_logs/$SESSION_DIR/complaints/"

# 查看 QA 存档
ls -lt transcript_analyze/video_knowledge_db/qa_archive/ | head -10
```
