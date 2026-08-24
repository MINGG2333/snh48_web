# 新服务器安全加固与迁移 Runbook

本文把 2026-08-24 腾讯云和阿里云安全整改沉淀为可重复执行的迁移流程。它适用于新建替代服务器、灾备恢复和云厂商迁移，不包含任何生产密码、私钥、Token 或 Cookie。

代码和模板是目标状态来源；`doc/running_status.md` 只记录时间点快照，不能复制其中的 PID 或旧版本号作为新服务器配置。

## 1. 先确定服务器角色

| 角色 | 主要职责 | 允许保存的数据 | 不应部署 |
|------|----------|----------------|----------|
| 数据生成主机 | 采集、监控、归档、生成网站数据，同时可运行内地网站 | fan-hub 全量运行数据、必要凭据、采集配置和网站运行状态 | 不必要的公网后端端口 |
| 公开网站副本 | 通过 Nginx 提供网站，只拉取网站必要数据 | 脱敏派生数据、网站运行状态、页面密码和只读监控 Token | 采集 Cookie、口袋48 Token、原始 FLV、完整配置或全量原始数据 |

新服务器如果只是替代阿里云公开站，必须按“公开网站副本”执行，不能为了方便复制整个数据生成环境。

## 2. 版本化来源

| 目标 | 仓库文件 |
|------|----------|
| SSH 仅公钥模板 | fan-hub `deploy/ssh/00-snh48-key-only.conf` |
| 腾讯云网站 unit | `deploy/systemd/snh48-web.service` |
| 公开副本网站 unit | `deploy/systemd/snh48-aliyun.service` |
| 腾讯云权限脚本 | `deploy/harden_runtime_permissions.sh` |
| 公开副本权限脚本 | `deploy/harden_aliyun_runtime_permissions.sh` |
| 腾讯云 Nginx | `deploy/nginx.conf` |
| 公开副本 Nginx | `deploy/nginx-aliyun.conf` 或 `deploy/deploy.py` 生成配置 |
| 公开副本图片代理 | fan-hub `deploy/systemd/snh48-weibo-img-proxy-aliyun.service` |
| 跨云强制命令桥 | fan-hub `deploy/privileged/snh48-shared-state-peer-bridge` |
| 主机只读验收 | `deploy/verify_server_security_baseline.sh` |
| 非 Git 运行数据 | `doc/runtime_migration.md` 与 fan-hub `doc/codex/non_git_runtime_migration.md` |

不要从 `/etc/systemd/system` 或 `/etc/nginx` 反向复制一份长期模板。先更新仓库模板、提交评审，再安装到系统路径。

## 3. 迁移前置条件

1. 确认云控制台终端或 VNC 可用，作为 SSH 配置错误时的带外入口。
2. 记录旧服务器的 DNS、证书、云安全组、白名单、弹性 IP、定时任务和外部资源。
3. 对 Git 仓库执行 `git status --short`；tracked 改动、运行数据和缓存分开处理。
4. 按 `doc/runtime_migration.md` 备份非 Git 数据；敏感备份使用加密传输和受限临时目录。
5. 先部署并验证新服务器，最后切换 DNS 或停旧服务器。不要同时让两个数据生成主机写同一权威状态。

## 4. 云控制面与操作系统

- 云安全组默认只放行 `22/80/443`。后端 `8000` 和图片代理 `8899` 不允许公网访问。
- SSH 22 如果管理出口 IP 稳定，可进一步限制来源；否则至少保持仅公钥认证。
- 安装系统安全更新、`nginx`、`acl`、Python venv 和 Certbot。内核或 libc 要求重启时另开维护窗口，不与首次迁移混在一起。
- HTTPS 证书按新域名重新签发；私钥不进 Git。确认 `certbot.timer` 或等价续期机制已启用。
- 不因提示存在 Ubuntu Pro/ESM 更新就自动绑定订阅；订阅属于独立授权决策。

## 5. 代码、依赖与生产配置

1. 从 GitHub clone 两个需要的仓库，不使用 `rsync` 覆盖代码目录。
2. 从锁定依赖重建 venv，运行 `pip check`、语法检查和目标单元测试。
3. 以 `.env.example` 为键清单创建 root 所有的 `.env`，权限 `0600`。
4. 使用 `deploy/set_env_secret.py` 从标准输入原子写入秘密；不要把秘密放进命令行参数或 shell history：

