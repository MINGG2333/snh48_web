# 阿里云 HTTPS 证书与月度提醒机制

更新日期：2026-07-05 CST +0800

本文件记录阿里云公开站 `cjy.我爱你` / `cjy.xn--6qq986b3xl` 的 HTTPS 证书续期与提醒机制。它的目标是让接入本工程的 Codex 先知道：证书由 Certbot 自动续期，月度 cron 负责提醒和留下可查记录；证书仍有效时不要手动替换。

## 当前状态

- 2026-07-05 已确认阿里云线上 HTTPS 可用。
- `certbot certificates` 显示证书名为 `cjy.xn--6qq986b3xl`，域名包含 `cjy.xn--6qq986b3xl` 和 `www.cjy.xn--6qq986b3xl`。
- 当前证书到期时间：`2026-09-02 00:09:46+00:00`，检查时剩余约 58 天。
- 阿里云存在 `certbot.timer`，用于 Certbot 自动续期。

## 组件

| 项 | 位置 |
|----|------|
| Nginx 配置 | `/etc/nginx/conf.d/cjy.xn--6qq986b3xl.conf`，仓库来源 `deploy/nginx-aliyun.conf` |
| 证书路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem` |
| 私钥路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/privkey.pem` |
| 自动续期 | `certbot.timer` / `certbot.service` |
| 月度提醒脚本 | `/home/snh48_web/script/check_https_certificate.py` |
| 月度提醒日志 | `/var/log/snh48/https-cert-reminder.log` |
| 最新提醒报告 | `/home/snh48_web/website/data/ops_reminders/https_certificate.md` |

## 月度提醒 cron

生产环境在阿里云 root crontab 中保留这一行：

```cron
0 10 1 * * cd /home/snh48_web && /usr/bin/python3 script/check_https_certificate.py --host cjy.xn--6qq986b3xl --cert-file /etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem --output /home/snh48_web/website/data/ops_reminders/https_certificate.md >> /var/log/snh48/https-cert-reminder.log 2>&1
```

这条任务每月 1 日 10:00 CST 运行一次，检查公网正在服务的 TLS 证书和本机 Let's Encrypt 证书文件，输出 Markdown 报告并追加日志。它只提醒和检查，不负责续期。

## Codex 接入检查

处理阿里云、HTTPS、Nginx、证书或部署问题时，先执行这些只读检查：

```bash
ssh -F /dev/null root@8.210.188.184 "certbot certificates"
ssh -F /dev/null root@8.210.188.184 "systemctl list-timers --all | grep -E 'certbot|acme' || true"
ssh -F /dev/null root@8.210.188.184 "crontab -l | grep 'check_https_certificate.py' || true"
ssh -F /dev/null root@8.210.188.184 "tail -n 40 /var/log/snh48/https-cert-reminder.log 2>/dev/null || true"
```

本地或服务器上也可以手动运行脚本：

```bash
python3 script/check_https_certificate.py \
  --host cjy.xn--6qq986b3xl \
  --cert-file /etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem \
  --output /home/snh48_web/website/data/ops_reminders/https_certificate.md
```

如果在本地没有服务器证书文件，只检查公网证书：

```bash
python3 script/check_https_certificate.py --host cjy.xn--6qq986b3xl --skip-local-cert
```

## 续期和故障处理

证书有效且 Certbot 自动续期任务存在时，不要手动替换证书。只有出现证书临近过期、自动续期失败、浏览器显示证书无效、Nginx 实际加载路径不一致等情况，才进入修复。

优先在阿里云执行诊断：

```bash
certbot renew --dry-run
nginx -t
systemctl status nginx
```

如果确需续期或修复，先确认 DNS、80/443 入站和 Nginx 配置，再执行 Certbot，并在成功后 reload Nginx：

```bash
certbot renew --cert-name cjy.xn--6qq986b3xl
nginx -t && systemctl reload nginx
```

如果浏览器与脚本结果不一致，优先排查浏览器缓存、访问域名是否为 `cjy.xn--6qq986b3xl`、Nginx 实际加载配置、证书链、DNS 解析和本机时间。

## 维护规则

- 证书和私钥不进 Git。
- 月度提醒输出是运行时状态，位于 `website/data/ops_reminders/`，不进 Git。
- 修改提醒 cron、证书路径、域名或服务器时，同步更新 `AGENTS.md`、`doc/codex/project_profile.md`、`doc/running_status.md` 和本文件。
- 修改 Nginx 配置后必须运行 `nginx -t`，通过后才能 reload。
