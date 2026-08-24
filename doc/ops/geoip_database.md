# OB 本地地区数据库维护

OB 页使用 DB-IP City Lite MMDB，把访问日志中已有的公网 IP 临时转换为粗略国家、省级地区或城市标签。运行时只读取本地文件，不向 DB-IP 或其他查询服务提交访客 IP。

## 数据边界

- 地区标签只在通过 `OB_PASSWORD` 鉴权的 `/api/ob/data` 响应中生成。
- 标签不写回 `visitor_page_views.jsonl`、`ip_clients.json` 或其他运行日志。
- 代码只读取国家、省级地区和城市名称，明确忽略数据库中的经纬度。
- 前端不把地区追加到带时间的逐次访问行，不绘制档案的地区变化。
- 地区代表网络出口的大致注册或路由区域，移动网络、企业出口、代理和数据库误差都会降低准确性。

## IP 数量口径

OB 状态栏和 API 的地区统计使用唯一 IP 值，不是页面访问次数，也不是 IP 与浏览器档案/旧会话的关联条目数：

- `observed_ip_count`：当前 OB 数据中出现的全部非空唯一网络值。
- `eligible_ip_count`：能被 Python `ipaddress` 判断为公网可路由地址、适合查询地区的数量。
- `located_ip_count`：本地 DB-IP MMDB 实际返回地区记录的数量。
- `unresolved_ip_count`：符合公网条件但数据库没有返回记录，或地区库暂时不可用的数量。
- `non_global_ip_count`：私有、回环、保留、文档示例等非公网地址，主动跳过地区查询。
- `invalid_ip_count`：日志中的空值以外、但不是合法 IP 格式的值，例如旧记录中的占位文本。

因此，未显示地区的 IP 不会消失：它们仍保留在 IP 关联组、档案和逐次访问记录中，只是不参与地区筛选。数据库更新或更换数据源后，公网未命中数量可能变化；地区筛选不能把这些地址推断成城市。

## 安装与更新

先确认网站 venv 已安装 `website/requirements.txt` 中的 `maxminddb`。两台服务器分别执行：

```bash
cd /home/snh48_web
/home/snh48_web/venv/bin/python script/update_geoip_database.py --group snh48-web
```

默认输出路径为 `/home/snh48_web/website/data/geoip/dbip-city-lite.mmdb`。如 `.env` 使用其他路径，更新时同时传入 `--output`。数据库文件不进 Git，也不通过网站运行数据同步脚本跨云复制。

建议在每台服务器的 root crontab 中每月 5 日更新：

```cron
15 4 5 * * cd /home/snh48_web && /home/snh48_web/venv/bin/python script/update_geoip_database.py --group snh48-web >> /var/log/snh48/geoip-update.log 2>&1
```

更新脚本下载当月 `https://download.db-ip.com/free/dbip-city-lite-YYYY-MM.mmdb.gz`，限制压缩包与数据库大小，校验 MMDB 类型和查询结果，并确保数据库目录允许 `snh48-web` 组进入，然后以 `root:snh48-web 0640` 原子替换。下载或校验失败时保留原数据库。

## 验收

```bash
stat -c '%U:%G %a %s %n' /home/snh48_web/website/data/geoip/dbip-city-lite.mmdb
sudo -u snh48-web /home/snh48_web/venv/bin/python - <<'PY'
from website.ip_geolocation import lookup_ip_locations

locations, status = lookup_ip_locations(
    ["120.229.72.69"],
    "/home/snh48_web/website/data/geoip/dbip-city-lite.mmdb",
)
print(status)
print(locations)
PY
```

随后重启网站服务并登录 `/ob`：地区输入框应可用，状态显示本地地区库日期，IP 节点和历史 IP 摘要可显示地区。DB-IP Lite 要求在使用结果的网页显示 `IP Geolocation by DB-IP` 链接，OB 筛选栏已提供该署名。

部署前按 `.env.example` 检查 `OB_GEOIP_DATABASE_PATH`；只核对键名和路径，不输出密码值。