```bash
openssl rand -hex 48 | python3 deploy/set_env_secret.py \
  --file /home/snh48_web/.env \
  --key EXAMPLE_SECRET
```

生产 `.env` 至少确认 `HOST=127.0.0.1`、`SECURE_COOKIES=true`、可信代理仅包含实际 Nginx，并关闭不需要的节点能力。

## 6. SSH 仅公钥切换顺序

1. 先安装笔记本、台式机和必要自动化公钥。
2. 分别从两台管理设备执行：

```bash
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no root@新服务器IP
```

3. 安装 fan-hub SSH 模板到 `/etc/ssh/sshd_config.d/00-snh48-key-only.conf`。
4. 执行 `sshd -t`，成功后只 reload SSH 服务。
5. 保持原会话不退出，重新从两台设备建立新会话。
6. 使用禁用公钥的测试确认密码认证被拒绝；最后再关闭原会话。

模板保留 `PermitRootLogin prohibit-password`，因此 root 仍能使用受控公钥管理。未来如改为普通 sudo 管理员，应先完整迁移自动化和恢复流程，再禁止 root 登录。

## 7. 非 root 网站服务

1. 安装 `acl`，运行与角色对应的权限脚本。
2. 确认 `snh48-web` 是不可登录系统账号。
3. 安装对应 systemd unit，运行 `systemd-analyze verify` 后 `daemon-reload`。
4. 网站必须只监听 `127.0.0.1:8000`，运行文件目录为 `0700`、文件为 `0600`。
5. 数据生成主机的翻牌账号与社交 Cookie 操作使用独立 root systemd 服务；网站只连接 UID 校验的本机 Unix Socket，不授予网站账号 sudo、fan-hub 写权限或额外 capability。公开副本不启动这些桥服务。

```bash
systemctl enable --now snh48-aliyun.service
systemctl show snh48-aliyun.service \
  --property=User,UMask,NoNewPrivileges,ProtectSystem,ProtectHome,MainPID,NRestarts
```

## 8. 图片代理与 Nginx

- 公开副本使用 fan-hub 的阿里云图片代理 unit：`DynamicUser`、systemd 沙箱、`127.0.0.1:8899`。
- 数据生成主机当前图片代理可因本机/VPC 回源监听受控网络地址，但安全组仍不得公网放行 8899。
- Nginx 是唯一公网应用入口：隐藏版本、拒绝未知 Host、限制请求体、配置 HSTS/CSP/X-Frame-Options/X-Content-Type-Options、图片缓存和温和限速。
- 复制 Nginx 配置后必须先 `nginx -t`，成功才 reload；失败时保留旧配置继续服务。
- 公网 `/openapi.json` 应返回 404，后端 8000 和代理 8899 应从独立网络超时或拒绝连接。

## 9. 跨云密钥与数据同步

- root 数据拉取使用独立运维密钥；网站进程不得复用该密钥。
- 网站共享状态密钥在权威主机 `authorized_keys` 中绑定 `restrict,command=...` 强制命令。
- 用合法协议请求验证成功，再用 `id` 等交互命令验证被拒绝。
- 公开副本只拉取 `core` / `dynamic` 网站必要数据；不得加入 Cookie、Token、完整原始房间数据或采集配置。
- 拉取和手动推送脚本必须让接收端以 `root:snh48-web`、目录 `0750`、文件 `0640` 保存只读副本。原子替换 manifest/accounts 文件也必须经过同一规则；不能依赖只执行一次、随后会被 rsync 覆盖的 ACL。
- 更新服务器 IP 后同步更新云控制台登录白名单；停用旧服务器后删除旧 IP。

## 10. 跨云回放健康检查 Token

页面密码允许两台服务器保持不同。跨云检查使用独立高熵 Token：

- 阿里云网站 `.env`：`ROOM_VOICE_REPLAYS_MONITOR_TOKEN=<随机值>`。
- 腾讯云 root 配置：`/etc/snh48/room-voice-cross-cloud-health.env`，同名键、`root:root 0600`。
- Token 只通过 `X-Room-Voice-Replays-Monitor-Token` 读取 GET 元数据和音频 Range，不能调用 `/login` 或签发 Cookie。
- fan-hub 健康检查优先使用专用 Token；未配置时才兼容旧页面密码。

