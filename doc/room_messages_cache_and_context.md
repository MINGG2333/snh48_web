# 房间消息缓存与上下文展开

> 最后更新：2026-11-01

本文记录 `/room-messages`（短链 `/room`）在 2026-11-01 之后的缓存模型和“拓展上下文”交互。

## 背景

房间消息事实表包含约 19 万条可见消息、200MB 左右的月封存文件加主文件。旧实现会在数据更新后整表重新解析：

- 每次重建同时保留旧缓存和新数据，进程常驻可达到约 1.7GB RSS + 1.7GB swap；
- 重建线程持有缓存锁，筛选、摘要轮询等请求一起排队；
- 在 7GB 内存的阿里云节点上会触发 swap thrash，页面表现为筛选时长时间卡死。

## 当前缓存模型

代码：`website/room_messages_api.py`。

1. **stale-while-revalidate**
   - 请求优先返回上一次成功缓存；
   - 数据签名变化时只启动一个后台重建线程，请求不等待；
   - 强制重建，例如忽略/撤销忽略礼物后需要立即返回新摘要时，才同步重建。
2. **主文件增量重载**
   - `messages_2*.jsonl` 月封存文件按签名缓存，只有月文件或封存清单变化时才重新读取；
   - 日常只重新解析 `metadata/messages.jsonl` 主文件；
   - 上麦事件 `room_voice_events.jsonl` 每次重新读取（文件很小）。
3. **内存收缩**
   - 缓存行不再保存 `_search_text` 拼接副本，关键词筛选按字段直接匹配；
   - 房间动态的 `raw_extInfo` 只在解析/前后 diff 时使用，进入缓存前移除；
   - 发送者索引只保存昵称到行号的映射，供发送者筛选使用。
4. **最低刷新间隔**
   - 数据签名变化且距上次重建不足 `ROOM_MESSAGES_REBUILD_MIN_INTERVAL_SECONDS` 时继续返回旧缓存，避免持续重建。

## 上下文展开

### API

`GET /api/room-messages/context`

鉴权：与房间消息页相同，使用 `X-Room-Messages-Password`。

参数：

| 参数 | 说明 |
|------|------|
| `message_id` | 作为锚点的可见消息 ID |
| `direction` | `before` 或 `after`，相对锚点向前/向后读取 |
| `limit` | 1–100，默认 20 |

行为：

- 在**未过滤**的完整可见消息序列中定位锚点；
- 返回锚点之前或之后的连续消息，包含其他类型/其他发送者，实现“上下文”；
- 不改变当前筛选条件，也不影响原有 `data` 接口的游标。

响应：

```json
{
  "items": [],
  "message_id": "锚点消息 ID",
  "direction": "before",
  "start_index": 100,
  "end_index": 120,
  "has_more_before": true,
  "has_more_after": true
}
```

`/api/room-messages/data` 和 `context` 返回的每条消息新增公开字段 `row_index`，表示该消息在完整可见序列中的位置。

### 前端

代码：`website/templates/room_messages.html`。

- 筛选结果中，相邻两条消息的 `row_index` 不连续时，在它们之间显示一个与消息卡片等宽的面板，自上而下为：
  - “中间还有 N 条其他消息”
  - “↓ 拓展下文”：以**上方**消息为锚点，加载它之后的上下文；
  - “↑ 拓展上文”：以**下方**消息为锚点，加载它之前的上下文。
- 两个按钮上下排列、扁长铺满卡片宽度，先下文后上文，贴合“上一条消息 → 下文 → 上文 → 下一条消息”的阅读顺序。
- 上下文消息带“上下文”标签，并使用虚线卡片区分；
- 展开时保持当前锚点消息的屏幕位置，避免页面跳动；
- 上下文滚动加载后，会重新计算剩余间隔并继续显示两端按钮；
- 分页补载会按消息 ID 去重，避免上下文消息与筛选结果重复；
- 交互追踪只记录 `action`、`direction`、`message_id`、`result` 和数量，不记录消息正文。

## 验证

```bash
PYTHONPYCACHEPREFIX=/tmp/snh48_web_pycache /home/snh48_web/venv/bin/python -m unittest \
  tests.test_room_messages_api tests.test_room_messages_template tests.test_shared_state_mutators

awk '/^  <script>$/{flag=1; next} /^  <\/script>$/{flag=0} flag {print}' \
  website/templates/room_messages.html > /tmp/room_inline.js
node --check /tmp/room_inline.js
```

上线后检查：

- 连续刷新房间消息页，首次加载后其他请求不再长时间阻塞；
- 等待主文件新增消息，确认请求仍快速返回，后台完成后摘要时间更新；
- 输入发送者筛选，确认结果正常且消息间出现扩展按钮；
- 点击“拓展上文/拓展下文”，确认其他类型消息插入且滚动位置稳定。
