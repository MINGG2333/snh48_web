# AI 问答系统 - 邮箱收集功能说明

## 概述

本系统共提供 **3 种邮箱收集入口**，用于在用户无法即时收到 LLM 问答结果时，通过邮箱记录任务以便后续获取。

---

## 入口 1：5 分钟超时弹出

**触发条件**：用户提交问题后，前端倒计时达到 **300 秒（5 分钟）**。
**对应代码**：`qa.js` 的 `showTimeoutForm()` 函数

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
  → 前端校验邮箱格式（/^[^\s@]+@[^\s@]+\.[^\s@]+$/）
  → POST /api/qa/archive-email { task_id, email }
  → 后端写入 email_requests.jsonl
  → 同时写入 combined.jsonl（type=email_collection）
```

### 涉及函数
- `showTimeoutForm(taskId, question, elapsed)` — 渲染 UI
- `window._qaLeaveEmail(taskId)` — 提交邮箱
- `window._qaRetryPoll(taskId)` — 手动重试轮询

---

## 入口 2：刷新页面后恢复

**触发条件**：用户提交问题后刷新页面，且任务尚未完成。
**对应代码**：`qa.js` 的 `checkPendingTask()` + `#refreshOverlay`

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
- 邮箱提交同入口 1

### 涉及函数
- `checkPendingTask()` — 检测 sessionStorage 并启动 UI
- `pollPending()` — 内部递归轮询函数
- `window._qaRefreshLeaveEmail()` — 弹窗邮箱提交
- `window._qaRefreshRetryPoll()` — 弹窗手动重试
- `window._qaRefreshDismiss()` — 关闭弹窗并清除记录

---

## 入口 3：5 分钟内恢复网络/回到页面

**非显式邮箱入口**，但同样依赖邮箱系统。

如果用户在 5 分钟内回到页面或有信号：
- 前端轮询自动恢复
- 无需邮箱，结果直接展示

如果用户在 5 分钟后回来看到超时表单：
- 可填写邮箱（同入口 1）
- 可点击「再次尝试获取结果」

---

## 后端 API

### `POST /api/qa/archive-email`

位于 `router.py` 的 `@router.post("/archive-email")`

**请求体**：
```json
{
  "task_id": "<string>",
  "email": "<string>"
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
3. 同时调用 `log_interaction()` 记录到标准 interaction log

---

## 数据存储位置

所有邮箱记录存储在交互日志目录下：

```
website/data/interaction_logs/
  └── session_YYYYMMDD_HHMMSS/
      ├── email_requests.jsonl          ← 邮箱收集专用日志
      ├── combined.jsonl                ← 综合交互日志（含 email_collection 条目）
      └── user_<client_id>.jsonl        ← 对应用户日志
```

### `email_requests.jsonl` 格式

每行一条 JSON：
```json
{
  "task_id": "a1b2c3d4e5f6",
  "email": "user@example.com",
  "timestamp": "2026-05-14T04:00:00"
}
```

---

## 处理流程建议（给管理员）

目前邮箱**仅收集到日志文件**，暂未实现自动发送邮件功能。如需让邮箱真正生效，建议：

1. **定时扫描**：定期检查 `email_requests.jsonl` 文件
2. **匹配结果**：根据 `task_id` 在 `qa_archive/` 目录中查找对应结果
3. **发送邮件**：通过 SMTP / 邮件 API 将结果发送给用户
4. **标记已发送**：添加 `sent: true` 字段避免重复发送

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