从 Bash 管理终端可把同一随机值顺序写到两台新服务器。Token 只短暂存在于当前 shell 内存，不落盘、不回显；任一步失败都会停止：

```bash
set -e
read -r snh48_monitor_token < <(openssl rand -hex 48)
printf '%s' "$snh48_monitor_token" | ssh root@数据生成主机 \
  'cd /home/snh48_web && python3 deploy/set_env_secret.py --create --file /etc/snh48/room-voice-cross-cloud-health.env --key ROOM_VOICE_REPLAYS_MONITOR_TOKEN'
printf '%s' "$snh48_monitor_token" | ssh root@公开网站主机 \
  'cd /home/snh48_web && python3 deploy/set_env_secret.py --file .env --key ROOM_VOICE_REPLAYS_MONITOR_TOKEN'
unset snh48_monitor_token
```

设置后只重启公开网站服务。数据生成主机的检查脚本每次读取 root 配置，不需要重启采集服务。

## 11. 主机内验收

公开网站副本：

```bash
cd /home/snh48_web
PUBLIC_BASE_URL=https://新域名 \
  bash deploy/verify_server_security_baseline.sh
```

数据生成主机当前因固定桥和图片代理网络监听，需要显式声明差异：

```bash
cd /home/snh48_web
WEB_SERVICE=snh48-web.service \
IMAGE_PROXY_EXPECT_DYNAMIC_USER=no \
IMAGE_PROXY_EXPECT_LOOPBACK=no \
PRIVILEGED_BRIDGE_SERVICES=snh48-privileged-bridge-flip.service,snh48-privileged-bridge-social.service \
ALLOWED_NETWORK_PORTS=22,80,443,8899 \
PUBLIC_BASE_URL=https://新域名 \
  bash deploy/verify_server_security_baseline.sh
```

脚本只读，不修改配置。它验证 sshd、systemd、监听端口、Nginx、安全头、私有运行目录权限，并以网站账号直接读取上麦回放 manifest，避免只读副本的属组/ACL 漂移漏检；它不能读取云厂商安全组规则。

## 12. 独立网络验收

从不在目标 VPC 内的管理设备执行：

```bash
curl --connect-timeout 5 http://新服务器IP:8000/
curl --connect-timeout 5 http://新服务器IP:8899/health
curl -sS -D - -o /dev/null https://新域名/
```

前两项必须超时或拒绝；HTTPS 应为 200，`Server` 不包含版本，并包含基线安全头。再验证未知 HTTP/HTTPS Host 被空响应拒绝、图片代理首次 MISS 后再次 HIT、密码专用 SSH 登录失败。

数据生成主机还要运行：

```bash
/home/snh48-fan-hub/venv/bin/python3 \
  /home/snh48-fan-hub/scripts/tools/monitor_process_health.py --dry-run --json
```

跨云回放项必须完成会话、消息、两种音质大小和每个媒体文件 1-byte Range 校验。

## 13. 切换、回滚与收尾

- 切换前记录服务 PID、启动时间、队列数量、revision 和同步状态。
- 新服务启动失败时只回滚对应 unit/Nginx 配置或 DNS，不清理旧服务器数据。
- SSH 加固失败时通过保持的旧会话或云控制台终端修复，不能用重装绕过。
- 共享状态切换失败时先停止新写入方，再恢复旧权威节点，禁止双主并写。
- 验收后更新 `project_profile.md` 的长期事实、稳定拓扑、健康检查说明和 `running_status.md` 的真实快照。
- 删除临时传输文件、旧 IP 白名单和停用服务器的授权公钥；敏感迁移包按策略销毁。

## 14. 2026-08-24 案例结论

本次腾讯云与阿里云整改验证了以下顺序可行：先验证全部公钥和带外入口，再关闭密码 SSH；先准备 ACL/运行目录，再切非 root systemd；先 `nginx -t`，再 reload；跨云网站密钥使用强制命令；公开副本图片代理使用回环监听和动态用户；最后从公网验证未知 Host、后端端口、缓存和安全头。案例还发现一次性 ACL 会被后续 root rsync 的原子替换覆盖，因此只读副本权限必须固化在每一次接收操作中，并由验证器以真实网站账号读取关键 manifest。

案例中的 IP、域名、PID、证书路径和云厂商版本是时间点事实。未来迁移时应替换为新目标参数，不能照抄动态值。
