# AI 问答系统 - 邮箱收集功能说明

## 概述

本系统共提供 **4 种邮箱收集入口**，用于在用户无法即时收到 LLM 问答结果时，通过邮箱记录任务以便后续获取。

每次邮箱提交都会：
1. ✅ 伴随提交缘由信息（`action` 字段区分 4 种场景）
2. ✅ 生成唯一标识（`event_id` 包含精确到秒的时间戳 + 用户标识）
3. ✅ 写入 `email_requests.md`（人类可读）+ `email_requests.jsonl`（机器可读）
4. ✅ 写入用户事件表（`user_events.jsonl` + `user_{client_id}_events.md`）
5. ✅ 推送到通知中心（`notification_center.md`）

---

## 邮箱提交入口一览

| 入口 | 触发条件 | action 值 | 前端函数 | 后端 task_id |
|------|---------|-----------|---------|-------------|
| 全面性请求 | 回答全面性不足时用户主动提交 | `comprehensiveness_request` | `_qaCompRequest` | `comprehensiveness_request` |
| 内容安全审核 | 回答被安全审核拦截时用户提交 | `safety_review` | `_qaSafetyEmail` | `content_safety_review` |
| 超时邮箱 | 5 分钟超时后用户提交 | `timeout_email` | `_qaLeaveEmail` | 真实 task_id |
| 刷新恢复邮箱 | 刷新页面后任务未完成时用户提交 | `refresh_email` | `_qaRefreshLeaveEmail` | 真实 task_id |

---

## 入口 1：全面性请求（Comprehensiveness Request）

**触发条件**：AI 回答的全面性评分低于阈值（< 95%）时，在回答底部显示全面性提醒横幅。
**对应代码**：`qa.js` 的 `buildComprehensivenessBanner()` + `_qaCompRequest()`

### 用户界面
- 回答底部显示全面性提醒横幅（严重程度分 low / medium / high）
- 包含邮箱输入框 + 「提交请求」按钮

### 数据流
```
用户输入邮箱 → 点击提交
  → 前端校验邮箱格式
  → POST /api/qa/archive-email { task_id: 'comprehensiveness_request', email, question, client_id }
  → window._trackEvent('email_submit', { action: 'comprehensiveness_request', email, question })
```

---

## 入口 2：内容安全审核（Content Safety Review）

**触发条件**：AI 回答被内容安全审核标记（`content_safety_flagged: true`），需要人工审核。
**对应代码**：`qa.js` 的 `displayResult()` + `_qaSafetyEmail()`

### 用户界面
- 显示安全审核拦截卡片（🛡️ 图标）
- 说明"该回答需要审核"
- 包含邮箱输入框 + 「提交」按钮

### 数据流
```
用户输入邮箱 → 点击提交
  → 前端校验邮箱格式
  → POST /api/qa/archive-email { task_id: 'content_safety_review', email, question: '内容安全审核', client_id }
  → window._trackEvent('email_submit', { action: 'safety_review', email, question: '内容安全审核' })
```

---

## 入口 3：5 分钟超时弹出

**触发条件**：用户提交问题后，前端倒计时达到 **300 秒（5 分钟）**。
**对应代码**：`qa.js` 的 `showTimeoutForm()` + `_qaLeaveEmail()`

### 用户界面
- 显示超时提示卡片，包含：
  - 用户的原问题文本
  - 已耗时
  - 超时原因说明
  - 邮箱输入框 + 「提交」按钮
  - 「再次尝试获取结果」按钮

### 数据流
```
用户输入邮箱 → 点击提交
  → 前端校验邮箱格式
  → 从 sessionStorage 恢复问题内容
  → POST /api/qa/archive-email { task_id: <真实task_id>, email, question, client_id }
  → window._trackEvent('email_submit', { action: 'timeout_email', task_id, email, question })
```

---

## 入口 4：刷新页面后恢复

**触发条件**：用户提交问题后刷新页面，且任务尚未完成。
**对应代码**：`qa.js` 的 `checkPendingTask()` + `_qaRefreshLeaveEmail()`

### 核心机制
1. **提交时持久化**：在 `askQuestionAsync()` 中，成功获取 `task_id` 后立即写入：
   ```js
   sessionStorage.setItem('pending_task', JSON.stringify({
     taskId: taskId,
     question: question,
     timestamp: Date.now()
   }));
   ```
2. **完成时清理**：轮询到 completed/error 时执行 `sessionStorage.removeItem('pending_task')`
3. **刷新检测**：页面加载完成 (`init` 阶段) 自动调用 `checkPendingTask()`

