# 页面加载与缓存策略（2026-11-01）

> 本文记录除房间消息页之外的页面加载优化。房间消息缓存和上下文展开见
> `doc/room_messages_cache_and_context.md`。

## 身份索引共享缓存

代码：`website/identity_index.py`。

- `fan_identity_index.json` 约 9.7MB，红蓝台账和计分礼物页都需要读取。
- 两个模块现在共用一份解析结果：`by_id`、`by_name` 和 `latest_by_id`。
- 网站启动后由 `identity_index.start_warmup()` 在后台预热，避免服务重启后第一次打开页面等待约 2.5 秒。
- 红蓝台账的主索引存在时，fallback 文件（`sender_identity_map.json` 等）的频繁更新不再使主索引缓存失效。该文件约每 1–2 分钟更新一次，之前会导致红蓝页反复重新解析 9.7MB。

## 红蓝台账

代码：`website/redblue_ledger_api.py`。

- `GET /api/redblue/data` 改为纯读接口，不再调用 `_sync_room_live_now()`。
- 房间/直播计分同步只由页面加载后的后台任务或手动同步按钮触发。
- `_sync_room_live_now()` 使用进程内锁串行执行，避免多个标签页或并发请求重复写入 shared state。

## 观察页 OB

代码：`website/ob_api/router.py`、`website/templates/ob.html`。

- `/api/ob/data` 增加进程内缓存，按 `_ob_data_revision()` 判断新鲜度。
- 响应使用 `orjson` 预序列化为字节并随缓存保存，避免每次对约 4.4MB 响应重复做 `jsonable_encoder`（实测约 1.7–2 秒）。
- 数据过期时先返回旧缓存，后台单线程重建；登录加载不会等待完整重建。
- 手动“加载最新”请求使用 `/api/ob/data?fresh=1`，会等待一次完整重建，确保用户点击后拿到最新数据。
- 网站启动后由 `start_cache_warmup()` 后台预热，减少第一次打开观察页的冷加载时间。
- `/api/ob/summary` 仍只返回 revision，不返回完整数据。

## 礼物回复页

代码：`website/gift_replies_api.py`。

- `summary.json` 和 `gifts.csv` 按文件签名缓存；文件未变化时不再重复解析 2.9MB CSV。
- 筛选、分组和导出继续使用缓存行，不会修改缓存对象。

## 微店订单页

代码：`website/weidian_orders_api.py`。

- `/api/weidian-orders/data` 改为 stale-while-revalidate：有缓存时立即返回，8 秒 TTL 到期后后台经共享状态通道刷新。
- 写操作仍会清空缓存，确保后续读取拿到新状态。
- 后台刷新带 generation 校验，避免旧快照覆盖写操作后的缓存。

## 验证命令

```bash
PYTHONPYCACHEPREFIX=/tmp/snh48_web_pycache /home/snh48_web/venv/bin/python -m unittest \
  tests.test_identity_index tests.test_visitor_observation tests.test_score_gifts_sender_export \
  tests.test_password_verify_endpoints

PYTHONPYCACHEPREFIX=/tmp/snh48_web_pycache /home/snh48_web/venv/bin/python -m compileall -q website
```

上线后重点观察：

- 红蓝页在 `sender_identity_map.json` 更新后仍应保持快速；`/api/redblue/data` 不再触发房间/直播同步写入。
- OB 第二次及后续加载应直接命中缓存；点击“加载最新”才等待重建。
- 礼物回复页首次解析后，重复加载不再重复读取 CSV。
- 微店订单页过期缓存会先显示旧数据，再在后台刷新。
