# 🔍 日志与调试系统说明

## 目录

- [1. 服务启动时的自动备份](#1-服务启动时的自动备份)
- [2. 用户交互日志系统](#2-用户交互日志系统)
- [3. QA 存档 (qa_archive)](#3-qa-存档-qa_archive)
- [4. 日志详细程度说明](#4-日志详细程度说明)
- [5. 用户区分机制](#5-用户区分机制)
- [6. 常见调试场景](#6-常见调试场景)
- [7. 文件结构总览](#7-文件结构总览)

---

## 1. 服务启动时的自动备份

### 1.1 什么时候触发

每次通过 `python -m website.main` 启动 FastAPI 服务时，`startup` 事件会自动执行以下备份逻辑。

### 1.2 备份内容

#### ① qa_archive（问答存档）

| 位置 | 说明 |
|------|------|
| 原始目录 | `transcript_analyze/video_knowledge_db/qa_archive/` |
| 备份后 | `transcript_analyze/video_knowledge_db/qa_archive_backup_YYYYMMDD_HHMMSS/` |
| 动作 | 将原有 `qa_archive` **整个移走**（重命名），然后**新建空的** `qa_archive/` |

> **为什么备份？** 每次服务重启后，新产生的问答存档会从零开始，避免和上一次的存档混在一起。需要查上一次的问答记录时，去备份目录找。

#### ② 服务日志文件

| 原始文件 | 备份路径 |
|----------|----------|
| `transcript_analyze/kb_qa.log` | `transcript_analyze/logs_backup/kb_qa.log_YYYYMMDD_HHMMSS` |
| `./kb_qa.log` (项目根目录) | `transcript_analyze/logs_backup/kb_qa.log_YYYYMMDD_HHMMSS` |
| `./snh48_screen.log` (项目根目录) | `transcript_analyze/logs_backup/snh48_screen.log_YYYYMMDD_HHMMSS` |
| `/var/log/snh48/*.log` (服务器日志) | `transcript_analyze/logs_backup/对应文件名_YYYYMMDD_HHMMSS` |

> 备份方式：**复制原文件到 `logs_backup/`，然后清空原文件**（不是删除）。这样服务可以继续写日志，而旧日志已安全存档。

#### ③ 交互日志新会话

```
website/data/interaction_logs/session_YYYYMMDD_HHMMSS/
```

每次启动都会创建一个以启动时间命名的**新会话目录**，之后的所有交互日志都会写在这个目录下，不会和上次服务的日志混淆。

---

## 2. 用户交互日志系统

### 2.1 存储位置

```
website/data/interaction_logs/
├── session_20260514_033000/          ← 每次启动一个会话目录
│   ├── _events.jsonl                 ← 系统事件（启动、备份等）
│   ├── combined.jsonl                ← 所有用户的交互总日志
│   ├── combined_llm.jsonl            ← 所有用户的 LLM 调用日志
│   ├── user_abc12345.jsonl           ← 用户 abc12345 的所有交互
│   ├── user_abc12345_llm.jsonl       ← 用户 abc12345 的 LLM 调用
│   ├── user_xyz67890.jsonl           ← 用户 xyz67890 的所有交互
│   └── user_xyz67890_llm.jsonl       ← 用户 xyz67890 的 LLM 调用
├── session_20260513_220000/          ← 上一次启动的会话
│   └── ...
└── ...
```

### 2.2 文件格式

所有日志文件均采用 **JSONL** 格式（每行一个 JSON 对象）。可以直接用 `grep`、`jq` 等命令行工具处理。

```bash
# 查看某个用户的全部交互（逐行 JSON）
cat user_abc12345.jsonl | jq .

# 只看某个用户问了什么问题
cat user_abc12345.jsonl | jq '.question'

# 只看错误记录
cat combined.jsonl | jq 'select(.error != null)'

# 按时间排序（JSONL 默认就是时间顺序）
cat combined.jsonl | jq -r '.timestamp + " | " + .client_id + " | " + .question'
```

### 2.3 每条记录包含的字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `client_id` | string | 用户唯一标识（浏览器自动生成） |
| `timestamp` | string | ISO8601 时间（秒级精度） |
| `question` | string | 用户提出的问题 |
| `answer` | string | 系统返回的回答（空串表示尚未完成） |
| `citations` | array | 引用的片段列表（每条含 `citation_id`、`quoted_text`、`video_offset`、`source_type`、`reason` 等） |
| `video_results` | array | 按视频划分的独立问答结果 |
| `stats` | object | 检索统计（向量命中数、BM25 命中数、阈值过滤后数量等） |
| `archive_path` | string | 对应 qa_archive 中的 JSON 文件路径 |
| `error` | string/null | 错误信息，null 表示成功 |
| `extra` | object | 额外元信息（task_id、endpoint、状态等） |

**LLM 调用日志额外字段：**

| 字段 | 说明 |
|------|------|
| `type` | 固定为 `"llm_call"` |
| `description` | 本次调用的描述（"逐批分析第 1 批"、"最终答案合成" 等） |
| `model` | 使用的模型名 |
| `prompt` | 发送给 LLM 的完整 Prompt |
| `response` | LLM 返回的完整响应 |
| `input_tokens` | 输入 token 数 |
| `output_tokens` | 输出 token 数 |
| `success` | 是否成功 |
| `error` | 错误信息 |

---

## 3. QA 存档 (qa_archive)

### 3.1 位置

```
transcript_analyze/video_knowledge_db/qa_archive/
├── 20260513_155835_0c82f8d6.json    ← 一次问答的完整存档
├── 20260513_230547_6b751fe9.json
└── ...
```

### 3.2 什么时候生成

每次用户提问完成（无论同步 `/api/qa/ask` 还是异步 `/api/qa/ask-async`），`Response.ask()` 方法都会在 `qa_archive/` 下生成一个完整的 JSON 存档文件。

文件名格式：`YYYYMMDD_HHMMSS_随机8位.json`

### 3.3 存档包含的内容（比 API 返回更详细）

| 内容 | 说明 |
|------|------|
| `question` | 用户问题 |
| `answer` | 最终回答 |
| `citations` | 引用列表 |
| `retrieval_segments` | **所有检索到的候选片段**的完整信息（API 不返回） |
| `analysis` | **逐批分析结果**（API 不返回） |
| `useful_segments` | 被判定为有用的片段列表（API 不返回） |
| `llm_calls` | LLM 调用的完整元数据 |
| `video_results` | 按视频划分的结果 |
| `retrieval` | 检索统计（向量 + BM25 的原始命中数、过滤后数量等） |

### 3.4 调试用法

```bash
# 查看一次问答的完整内部流程
cat qa_archive/20260513_155835_0c82f8d6.json | jq '.analysis_summary'

# 查看 LLM 每一批的分析结果
cat qa_archive/20260513_155835_0c82f8d6.json | jq '.llm_calls'

# 查看所有检索到的原始候选项
cat qa_archive/20260513_155835_0c82f8d6.json | jq '.retrieval_segments | length'

# 查看被判定为有用的片段
cat qa_archive/20260513_155835_0c82f8d6.json | jq '.useful_segments[] | {segment_id, text, reason}'
```

### 3.5 如何查找某次用户交互对应的存档

在交互日志中，每个 `log_interaction` 记录都包含 `archive_path` 字段：

```bash
# 找到用户提问 "陈嘉仪和北舞的关联" 对应的存档路径
grep "陈嘉仪和北舞" user_abc12345.jsonl | jq '.archive_path'

# 直接打开该存档查看详情
cat $(grep "陈嘉仪和北舞" user_abc12345.jsonl | jq -r '.archive_path') | jq '.'
```

---

## 4. 日志详细程度说明

### 4.1 是否记录了用户看到了什么？

是的。每条交互日志都包含：

- **用户的提问** → `question` 字段
- **系统返回的回答** → `answer` 字段（完整的模型回答文本）
- **引用的信息** → `citations` 数组，每条引文包含：
  - 引用的原文片段
  - 来源视频标题和时间偏移
  - 来源类型（主播讲话/观众弹幕）
  - 该引用被选中的原因说明
- **视频级结果** → `video_results` 数组，每个视频有独立的答案和引用

### 4.2 是否记录了给用户返回的什么提示？

- **成功返回** → `answer` 字段记录了完整回答，包括引用标记 如 `[#1] [#2]`
- **错误返回** → `error` 字段记录了具体错误信息
- **无结果返回** → `answer` 字段会显示如 "未检索到可用片段" 等提示文本

### 4.3 是否记录了 LLM 内部调用？

我们提供了 `log_llm_call()` 函数，但目前的 QA 引擎内部（`VideoKnowledgeQA.ask()`）是直接调用 API 的，尚未接入这个函数。要记录完整的 Prompt/Response，需要修改 `kb_qa/qa.py` 中的 `_call_llm_json()` 方法。

**但是**，在 `qa_archive` 的 JSON 存档中已经包含了 LLM 调用的元数据（`llm_calls` 字段），可以查看每个批次的调用的结果摘要。如果想记录完整的 Prompt 和 Response 到日志文件，可以在 `qa.py` 的 `_call_llm_json` 方法中添加类似：

```python
# 在 _call_llm_json 方法中
from website.logging_setup import log_llm_call
log_llm_call(
    client_id=client_id,  # 需要传入
    description=description,
    prompt=str(messages),
    response=str(response_text),
    model=self.llm_model,
    input_tokens=usage.prompt_tokens if usage else 0,
    output_tokens=usage.completion_tokens if usage else 0,
    success=True,
)
```

---

## 5. 用户区分机制

### 5.1 前端

每个浏览器标签页在首次打开 QA 页面时，会在 `sessionStorage` 中生成一个唯一 `client_id`：

```javascript
// 格式：user_随机8字符_时间戳36进制
// 示例：user_a3f8c9d2_1k2m3n4o
clientId = 'user_' + Math.random().toString(36).substring(2, 10)
         + '_' + Date.now().toString(36);
```

- 保存在 `sessionStorage` 中，**关闭标签页即销毁**
- 每次 API 请求都通过 `X-Client-Id` 头发送
- **一个浏览器标签页 = 一个用户**（打开多个标签页会生成多个不同的 client_id）
- **同一浏览器的不同标签页不共享**（sessionStorage 隔离）

### 5.2 后端

- 从 `X-Client-Id` 请求头读取 `client_id`
- 请求头缺失时使用 `unknown_随机8位` 作为标识
- 每条日志同时写入 `combined.jsonl`（总日志）和 `user_{client_id}.jsonl`（用户单独文件）

### 5.3 如何查看特定用户的交互

```bash
# 列出当前会话有哪些用户
ls -la website/data/interaction_logs/session_20260514_*/user_*.jsonl

# 查看用户 abc12345 的所有交互
cat website/data/interaction_logs/session_20260514_*/user_abc12345.jsonl | jq .

# 使用交互日志中的 archive_path 找到对应的完整存档
cat website/data/interaction_logs/session_20260514_*/user_abc12345.jsonl | jq -r '.archive_path'

# 查看该用户的 LLM 调用日志
cat website/data/interaction_logs/session_20260514_*/user_abc12345_llm.jsonl | jq .
```

---

## 6. 常见调试场景

### 场景 1：用户反馈说回答不对，想查看当时的情况

```bash
# 1. 找到该用户的所有交互
grep "用户说的问题关键词" website/data/interaction_logs/session_*/user_*.jsonl

# 2. 查看该次交互的完整存档
archive_path=$(grep "关键词" website/data/interaction_logs/session_*/user_*.jsonl \
    | jq -r '.archive_path')
cat "$archive_path" | jq '.analysis_summary, .llm_calls'

# 3. 检查检索到了哪些信息
cat "$archive_path" | jq '.retrieval_segments[] | {segment_id, video_title, text}'

# 4. 检查哪些被判定为有用
cat "$archive_path" | jq '.useful_segments[] | {segment_id, text}'
```

### 场景 2：检查某次 LLM 调用

```bash
# 查看 LLM 调用历史（如果开启了完整日志）
cat website/data/interaction_logs/session_*/combined_llm.jsonl | jq '{
    time: .timestamp,
    desc: .description,
    model: .model,
    success: .success
}'
```

### 场景 3：对比两次不同会话的交互

```bash
# 列出所有会话
ls -d website/data/interaction_logs/session_*/

# 分别查看各会话的交互日志
wc -l website/data/interaction_logs/session_20260513_*/combined.jsonl
wc -l website/data/interaction_logs/session_20260514_*/combined.jsonl
```

### 场景 4：查看上一次服务的 qa_archive

```bash
# 找到备份目录
ls -d transcript_analyze/video_knowledge_db/qa_archive_backup_*/

# 查看上次服务的全部问答存档
ls -la transcript_analyze/video_knowledge_db/qa_archive_backup_20260513_*/
```

### 场景 5：查看服务器日志

```bash
# 服务器运行日志（nohub/systemd 方式）
tail -f /var/log/snh48/snh48.log

# 备份的旧日志
ls transcript_analyze/logs_backup/
```

---

## 7. 文件结构总览

```
snh48_web/
├── website/
│   ├── logging_setup.py              ← 🔧 日志核心模块（新建）
│   ├── logging_guide.md              ← 📖 本文档（新建）
│   ├── main.py                       ← 修改：startup 备份逻辑
│   ├── qa_api/
│   │   └── router.py                 ← 修改：添加 client_id + 交互日志
│   ├── static/js/qa.js               ← 修改：前端生成 X-Client-Id
│   └── data/
│       └── interaction_logs/         ← 每次服务的交互日志目录
│           └── session_YYYYMMDD_HHMMSS/
│               ├── _events.jsonl      ← 系统事件
│               ├── combined.jsonl     ← 总交互日志
│               ├── combined_llm.jsonl ← 总 LLM 调用日志
│               ├── user_xxx.jsonl     ← 用户 xxx 的交互
│               └── user_xxx_llm.jsonl ← 用户 xxx 的 LLM 调用
├── transcript_analyze/
│   ├── video_knowledge_db/
│   │   ├── qa_archive/               ← 本次服务的问答存档（每次启动清空）
│   │   ├── qa_archive_backup_*/      ← 上次服务的问答存档备份
│   │   ├── segment_store.json        ← 知识库数据
│   │   └── chroma_db/                ← 向量索引
│   └── logs_backup/                  ← 日志文件备份
│       ├── kb_qa.log_20260514_033000
│       ├── snh48.log_20260514_033000
│       └── ...
```

---

## 附录：命令行速查

```bash
# 格式化查看 JSONL
cat file.jsonl | jq .

# 筛选特定用户的记录
cat combined.jsonl | jq 'select(.client_id == "user_abc12345")'

# 筛选成功完成的记录
cat combined.jsonl | jq 'select(.extra.status == "completed")'

# 筛选错误记录
cat combined.jsonl | jq 'select(.error != null)'

# 只看问题和回答
cat combined.jsonl | jq '{q: .question, a: .answer[:100]}'

# 统计会话总数
ls website/data/interaction_logs/ | wc -l

# 统计某会话的交互数
wc -l website/data/interaction_logs/session_20260514_*/combined.jsonl

# 清理旧会话日志（手动）
rm -rf website/data/interaction_logs/session_20260513_*

# 清理旧 qa_archive 备份（手动）
rm -rf transcript_analyze/video_knowledge_db/qa_archive_backup_*

# 清理日志备份（手动）
rm -rf transcript_analyze/logs_backup/*
```
