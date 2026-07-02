# 多服务器部署工具

`deploy/deploy.py` 是当前推荐的部署入口。它处理代码同步、可选服务重启、可选 Nginx 配置同步、基础烟测，以及新 Ubuntu 服务器的初始引导。

旧的 `deploy/deploy.sh` 只保留为 CentOS/OpenCloudOS 初始化脚本，默认不会执行。日常部署不要使用它。

## 能力范围

这个工具分三类能力：

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 将最新代码部署到已上线服务器 | 已支持 | `deploy tencent`、`deploy aliyun`、`deploy all` 会执行远端 Git 更新、服务重启和基础烟测 |
| 无重启同步 | 已支持 | 加 `--no-restart` 后只做远端 Git 更新和验证，适合文档、Codex 规则、已构建静态资源等更新 |
| 同步 Nginx 配置 | 已支持 | 部署时加 `--nginx`，会复制或生成 Nginx 配置，先 `nginx -t`，再 reload |
| 检查远端 `.env` 键 | 已支持 | `check-env` 只比较键名，不输出真实值；可在环境变量变更后使用 |
| 同步运行数据 | 部分支持 | `sync-data` 目前面向网站必要运行数据，按 target 中配置的路径同步，不覆盖 `.env`、证书和用户运行数据 |
| 预热图片代理缓存 | 已支持 | `prewarm-image-cache` 或 `sync-data --prewarm` 会访问最新图片 URL，降低首次打开失败率 |
| 全新 Ubuntu 服务器初始化 | 半自动支持 | `bootstrap-ubuntu` 会安装基础依赖、clone 仓库、创建 venv 和 systemd，但不会处理云安全组、DNS、证书、真实 `.env` 和完整数据迁移 |

因此，“已部署服务器的一键代码更新”是当前成熟路径；“全新服务器一键上线”目前不是完全无人值守，需要人工完成云资源、证书、密钥和数据确认。

## 日常部署

部署腾讯云：

```bash
python3 deploy/deploy.py deploy tencent
```

部署阿里云：

```bash
python3 deploy/deploy.py deploy aliyun
```

同时部署默认目标：

```bash
python3 deploy/deploy.py deploy all
```

仅同步不重启应用：

```bash
python3 deploy/deploy.py deploy all --no-restart
```

如果本次修改包含 Nginx 配置：

```bash
python3 deploy/deploy.py deploy tencent --nginx
python3 deploy/deploy.py deploy aliyun --nginx
```

如果只改 Nginx 配置，不需要重启 Python 服务：

```bash
python3 deploy/deploy.py deploy all --nginx --no-restart
```

如果本次新增或修改了环境变量，先推送 `.env.example`，再检查远端 `.env` 键是否需要补齐：

```bash
python3 deploy/deploy.py check-env all
python3 deploy/deploy.py deploy all --check-env
```

## 是否需要重启

| 变更范围 | 推荐动作 |
|---|---|
| Python 代码、依赖、`.env`、服务入口 | 普通 `deploy`，让工具重启服务 |
| 仅文档、Codex 文件、部署说明 | `deploy --no-restart` |
| 仅静态 JS/CSS 产物、图片 | `deploy --no-restart`，验证对应静态 URL |
| 仅模板 HTML | 通常 `deploy --no-restart`，验证目标页面；若同时改 Python 上下文或路由则重启 |
| Nginx 配置、证书、CSP | `deploy --nginx --no-restart`，只 reload Nginx |
| 不确定是否启动时加载的数据或配置 | 保守重启，并记录原因 |

只验证不部署：

```bash
python3 deploy/deploy.py check tencent
```

服务重启后的验证默认最多等待 3 分钟（`--verify-attempts 90 --verify-delay 2`）。腾讯云启动时会加载本地知识库和模型，冷启动可能超过 30 秒。

先看将执行什么：

```bash
python3 deploy/deploy.py --dry-run deploy tencent
```

## 新 Ubuntu 服务器

以华为云 Ubuntu 服务器为例：

```bash
cp deploy/targets.example.json deploy/targets.local.json
```

编辑 `deploy/targets.local.json`，把 `huawei.ssh`、域名、service 名称、Nginx 配置和证书路径改成真实值。这个文件已被 `.gitignore` 排除，可以存放服务器 IP 等本地部署配置，但不要写真实密码。

初始化 Ubuntu 服务器：

```bash
python3 deploy/deploy.py --config deploy/targets.local.json bootstrap-ubuntu huawei
```

该步骤会安装基础包、clone 仓库、创建 venv、安装依赖、创建 systemd unit，并复制 `.env.example` 为远端 `.env`。它不会填写真正的密码、API Key、DNS、安全组、SSL 证书。

初始化后需要手动完成：

- 在远端 `/home/snh48_web/.env` 填入真实值，并 `chmod 600 .env`
- 配置云安全组，开放 80/443，不开放公网 8000
- 配置域名 DNS
- 申请/安装 SSL 证书
- 确认 `deploy/targets.local.json` 中的 `nginx.server_names` 和证书路径正确
- 同步知识库、行程、直播封面等运行数据

远端 `.env` 和证书就绪后启动服务：

```bash
ssh root@YOUR_HUAWEI_PUBLIC_IP "systemctl restart snh48-huawei"
```

之后日常部署同样走：

```bash
python3 deploy/deploy.py --config deploy/targets.local.json deploy huawei
```

如果需要把 target 配置中的 Nginx 配置写入服务器并 reload：

```bash
python3 deploy/deploy.py --config deploy/targets.local.json deploy huawei --nginx
```

## 运行数据同步

从腾讯云同步工具已配置的网站必要运行数据到阿里云：

```bash
python3 deploy/deploy.py sync-data tencent aliyun
```

同步后预热阿里云图片代理缓存：

```bash
python3 deploy/deploy.py sync-data tencent aliyun --prewarm
```

从腾讯云同步工具已配置的网站必要运行数据到新增目标：

```bash
python3 deploy/deploy.py --config deploy/targets.local.json sync-data tencent huawei
```

这个命令会让源服务器执行 `rsync` 到目标服务器，因此要求源服务器能 SSH 登录目标服务器。线上腾讯云到阿里云的自动数据同步不使用该推送入口，而是在阿里云 cron 中运行 `deploy/sync-from-tencent-if-changed.sh`，由阿里云每分钟按 `core` / `dynamic` 分组检查腾讯云源数据指纹，有变化时调用 `deploy/sync-from-tencent.sh` 主动拉取对应分组。`deploy/sync-to-aliyun.sh` 只作为腾讯云临时手动推送兜底。`website/data/manual_events.csv` 不由 Git 跟踪，作为运行数据同步；仓库里的 `website/data/manual_events.example.csv` 只用于说明字段格式。`website/data/room_messages_ignored_batches.json` 也是运行状态文件，不由 Git 跟踪，格式示例见 `website/data/room_messages_ignored_batches.example.json`；完整非 Git 迁移清单见 `doc/runtime_migration.md`。

只预热目标站点图片代理缓存：

```bash
python3 deploy/deploy.py prewarm-image-cache aliyun
python3 deploy/deploy.py prewarm-image-cache all --limit 120 --workers 8
```

## 边界

这个工具解决“代码部署和常规服务操作”，不负责：

- 购买或签发证书
- 修改云厂商安全组
- 修改 DNS
- 写入真实 `.env` 密钥
- 处理 Git 冲突或覆盖远端运行数据

如果远端 tracked 文件有本地修改，工具会在 `git pull` 前停止，避免覆盖服务器上的代码改动。
