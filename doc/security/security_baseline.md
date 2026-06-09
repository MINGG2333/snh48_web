# 网站安全基线

> 更新日期：2026-06-09
>
> 适用范围：代码库中的 `deploy/nginx.conf`、`deploy/nginx-aliyun.conf`、FastAPI 后端、静态前端资源和部署维护流程。
>
> 重要说明：本文件记录的是当前代码库目标安全状态。线上是否已经生效，必须以服务器实际配置、Nginx reload 状态和 `curl` 验证结果为准。

## 已实施措施

| 类别 | 措施 | 主要效果 | 维护注意 |
|------|------|----------|----------|
| Nginx 安全头 | HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy | 降低点击劫持、MIME 嗅探、明文降级、外部脚本注入风险 | 腾讯云和阿里云两份 Nginx 配置必须同步维护 |
| CSP HLS 兼容 | `connect-src 'self' https:`、`media-src 'self' https: blob:`、`worker-src 'self' blob:` | 保持外部 `.m3u8` 回放和 hls.js worker 可用 | 新增 CDN、外部图片、外部 API 时必须更新 CSP |
| 后端端口收敛 | 生产环境 `HOST=127.0.0.1`，云安全组关闭公网 `8000` | 防止用户绕过 Nginx 安全头和 HTTPS | 临时调试后必须恢复本机监听并关闭安全组 |
| 可信代理 IP | 后端只在请求来源命中 `TRUSTED_PROXY_PEERS` 时采信 `X-Real-IP` / `X-Forwarded-For`，默认仅信任本机 | 降低客户端或同内网机器伪造 IP 绕过限速的风险 | Nginx 统一设置 `X-Forwarded-For $remote_addr`；多层反代需显式配置真实代理 IP |
| QA 访问控制 | 提问、异步提问、异步结果轮询均要求 `SITE_PASSWORD`；轮询还绑定 `X-Client-Id` 和一次性 `poll_token` | 防止知道 task_id 的人直接读取异步结果 | 前端自动保存并发送 `poll_token`，用户不需要记忆 |
| 防滥用限速 | QA、密码尝试、scroller 登录、邮箱提交、追踪事件、投诉、余额查询、OB 登录尝试均有限速 | 控制 API 成本和暴力尝试 | 默认阈值在 `website/config.py`，可由 `.env` 覆盖 |
| 余额接口缓存 | `/api/balance` 对成功结果短期缓存 | 减少公开接口对第三方 API 的压力 | 只缓存成功状态，不缓存缺少 API key 等配置错误 |
| 前端 XSS 防护 | QA 答案、引用、时光轴文本、URL、图标类名进行转义或白名单校验 | 降低后端数据或第三方数据污染后的脚本执行风险 | 新增 `innerHTML` 前必须先转义或改用 DOM API |
| 管理 Cookie | scroller 管理 Cookie 支持 `SECURE_COOKIES=true` | HTTPS 生产环境下防止 Cookie 经明文连接发送 | IP/http 临时测试时才允许设为 `false` |
| 前端构建 | 生产通过 `USE_OBFUSCATED_JS=true` 使用 `js-dist` / `css-dist` | 降低静态源码直接暴露程度，并压缩资源 | 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs` 并提交 dist |

## 生产环境必需配置

```ini
USE_OBFUSCATED_JS=true
HOST=127.0.0.1
SECURE_COOKIES=true
TRUSTED_PROXY_PEERS=127.0.0.1,::1
```

云安全组只应公网放行 `80/443`，不应公网放行 `8000`。如果备案前或故障排查需要临时暴露 `8000`，完成后必须撤销。

## 上线验证清单

在服务器上：

```bash
nginx -t
curl -I http://127.0.0.1:8000
curl -s http://127.0.0.1:8000 | head -5
```

在本地或任意公网环境：

```bash
curl -sS -D - -o /dev/null https://cjy.plus/
curl -sS -D - -o /dev/null https://cjy.plus/api/qa/status
curl -sS -D - -o /dev/null https://cjy.plus/image-proxy/health
curl -sS -D - -o /dev/null https://cjy.plus/static/js/main.js
curl -I --connect-timeout 5 http://124.222.72.203:8000
```

预期结果：

- HTTPS 响应包含 HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy。
- `http://cjy.plus` 跳转到 HTTPS。
- `/static/` 和 `/image-proxy/` 响应也包含安全头。
- 公网访问 `http://124.222.72.203:8000` 失败或超时；服务器本机访问 `127.0.0.1:8000` 正常。
- `/replay/{live_id}` 的外部 HLS 回放在 Chrome/Firefox 中可播放。
- 腾讯云和阿里云云安全组均已删除公网 `TCP:8000` 入站规则；这是云控制台操作，不能只靠代码库变更完成。

