# 用户操作记录与审计

本文说明网站记录哪些用户操作、存在哪里、怎么查询，以及“保留期”的含义。
**不修改隐私政策页面；任何对用户可见的文字变更都需要先确认。**

## 记录范围

前端统一脚本 `website/static/js/tracker.js`：

- 页面浏览：路径、标题、来源页；
- 带 `data-track` 的点击；
- 页面自定义事件；
- 全局媒体事件：`play` / `pause` / `seeked` / `ended`（含媒体文件名、当前时间、总时长）；
- 媒体下载点击（去除 query/token，只保留路径和文件名）。

页面额外上报：登录尝试、筛选、导出、弹窗、转录纠错、模型切换等。

服务端中间件 `website/main.py::audit_write_requests` 独立记录所有写请求
（POST/PUT/PATCH/DELETE），不依赖前端；密码、Token、Cookie、密钥字段自动脱敏。

## 存放位置

```text
website/data/interaction_logs/session_<启动时间>/
├── user_events.jsonl              所有用户事件
├── user_<client_id>_events.jsonl  按会话分开
├── user_<client_id>_events.md     人可读摘要
├── visitor_page_views.jsonl       访问记录（不透明 visitor_id、粗粒度设备、IP）
└── notification_center.md         重要事件

<snh48-fan-hub>/private_handover/web_state/audit/
└── user_actions-YYYYMM.jsonl      服务端写操作审计（按月）
```

观察页 `/ob` 已按访客聚合访问、设备、网络和事件。

## 事件字段（schema_version = 2）

```json
{
  "client_id": "user_xxx",
  "event_type": "media_seek",
  "schema_version": 2,
  "timestamp": "2026-11-09T08:02:44.575823",
  "data": {
    "page": "/flip",
    "media": "【SNH48-陈嘉仪】翻牌语音_1326....mp3",
    "media_kind": "audio",
    "current_time": 12.3,
    "duration": 60.1,
    "action": "可选动作名",
    "result": "可选结果"
  }
}
```

审计记录字段：`ts`、`method`、`path`、`query`、`status`、`duration_ms`、`ip`、
`user_agent`、`visitor_id`、`body`（脱敏后）。

## 查询

```bash
# 最近 7 天汇总
script/user_activity_report.py --days 7

# 指定日期 + JSON
script/user_activity_report.py --date 2026-11-09 --json

# 单个会话
script/user_activity_report.py --days 30 --client user_xxx
```

## “保留期”是什么意思

保留期是**热数据在网站磁盘上保留多久**的策略，不等于“到期永久删除”。

当前行为：

- 网站日志和审计记录**没有自动删除任务**，会一直留在磁盘上；
- `snh48-wholesite-log-archive` 只处理 Nginx 日志，且必须先上传 COS 校验成功后才删除本地归档文件；
- 用户操作日志和审计记录目前**不在任何自动删除范围内**。

建议的长期策略：

1. 热数据保留 180 天，便于 `/ob` 和报告直接查询；
2. 超过 180 天的会话目录和审计文件打包（带 SHA-256 manifest）归档到 NAS/COS；
3. 归档校验成功并留存 manifest 后，才允许清理本地副本；
4. 任何自动清理策略上线前需要明确确认，默认不删除。

也就是说：**除非人工确认并完成归档校验，数据不会因为“过了保留期”而永久消失**。

## 隐私边界

- 只使用服务端签发的匿名 `visitor_id` 和会话级 `client_id`；
- 不做浏览器指纹、不采集画布/字体/GPU 等主动指纹；
- 设备信息只使用 User-Agent 推导的粗粒度标签；
- 审计记录中的敏感字段统一写成 `***`。