### 用户界面（刷新后弹窗）
- 弹窗标题："检测到未完成的问题"
- 显示：问题文本 + 实时状态查询
- 状态自动查询：每 3 秒向后端轮询一次
- 三种状态：
  - **已完成** → 直接显示答案内容（在弹窗内 + 主页面 result 区域）
  - **处理中** → 显示已耗时 + 邮箱输入框 + 「检查完成状态」按钮
  - **处理失败** → 显示失败提示，移除邮箱/重试按钮

### 数据流
```
用户输入邮箱 → 点击提交
  → 前端校验邮箱格式
  → 从 pending 对象获取问题内容
  → POST /api/qa/archive-email { task_id: <真实task_id>, email, question, client_id }
  → window._trackEvent('email_submit', { action: 'refresh_email', task_id, email, question })
```

---

## 后端 API

### `POST /api/qa/archive-email`

位于 `router.py` 的 `@router.post("/archive-email")`

**请求体**：
```json
{
  "task_id": "<string>",
  "email": "<string>",
  "question": "<string | optional>",
  "client_id": "<string | optional>"
}
```

**响应**：
```json
{
  "success": true,
  "message": "邮箱已记录"
}
```

**行为**：
1. 获取当前 session 日志目录
2. 追加写入 `email_requests.jsonl`（JSON Lines 格式）
3. 写入 `email_requests.md`（人类可读 Markdown，按时间倒序排列）
4. 推送到 `notification_center.md`（统一通知中心）
5. 调用 `log_interaction()` 记录到标准 interaction log

---

## 唯一标识与跨文件关联

每次邮箱提交都会生成一个唯一的 `event_id`，格式为：

```
EVT-{YYYYMMDD}-{HHMMSS}-{client_id[:6]}
```

例如：`EVT-20260521-062130-abc123`

### 关联方式

| 文件 | 字段 | 示例 |
|------|------|------|
| `user_{client_id}_events.md`（操作记录列） | `EVT-...` → [email_requests.md](email_requests.md) | `EVT-20260521-062130-abc123` → [email_requests.md](email_requests.md) |
| `email_requests.md` | 事件ID 字段 | `EVT-20260521-062130-abc123` |
| `notification_center.md` | 事件标题 | `### EVT-20260521-062130-abc123` |

在 `email_requests.md` 中搜索 `EVT-20260521-062130-abc123` 即可精确定位到对应的邮箱请求记录。

---

## 数据存储位置

所有邮箱记录存储在交互日志目录下：

```
website/data/interaction_logs/
  └── session_YYYYMMDD_HHMMSS/
      ├── email_requests.jsonl          ← 邮箱收集专用日志（机器可读）
      ├── email_requests.md             ← 邮箱收集专用日志（人类可读）
      ├── notification_center.md        ← 统一通知中心
      ├── user_events.jsonl             ← 所有用户混合事件日志
      ├── user_{client_id}_events.jsonl ← 按用户分开的事件日志
      ├── user_{client_id}_events.md    ← 按用户分开的事件汇总（含操作记录列）
      └── combined.jsonl                ← 综合交互日志（含 email_collection 条目）
```

### `email_requests.jsonl` 格式

每行一条 JSON：
```json
{
  "task_id": "a1b2c3d4e5f6",
  "email": "user@example.com",
  "timestamp": "2026-05-14T04:00:00",
  "question": "用户的问题（可选）"
}
```

### `email_requests.md` 格式

```markdown
### 📧 邮箱请求 #062130

| 字段 | 内容 |
|------|------|
| **时间** | 2026-05-21 06:21:30 |
| **类型** | 📋 全面性请求 |
| **邮箱** | `user@example.com` |
| **事件ID** | `EVT-20260521-062130-abc123` |
| **任务ID** | `comprehensiveness_request` |
| **问题** | 用户的问题 |
| **存档路径** | `qa_archive/20260521_062130_xxx.json` |
```

---

## 处理流程建议（给管理员）

目前邮箱**仅收集到日志文件**，暂未实现自动发送邮件功能。如需让邮箱真正生效，建议：

1. **查看通知中心**：定期检查 `notification_center.md` 中的待处理邮箱请求
2. **匹配结果**：根据 `任务ID` 在 `qa_archive/` 目录中查找对应结果
3. **发送邮件**：通过 SMTP / 邮件 API 将结果发送给用户
4. **标记已处理**：在 `notification_center.md` 中将 `处理状态` 改为 `✅ 已处理`

示例伪代码：
```python
import json
from pathlib import Path

log_path = Path("website/data/interaction_logs/session_xxx/email_requests.jsonl")
for line in log_path.read_text().strip().split("\n"):
    record = json.loads(line)
    task_id = record["task_id"]
    email = record["email"]
    # 1. 查找 task 结果
    # 2. 发送邮件
    # 3. 记录已发送
```