## 后续开发规则

新增或修改 API：

- 明确是否需要密码、Cookie、`X-Client-Id` 或验证码。
- 公开可写或会产生费用的端点必须加 IP 限速。
- 获取客户端 IP 必须使用 `website.rate_limiter.get_client_ip()`，不要直接信任客户端传入的 `X-Forwarded-For`。
- 如果引入 Docker、CLB、CDN 或多层 Nginx，必须把实际连接后端的代理 IP/CIDR 配到 `TRUSTED_PROXY_PEERS`，不要宽泛信任整个内网。
- 不在响应中暴露 API key、内部路径、完整异常堆栈或管理密码。

新增或修改前端动态 HTML：

- 优先使用 `textContent`、`setAttribute`、DOM API。
- 必须使用 `innerHTML` 时，所有来自后端、CSV、第三方 API、URL 参数或用户输入的数据都要先转义。
- URL 只允许 `http:`、`https:` 或同源相对路径；拒绝 `javascript:`、`data:`、协议相对 URL。
- 图标类名等 class 片段必须做白名单或格式校验。

新增外部资源：

- 同时更新 `deploy/nginx.conf` 和 `deploy/nginx-aliyun.conf`。
- 按资源类型更新 CSP：脚本用 `script-src`，样式用 `style-src`，字体用 `font-src`，图片用 `img-src`，XHR/HLS playlist/segment 用 `connect-src`，媒体播放用 `media-src`。
- 修改后必须运行 `nginx -t`，并在测试环境确认对应页面不被 CSP 阻断。

修改 JS/CSS：

```bash
node script/obfuscate_js.cjs
git add website/static/js-dist/ website/static/css-dist/
```

服务器不要求安装 Node.js；构建产物必须随代码提交。

## 已知取舍

- 当前 CSP 仍保留 `'unsafe-inline'`，用于兼容现有模板内联脚本和样式。长期更严格方案是迁移到 nonce/hash CSP。
- `connect-src https:` 较宽，主要为兼容外部 HLS playlist 和分片。若后续回放来源固定，可收窄为指定 CDN 域名。
- HSTS 使用 `includeSubDomains`。如果未来新增子域名，该子域名也必须支持 HTTPS，否则浏览器会拒绝明文访问。
- Nginx 安全头目前在 server 块和多个 location 中重复声明，以规避 `add_header` 继承问题；修改 CSP/安全头时必须同步所有重复位置，长期可改为 Nginx include 片段降低维护风险。
- 如果未来接入 CDN、CLB 或 Docker 反向代理，必须重新确认真实连接后端的代理 IP，并只把这些 IP/CIDR 加到 `TRUSTED_PROXY_PEERS`。
- 多数滑动窗口限速为进程内存状态，服务重启会重置；IP 日配额为持久化 JSON。
- 前端混淆不是访问控制，真正的保护仍依赖后端鉴权、限速和不泄露敏感数据。
- 本文件不能证明线上已部署，线上状态必须按验证清单复核。
