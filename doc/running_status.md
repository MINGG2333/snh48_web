# /home/snh48_web 后台运行与同步状态

更新日期：2026-08-26 CST +0800

2026-08-26 06:41 阿里云 QA 长期修复完成：网站提交 `242c514` 已由 `python3 deploy/deploy.py deploy aliyun` 通过 GitHub 快进部署并重启 `snh48-aliyun.service`。此前 `/api/qa/status` 长期停留在 loading，根因为 Chroma/Pydantic 在导入时按当前工作目录读取项目 `.env`，而生产 `.env` 按安全基线为 `root:root 0600`，导致 `snh48-web` 进程导入 QA 依赖时报 `PermissionError`；早期后台线程还会把该失败表现为不可恢复的 loading。当前 QA 初始化改为服务启动阶段执行，并在导入 Chroma 时切换到服务账号可访问的 HOME，同时关闭 Chroma 后续 dotenv 探测，失败会记录 traceback 并返回可重试状态；懒加载仍有超时、代次保护和阶段状态。阿里云模型缓存保持在 `/var/lib/snh48-web/.cache/huggingface`，未修改 `.env` 权限或输出任何密钥。

线上复核：阿里云 checkout `242c514`，PID `2779192`，`active/running`、`NRestarts=0`，启动时间 06:40:38；本机和公网 `/api/qa/status` 均返回 `ready=true`、`loading=false`、`segment_count=292700`，首页、`/qa`、时间轴、Room、礼物、上麦回放、翻牌、计分礼物、静态资源、时间轴 API 和图片代理 smoke tests 全部通过。腾讯云未重启，继续按 `QA_ENABLED=false` 停用 QA；阿里云既有未跟踪运行文件保持原样。

2026-08-25 01:42 用户确认腾讯云后，阿里云网站通过 GitHub 从 `1dae795` 快进部署到 `358a65b`，重启 `snh48-aliyun.service` 后 PID `2625375`、active/running、`NRestarts=0`，01:41:27 启动，warning..emerg 日志为空；既有未跟踪 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 原样保留。部署工具的首页、时间轴、Room 礼物、综合回礼、上麦回放、翻牌、计分礼物、静态资源、时间轴 API、QA 和图片代理烟测全部通过。阿里云翻牌账号管理仍为 200/disabled，没有安装腾讯云专用账号桥、转录 venv 或敏感凭据；鉴权后账号 `172884074` 返回 373 条记录、341 条转录，媒体 1-byte Range 为 206，腾讯云与阿里云 `accounts.json` 和账号 JSON SHA-256 分别一致。阿里云安全基线全部通过。公网和本机 Certbot 证书均有效至 2026-11-01，约剩 68 天，`certbot.timer` 与月度提醒 cron 正常，本轮未修改证书或 Nginx。

2026-08-25 01:27 腾讯云修复网页验证码登录后的翻牌刷新失败，并完成用户本次账号任务。根因不是登录或 Token：任务已成功拉取 373 条记录和 10 个新语音，随后因 2026-08-24 网站虚拟环境精简后不再含 PyTorch 而在转录阶段退出；隔离桥又先后暴露出系统 `/tmp` 只读下 PyTorch 临时目录和账号清单提交锁未放行。fan-hub 提交 `892210b5`、`cae965c8`、`d12f0937`、`5c3be361` 建立 `/home/snh48-fan-hub/venv-transcription` 专用 CPU 转录环境，将翻牌和房间语音任务从网站 venv 解耦，通过 root-only 共享锁串行加载本地 `whisper-base`，并让失败提示包含具体阶段、重试时清除旧错误。网站提交 `2466aaf`、`d9d2a32`、`eaa2c62`、`6eff9c5` 保持桥服务系统 `/tmp` 只读，只精确放行短信限速、翻牌更新、转录串行化和账号清单提交四个 `root:root 0600` 锁，并把 PyTorch 临时文件限定到 `notifications/flip_web_admin/tmp` 私有目录；Hugging Face 强制离线，不上传音频或下载模型。

同轮重跑任务 `afe1f1bf1177067f575f0c80638de0a3` 最终为 200/completed：账号 `172884074` 更新为总计 373、已回复 347、待回复 7、退款 19，新增 10 条语音全部转录成功，语音转录达到 341/341；`accounts.json`、账号 JSON 和兼容副本于 01:23 同批提交。公网登录、最新任务和数据接口均为 200。受同一依赖漂移影响的 `room-audio-transcripts.timer` 已切到专用环境并恢复 active/waiting，积压 7/7 条补齐，最近 oneshot 为 success。fan-hub 15 项、网站 Python 12 项和前端 1 项专项测试通过；三个网站/桥服务 active、`NRestarts=0`、warning..emerg 日志为空，社交凭据桥仍返回微博/抖音/B站已配置状态且不含 Cookie，腾讯云安全基线全通过。阿里云代码未部署，本轮未手动触发跨云数据同步，等待腾讯云用户验收。

2026-08-25 00:40 腾讯云修复翻牌网页发送验证码返回 `操作失败（OSError）`：根因为 `snh48-privileged-bridge-flip.service` 的 `ProtectSystem=strict` 令 `/tmp` 只读，而短信限速和后台刷新仍需打开 fan-hub 的两个宿主机共享锁。提交 `aa6ac92` 在加固脚本中预创建并收紧 `/tmp/snh48-fan-hub-flip-web-rate.lock`、`/tmp/snh48-fan-hub-flip-update.lock` 为 `root:root 0600`，服务单元仅把这两个文件精确挂载为可写，没有开放整个 `/tmp`，网站进程的挂载仍为只读。两个锁在翻牌桥命名空间内均通过与生产脚本相同的 `open("a+")` 和 `flock` 验证；三个服务均 enabled、active/running、`NRestarts=0` 且重启后 warning..emerg 日志为空。公网翻牌登录、账号管理状态、最近任务接口分别为 200、200/enabled、200/completed；未重复触发真实短信。Python 12 项、前端 1 项专项测试、shell/systemd 语法和腾讯云主机安全基线全部通过。阿里云未同步，继续等待腾讯云用户验收。

2026-08-25 00:11 腾讯云翻牌账号与社交 Cookie 管理桥完成安全隔离修复：提交 `7197232` 将原先从 `snh48-web.service` 内调用的两个 sudo 包装器替换为 `snh48-privileged-bridge-flip.service` 和 `snh48-privileged-bridge-social.service`。两个 root 服务只通过 `root:snh48-web 0660` Unix Socket 接受固定命令并校验对端 UID；网页进程恢复 `NoNewPrivileges=yes`、空 capability、`ProtectHome=read-only`，在实际 mount namespace 中看到 fan-hub `config/` 和 `flip_data/` 为只读，只有对应桥服务看到明确列出的运行目录为可写。新桥启动并切换网站成功后，生产 `/etc/sudoers.d/snh48-web` 和旧包装器已删除，旧配置仅保存在 root `0700` 的 `/var/lib/snh48-web/bridge-migration-backup-20260825/` 供紧急回滚。

同轮线上验收中，三个服务均为 enabled、active/running、`NRestarts=0`，启动后 warning..emerg 日志为空；腾讯云翻牌管理能力为 true，最近任务从原先 503 恢复为 200/completed，账号 `172884074` 仍为 365 条记录；社交凭据状态从 503 恢复为 200，返回微博、抖音、B站配置槽位且不含 Cookie。真实 Cookie 替换和短信发送未用伪值触发，避免改变外部账号状态；固定命令、敏感值不进入 argv/响应、Socket 端到端传输和两个 API 的 14 项专项测试全部通过。全量 85 项测试通过 83 项，剩余 2 项为主分支既有礼物页模板文案/结构断言不一致，本次未修改对应文件。手机端翻牌“跳到最新”常驻条件同时恢复并通过前端测试。主机安全基线全部通过；阿里云尚未同步，等待腾讯云用户验收。

2026-08-24 19:37 腾讯云网站完成无 QA 运行时精简：提交 `9d9bd33` 将 `website/requirements.txt` 收敛为基础网站依赖，并让部署目标通过 `qa_enabled` 决定是否克隆知识库和安装 QA 依赖；腾讯云 systemd 写路径不再引用 `transcript_analyze/`，阿里云配置和运行环境未改。61 MiB 精简 venv 先在独立 18080 端口验证，再于最终 `/home/snh48_web/venv` 路径重建并只重启 `snh48-web.service`；当前 PID `257039`、`NRestarts=0`，`pip` 解释器路径与依赖完整性检查通过。本机和公网首页、`/timeline` 为 200，`/qa` 为本机 503，`/api/qa/status` 为 404，QA 页面不含阿里云域名或 IP；进程未加载 Torch、ChromaDB、sentence-transformers 或知识库模块。确认阿里云 QA 状态接口仍为 200 后，腾讯云删除 5.3 GiB 旧 venv 和 2.1 GiB `transcript_analyze/`，保留空 gitlink 目录以维持主仓库状态干净；全量 81 项 unittest 中 78 项通过，3 项为既有翻牌/礼物模板断言不一致。

2026-08-24 18:39 跨云回放安全遗留项完成：网站提交 `ce5fbf1` 增加独立只读监控 Token、stdin-only 原子密钥写入工具、双服务器迁移加固手册和只读基线验证器；提交 `5b8756c` 进一步修复阿里云同步后只读副本的权限漂移。Token 只保存在阿里云 `/home/snh48_web/.env` 与腾讯云 `/etc/snh48/room-voice-cross-cloud-health.env`，均为 root `0600`，没有写入 Git、日志或文档；页面密码仍可各自独立，监控 Token 不能登录或签发 Cookie。阿里云只为加载新环境变量重启 `snh48-aliyun.service`，当前 PID `2588462`、`2026-08-24 18:28:50` 启动、`NRestarts=0`；图片代理 PID `2523186` 保持不变。部署同步脚本和权限修复时没有再次重启网站或其他服务，没有重启整机，也没有订阅 Ubuntu Pro。

同轮确认旧版 root rsync 原子替换会把 `room_voice_replays/manifest.json` 恢复为网站账号不可读的 `root:root 0640`，这是认证修复后跨云检查一度报告“阿里云尚未出现最新会话”的原因。拉取与手动推送脚本现对每个接收操作强制 `root:snh48-web`、目录 `0750`、文件 `0640`；执行一次现有树修复后，18:39 的自动 cron 再次完整拉取 `core,dynamic`，清单仍为 `root:snh48-web 0640` 且 `snh48-web` 可读。跨云检查返回 `ok=true`，最新会话 `rv_20260821_235512_main_36376935_f22821` 的消息、兼容版和原始音质版均通过鉴权与 1-byte Range 校验；腾讯云总健康检查返回 `ok=true`、`missing=[]`。双服务器只读基线验证器均通过；从腾讯云独立探测阿里云 8000/8899 均超时，密码专用 SSH 仍被 `Permission denied (publickey)` 拒绝。

2026-08-24 06:07 最终复核：`snh48-aliyun.service` 当前 PID `2526577`、05:48:12 启动、`NRestarts=0`；journal 显示前一进程正常完成 application shutdown，新进程启动后标准页面/API 烟测通过，无崩溃重启。图片代理 PID 仍为 `2523186`、`NRestarts=0`。`sshd -T` 再次确认仅公钥认证；未知 HTTP/HTTPS Host 均为空响应，公网直连 8000/8899 均超时。最终文档快进到阿里云时未重启任何服务。

2026-08-24 05:38:42 阿里云安全整改完成：安全代码基线 `c066bc0`，既有未跟踪运行文件 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 均保留。`snh48-aliyun.service` enabled、active/running，PID `2523593`，05:24:49 启动，实际以 `snh48-web` UID/GID `998` 运行，`NoNewPrivs=1`、`UMask=0077`，FastAPI 只监听 `127.0.0.1:8000`；`snh48-weibo-img-proxy.service` enabled、active/running，PID `2523186`，05:22:26 启动，使用 systemd `DynamicUser`、`NoNewPrivs=1`，只监听 `127.0.0.1:8899`。运行数据目录/文件全部通过 0700/0600 检查，`.env` 为 root 0600，`/var/log/snh48` 为 root 0700 且内部文件均 0600。共享状态 outbox 为 0，action inbox 为 13 个已有事件。

同轮安全验收：笔记本、台式机公钥登录均在修改前成功；阿里云 sshd 已改为 `AuthenticationMethods publickey`，密码专用回归被 `Permission denied (publickey)` 拒绝。网站专用跨云公钥指纹 `SHA256:3ZfFX2P7LY0ElfIRQe3BPqZ3kHl5xXYF8yptL6ATqKE` 在腾讯云绑定 `mutate inbox-put` 强制命令，交互 shell 探测被 403 拒绝。Nginx `nginx -t` 通过并已 reload，未知 HTTP/HTTPS Host 均返回 444 空响应，服务头仅显示 `nginx` 而无版本号；裸域名、`www`、`/complaint` 为 200，`/openapi.json` 为 404。真实微博图片首次代理为 `MISS`、第二次为 `HIT`，公网直连 8000/8899 均超时。FastAPI 依赖已对齐 `fastapi 0.141.1`、`starlette 1.6.0`、`Jinja2 3.1.6`、`python-multipart 0.0.32`，`pip check` 通过。Ubuntu Main/Restricted 无待 unattended 安全更新；22 项 Universe/Multiverse ESM 需 Ubuntu Pro，本轮未绑定；既往 `libc6` 更新仍留有 reboot-required 标记，本轮未重启整机。

2026-08-24 06:01 腾讯云总健康检查除既有“房间上麦回放跨云同步”外全部健康；该项因阿里云业务接口 HTTP 403 连续失败 11 次。它早于本轮整改存在，阿里云网站、图片代理和公网烟测正常，作为独立跨云业务鉴权遗留项处理。

2026-08-24 04:20 腾讯云 QA 已停用并清理本地知识库：网站功能提交 `8fe2171` 通过节点级 `QA_ENABLED=false` 不再注册 `/api/qa/*`、不执行 QA 归档维护或模型预热；`/qa` 只返回本机 503 未启用页面，响应中不含阿里云域名、IP 或跳转，两个网站没有 QA 互链。腾讯云只重启 `snh48-web.service`，PID `3814128`、`active/running`、`NRestarts=0`；公网首页和 `/timeline` 为 200，`/qa` 为 503，`/api/qa/config`、`/api/qa/status` 为 404。确认阿里云 `snh48-aliyun` 仍为 `active/running`、PID `2512204`、`NRestarts=0` 且 QA 配置接口为 200 后，删除腾讯云 `chroma_db` 约 2.8G、`segment_store.json` 约 265M、`kb_description.txt` 和 root 旧嵌入模型缓存约 391M；磁盘可用空间从 2.9G 增至 6.3G。腾讯云 94 份历史问答归档约 92M 经内容清单前后校验一致，独有转录、下载记录、子项目源码和 Git 历史均保留；阿里云未重启、未删数据。目标 unittest 与编译检查通过；全量 76 项 unittest 中另有 3 项既有翻牌/礼物模板断言失败，与本次 QA 文件无关。

2026-08-24 00:49 Room 与礼物页筛选、最新定位和移动导航完成双云无中断发布：功能提交 `311061b` 已在腾讯云和阿里云生效。Room、礼物明细和综合回礼页把日期输入值与已应用值分离，只有点击“筛选”才提交日期；无新数据时“跳到最新”只平滑滚动，有新数据时才提示并加载；Room 按钮层级高于消息卡片，两个礼物页移动端互链固定在右上、筛选位于右侧第二行，综合回礼客服入口固定右下。本地 Playwright 390×844 视口确认 Room 点击 80ms 时仍在滚动、最终精确到列表底部，礼物两页无新数据点击不发 API 请求且导航无重叠。腾讯云 checkout 为 `311061b`，screen `3479202.snh48`、Python PID `3479212` 保持运行；阿里云执行 `python3 deploy/deploy.py deploy aliyun --no-restart` 快进到 `311061b`，`snh48-aliyun` 保持 `active/running`，PID `2485782`、`NRestarts=0`。两端 `/room`、`/room/gifts`、`/room/gift-senders` 均返回 200，部署工具标准烟测全部通过；未修改 Python、环境变量、Nginx、后台服务、数据同步拓扑或健康检查范围，既有运行文件与并行中的 OB 模板编辑保持原样。

2026-08-23 22:55 Room 日期筛选与移动端最新导航完成双云无中断发布：功能提交 `c9517ad` 已在腾讯云和阿里云生效。腾讯云通过阿里云既有免密链路复核时已位于目标提交，保留 screen `3352583.snh48` 与 Python PID `3352588`；阿里云执行 `python3 deploy/deploy.py deploy aliyun --no-restart` 从 `fe2d153` 快进到目标提交，`snh48-aliyun` 保持 `active/running`，PID `2468260`、`NRestarts=0`。两端公网 `/room`、`/room/gift-senders` 均返回 200，页面源码包含日期只暂存到点击“筛选”后再请求、Room 明确滚动到消息底部、送礼人页移动端顶部操作重排及固定客服入口；部署工具的首页、时间轴、礼物、上麦回放、翻牌、计分礼物、静态资源和关键 API 烟测全部通过。未修改 Python、环境变量、Nginx、后台服务、数据同步拓扑或健康检查范围；阿里云既有未跟踪运行文件保持原样。

2026-08-23 23:51 OB 3D IP 关系图完成阿里云部署：用户确认腾讯云阶段体验后，`python3 deploy/deploy.py deploy aliyun` 通过 GitHub 将网站快进到提交 `238aa0a`，重启 `snh48-aliyun`，主 PID `2485782`、状态 `active`。公网 `/ob` 返回 200，页面包含 Three.js `0.159.0`、`ForceGraph3D`、3D Canvas 与二维回退；鉴权 `/api/ob/data` 返回 1304 个成员组、583 个 IP 节点、49 条共享成员边，统计为 37 个稳定档案、1267 个旧会话和 172 条逐次访问。部署工具标准烟测、服务日志复核和公网 HTTPS 证书检查均通过，证书至 2026-11-01 有效；未修改 Nginx、环境变量或数据同步拓扑，阿里云既有未跟踪运行文件保持原样。

2026-08-23 23:40 OB 3D IP 关系图完成腾讯云阶段发布：网站提交 `0d59e6f` 已由腾讯云本机 `git pull --ff-only` 加载并重启 screen `3479202.snh48`，Python PID `3479212`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。`/api/ob/data` 新增 `ip_network_graph`，当前返回 193 个 IP 节点、19 条共享成员边，边权按共同浏览器档案/旧会话数量计算，历史关联保留低置信度标记；稳定档案、旧会话和逐次访问统计不变。公网 `/ob` 返回 200，页面包含 Three.js/`ForceGraph3D`、3D Canvas 和二维回退；`/timeline` 返回 200。本地 Playwright 桌面 1440×1000 与手机 390×844 均确认 Canvas 创建且截图非空；阿里云尚未同步，等待用户体验腾讯云后确认。

2026-08-23 20:36 OB 交互式 IP 网络图完成阿里云部署：用户确认腾讯云验收后，`python3 deploy/deploy.py deploy aliyun` 已将网站同步到提交 `5c37569`，重启 `snh48-aliyun`，远端主 PID `2468260`、状态 `active`。公网页面 `/ob` 返回 200，包含网络图节点、人物成员视图和会话悬浮逻辑；鉴权 `/api/ob/data` 返回 1302 个原始成员、542 个 IP 关联组，统计为 35 个稳定档案、1267 个旧会话和 164 条逐次访问。首页、时间轴、Room、礼物、上麦回放、翻牌、计分礼物、静态资源及关键 API 均通过部署工具烟测。证书公网检查为 OK，证书至 2026-11-01 有效，未修改证书或 Nginx；阿里云既有未跟踪运行文件保持原样。

2026-08-23 20:32 上麦回放 iPhone 播放态与顶部导航完成双云发布：网站提交 `3207f8c`（切换会话/分段前显式 `audio.pause()`，避免 iPhone Safari 保留旧的“正在播放”外观）和 `282309a`（移除顶部“退出”，改为 `/room` 的“返回 Room”链接）已推送。腾讯云通过阿里云既有免密链路快进并重启 screen `3352583.snh48`，Python PID `3352588`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`；阿里云由 `python3 deploy/deploy.py deploy aliyun` 快进并重启 `snh48-aliyun`，PID `2466759`，`active/running`、`NRestarts=0`，20:32:34 启动。两端公网 `/radio` 返回 200、未登录 `/api/room-voice-replays/sessions` 返回 401，页面均包含 `roomPageLink` 和 `pauseBeforeMediaChange`，不再包含 `logoutBtn`；阿里云既有未跟踪运行文件保持原样。桌面端布局未改动，移动端筛选仍默认收起。

2026-08-23 19:45 OB 交互式 IP 网络图完成腾讯云阶段发布：网站提交 `549acc5` 已推送并由腾讯云本机 `git pull --ff-only` 加载；现有 screen `3300763.snh48`、Python PID `3300772` 保持运行，无需重启。OB 默认显示按 IP 节点大小表达关联成员数的网络图，点击节点显示浏览器档案/旧会话人物视图，悬停成员或会话显示访问摘要；原关联组列表保留为切换视图。公网 `/ob` 返回 200，页面包含 `networkVisualization`、`ipNetworkSvg` 和会话悬浮逻辑；鉴权 `/api/ob/data` 返回 702 个原始成员、180 个 IP 关联组，统计为 99 个稳定档案、603 个旧会话和 216 条逐次访问；`/timeline` 返回 200。未加入城市、坐标、主动指纹或轨迹分析；阿里云尚未同步，等待用户确认腾讯云效果。

2026-08-23 19:31 OB IP 关联组展示完成腾讯云阶段发布：网站提交 `bb6ca36` 已推送并加载到腾讯云 screen `3300763.snh48`、Python PID `3300772`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。OB 新增仅用于整理展示的 `association_groups`，按稳定浏览器档案和旧会话共享 IP 的传递关系生成组，不改变估计访客数、稳定档案数、旧会话数或逐次访问记录；旧会话使用历史 IP 参与并明确标记限制。公网 `/ob` 返回 200，鉴权 `/api/ob/data` 返回 702 个原始成员、180 个关联组，统计仍为 99 个稳定档案、603 个旧会话和 215 条逐次访问；`/timeline` 返回 200。前端已改为默认收起的关联组总览，展开后显示成员行并可进入原详情弹窗。阿里云尚未同步，等待腾讯云验收。

2026-08-23 18:42:44 阿里云上麦回放页面完成部署复核：`python3 deploy/deploy.py deploy aliyun` 已完成 Git 快进、`snh48-aliyun` 重启和目标页面烟测；远端随后自动合并文档提交，当前 checkout 为 `33f37be`，其中保留上麦回放移动端 `filterPanel` 改动。阿里云 PID `2454218`，`active/running`、`NRestarts=0`，18:41:01 启动；公网页面 `/radio` 返回 200、未登录 `/api/room-voice-replays/sessions` 返回 401。远端既有未跟踪运行文件保持原样。

2026-08-23 18:39:59 阿里云部署网站提交 `778161a`：修复移动端日期筛选首次选择卡死风险，统一受保护页面的初始鉴权错误状态，并为 Room、礼物明细、送礼人和翻牌页调整“跳到最新”显示逻辑。`python3 deploy/deploy.py deploy aliyun` 已完成 Git 快进、`snh48-aliyun` 重启和首页、时间轴、礼物、上麦、翻牌、静态资源及关键 API 烟测；阿里云 PID `2453662`，`active/running`，`NRestarts=0`。远端既有未跟踪的 `website/data/manual_events.csv`、`website/data/runtime_backups/`、`website/static/js/timeline.js.bak` 保持原样；腾讯云未重启。

2026-08-23 18:11:33 腾讯云阶段发布上麦回放移动端筛选收纳：网站提交 `6e0cfaf` 已加载并重启 screen `3233514.snh48`，Python PID `3233519`；腾讯云 `/radio` 返回 200，未登录 `/api/room-voice-replays/sessions` 返回 401，页面已包含移动端默认关闭的 `filterPanel`。桌面端仍保留左侧会话列表；阿里云尚未同步，等待腾讯云验收。

2026-08-23 17:49 修复 Room 筛选弹窗打开后背景消息持续上滑：网站提交 `8957188` 已部署到阿里云并重启 `snh48-aliyun`。筛选锁定期间暂停全局滚动触发的前后页加载和填充视口任务，关闭弹窗恢复滚动位置期间抑制一帧误触发；线上 390×844 移动视口打开弹窗等待 2 秒，消息数保持 100，新增数据请求为 0，关闭后滚动位置从 0 恢复到原位置 5000。阿里云 PID `2448602`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 17:37 Room 页移动端导航位置与筛选滚动边界完成阿里云发布：网站提交 `d49590e` 已重启 `snh48-aliyun`。`综合回礼`、`上麦回放`位于顶部第一行，`筛选`位于统计行；390×844 移动视口测量分别为 `y=10` 与 `y=52`。打开筛选后背景 `window.scrollY` 锁定为 0，遮罩阻止触摸穿透，筛选卡片内部保持可滚动。阿里云 PID `2446857`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 17:19 修复 Room 页面移动端顶部栏消失：网站提交 `e1ebd96` 已部署到阿里云并重启 `snh48-aliyun`。移动端改为仅由 `html` 承担文档滚动，`body` 保持 `overflow: visible`，避免 `sticky` 顶部栏绑定到不实际滚动的 body 容器；390×844 移动视口登录后页面滚到底部时，顶部栏实际 `y=0`、`position: sticky`，线上截图和 DOM 计算样式复核通过。阿里云 PID `2444525`，`active/running`、`NRestarts=0`；腾讯云未重启。

2026-08-23 16:55 阿里云完成网站导航、移动端固定顶部栏、筛选弹窗和公开记忆页改造部署：网站提交 `ed020aa` 已由 `python3 deploy/deploy.py deploy aliyun` 快进并重启 `snh48-aliyun`。阿里云主 PID `2441690`，`active/running`、`NRestarts=0`；首页、`/timeline`、`/room/gifts`、`/room/gift-senders`、`/room-voice-replays`、`/flip-cards`、`/score-gifts`、静态资源、时间轴/QA/图片代理接口均通过部署烟测，公开 `/memories` 与 `/api/memories/data` 返回 200，公开记录不包含内部审核字段或 `platform_id`。阿里云既有未跟踪 `website/data/manual_events.csv`、`website/data/runtime_backups/` 与 `website/static/js/timeline.js.bak` 保持原样；本次未同步 `snh48-fan-hub` 数据、Cookie、Token、`.env` 或其他密钥。腾讯云未重启，继续运行其现有 screen 进程。

2026-08-23 16:44 观察页设备识别改为服务器签发档案 Cookie 并完成双服务器发布：网站提交 `9c3afec` 已推送。tracker 不再从浏览器存储生成或提交 `visitor_id`；首次 `page_view` 由服务端签发 HMAC 校验的 `ob_device_profile` HttpOnly Cookie，后续由服务端读取，仍只记录页面、当时 IP 和粗粒度 User-Agent 设备标签，不加入主动指纹、城市或经纬度。腾讯云因本机回连公网 SSH 无可用密钥，按既有方式确认本地 checkout 为 `9c3afec` 后重启 screen `3152206.snh48`、Python PID `3152211`，公网 `/ob`、`/timeline` 和事件接口通过；阿里云由部署工具拉取同一提交并重启 `snh48-aliyun`，PID `2440328`、active/running。两端首次事件均返回带 `HttpOnly`、`Secure` 的 `ob_device_profile`，带回同一 Cookie 的第二次事件不重新签发；两端 `/ob` 均为 200，静态 tracker 均不含 `localStorage`。

2026-08-23 10:48 社交凭据管理完成双服务器运行复核：功能提交 `149a8ca` 和非主节点隐藏修复 `437d0d6` 已部署。腾讯云 screen `2878064.snh48`、Python PID `2878066` 于 10:46:43 重启；公网 `https://cjy.plus/social-credentials-admin` 返回 200，密码登录及鉴权状态接口通过，只返回微博、抖音、B站各槽位状态，不回显 Cookie；页面与 API 使用 `no-store`，页面设置 `noindex/nofollow` 且没有站内入口。严格桥接脚本只允许腾讯云主节点在验证新 Cookie 成功后原子替换。阿里云 `snh48-aliyun`、PID `2407221` 于 10:47:48 重启，隐藏页面返回 404、API 返回 403，不能读取或更新凭据。两端 `/api/timeline/schedule` 均为 130 条，并确认不返回 2026-08-23 错误行程。

2026-08-23 10:36 客服聊天长等待更新完成双服务器发布：网站提交 `369e4e0` 已推送，两端 Gift Senders 与 OB 客服从固定 1 秒轮询改为最多约 25 秒的可恢复长等待请求，新事件通常在服务端 200 毫秒检查周期内返回；隔离 HTTP 烟测从发消息到等待请求返回约 247 毫秒。腾讯云 screen `2867975.snh48`、Python PID `2867981` 于 10:35:40 重启；阿里云 `snh48-aliyun`、PID `2405889` 于 10:36:43 重启，均已通过 `/room`、`/room/gift-senders`、`/ob` 和新客服接口烟测。飞书反馈转发服务不受网站接口实现变化影响，保持 PID `2613036`、active/running、`NRestarts=0`，未重启。

2026-08-22 19:45 翻牌成员筛选、独立更新状态和底部合并刷新入口完成腾讯云阶段发布：网站提交 `64e3d7f`、fan-hub 提交 `5309e0a` 已推送，腾讯云 screen 重启为 `2303857.snh48`、Python PID `2303871`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。账号 `172884074 / xxgg2333` 的 19:05 网页登录刷新任务已于 19:11 成功完成，Token 安全复查有效；公网账号数据为 schema v4 共 365 条、331 条语音转录，成员为陈嘉仪 364 条和闫娜 1 条，默认成员键为陈嘉仪 `161808449`。页面顶部旧“最新”按钮已移除；筛选默认陈嘉仪，逐条头像为“嘉仪”或其他成员完整姓名；独立更新状态弹窗可收起并恢复，底部按钮同时重新加载数据和跳到最新。受保护数据版本和最近任务 API、媒体 Range 206、伪造跨站 POST 403、账号清单无手机号/Token/验证码字段均通过。阿里云代码尚未部署，等待用户验收腾讯云后再同步同一提交。

2026-08-22 18:48 翻牌多账号与腾讯云网页验证码登录完成腾讯云阶段发布：网站功能提交 `24e7f7b`、空配置修复 `a5246d7`、fan-hub 提交 `24f4ddc` 已推送，腾讯云 screen 重启为 `2255530.snh48`、Python PID `2255534`，继续覆盖 `QA_WARMUP_ON_STARTUP=false`。公网 `/flip-cards` 已包含账号选择器和统一管理弹窗；受保护 API 返回默认账号 `172884074 / xxgg2333`、schema v3 共 338 条、312 条语音转录，账号级媒体 Range 为 206；腾讯云账号管理能力为 true，伪造跨站 POST 为 403。现有单账号运行产物已只复制迁移到账号目录，旧文件保留。阿里云代码和同步脚本尚未部署，等待用户验收腾讯云；最终两端使用同一代码和弹窗，阿里云能力开关为 false 且不提供跨站跳转。

2026-08-22 15:20 管理员行程/事件统一入口完成腾讯云阶段发布：功能提交 `c6f2302` 已由 `cjy.plus` 加载，旧 `/api/timeline/manual-events` 返回 404，原手工文件中的“加入 SNH48 二十三期生”和“Mini Live”已迁入统一行程 CSV，并补充“陈嘉仪出道首演”里程碑。腾讯云 `/api/timeline/schedule` 当前返回 131 条。阿里云的必要行程数据已由既有 cron 自动拉到 131 条，但网站 checkout 仍为 `72d1cd1`，旧手工接口仍返回 200；这说明数据副本已更新、统一接口代码尚未部署，等待用户验收腾讯云后再发布代码。

2026-08-22 时光轴行程/事件拆分、微博/抖音统一数据、抖音稳定作品链接和微博日常去重改造已完成腾讯云验收，并按用户确认部署到阿里云；本次补处理新助手 `182321334` 的 8/16、8/17 行程后，两端 `/api/timeline/schedule` 均返回 128 条有效记录（无 `event_type=日常`），新增 8/19、8/28、8/30 行程；社交时间轴两端仍返回微博 25 条、抖音 36 条，出道 300 天仅保留一条。

抖音稳定作品链接、微博日常去重与 300 天事件合并专项复核：2026-08-22 CST +0800

观察页浏览器档案聚合腾讯云阶段发布专项复核：2026-08-16 03:18 CST +0800

计分礼物送礼用户 Excel 导出腾讯云阶段发布专项复核：2026-08-08 20:15 CST +0800

翻牌网站 HTML 移除专项复核：2026-07-21 15:31 CST +0800

电台/翻牌交互统计阿里云同步专项复核：2026-07-21 15:12 CST +0800

双服务器版本化运行状态阿里云完成发布专项复核：2026-07-21 15:15 CST +0800

翻牌应用页与阿里云同步专项复核：2026-07-20 21:54 CST +0800

双服务器版本化运行状态腾讯云阶段发布专项复核：2026-07-20 17:59 CST +0800

计分礼物刷新体验与阿里云补发专项复核：2026-07-20 12:06 CST +0800

腾讯云翻牌记录页发布专项复核：2026-07-20 04:18 CST +0800

腾讯云成员房间上麦回放发布专项复核：2026-07-17 16:13 CST +0800

腾讯云成员房间上麦双版本播放专项复核：2026-07-20 12:35 CST +0800

阿里云成员房间上麦双版本与跳转体验专项复核：2026-07-20 16:21 CST +0800

阿里云成员房间上麦回放发布与同步专项复核：2026-07-19 04:51 CST +0800

陈嘉仪/曾雪婷房间计分 PK 腾讯云发布专项复核：2026-08-08 18:07 CST +0800

本文件记录 `/home/snh48_web` 的长期运行方式和腾讯云到阿里云的数据同步口径。进程 PID 会随重启变化，排查时以文中的命令实时查询为准。

## 当前运行方式

| 环境 | 网站服务 | 监听 | 说明 |
|------|----------|------|------|
| 腾讯云 `cjy.plus` | `systemd` 服务 `snh48-web` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前运行功能基线为 `8fe2171`。PID `3814128`，active/running、`NRestarts=0`；私有 `.env` 设置 `QA_ENABLED=false`，QA API 不注册，本机不保留知识库索引或嵌入模型缓存 |
| 阿里云香港 `cjy.我爱你` | `systemd` 服务 `snh48-aliyun` | `127.0.0.1:8000`，公网由 Nginx 代理 | 当前 checkout 为 `13d4c46`。PID `2512204`，active/running、`NRestarts=0`；QA 保持启用并独立运行，腾讯云没有到该站的 QA 跳转或互链 |

## 常用状态命令

腾讯云：

```bash
systemctl status snh48-web
journalctl -u snh48-web --no-pager -n 80
ss -ltnp | grep ':8000'
```

阿里云：

```bash
systemctl status snh48-aliyun
journalctl -u snh48-aliyun --no-pager -n 80
ss -ltnp | grep ':8000'
```

Nginx：

```bash
nginx -t
systemctl status nginx
```

2026-07-17 本次重启发现既有 `/api/qa/status` 会在模型尚未加载时启动后台预热；模型加载线程会在当前小规格主机上短时占用 GIL，导致全站请求等待。当时用 `QA_WARMUP_ON_STARTUP=false` 临时规避。该问题已于 2026-08-24 通过腾讯云 `QA_ENABLED=false` 完整解决：QA 路由和预热均不加载，本地知识库与模型缓存已删除。

## 阿里云 HTTPS 证书与月度提醒

阿里云公开站 `cjy.我爱你` / `cjy.xn--6qq986b3xl` 使用 Let's Encrypt / Certbot 证书。2026-07-05 已确认线上 HTTPS 可用，证书到期时间为 `2026-09-02 00:09:46+00:00`，服务器存在 `certbot.timer`。

| 项 | 当前值 |
|----|--------|
| 证书路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem` |
| 私钥路径 | `/etc/letsencrypt/live/cjy.xn--6qq986b3xl/privkey.pem` |
| 自动续期 | 阿里云 `certbot.timer` |
| 月度提醒脚本 | `/home/snh48_web/script/check_https_certificate.py` |
| 月度提醒 cron | `0 10 1 * * cd /home/snh48_web && /usr/bin/python3 script/check_https_certificate.py --host cjy.xn--6qq986b3xl --cert-file /etc/letsencrypt/live/cjy.xn--6qq986b3xl/fullchain.pem --output /home/snh48_web/website/data/ops_reminders/https_certificate.md >> /var/log/snh48/https-cert-reminder.log 2>&1` |
| 提醒日志 | `/var/log/snh48/https-cert-reminder.log` |
| 最新提醒报告 | `/home/snh48_web/website/data/ops_reminders/https_certificate.md` |

操作细节见 `doc/ops/https_certificate_reminder.md`。证书仍有效且 Certbot 自动续期存在时，不要手动替换证书。

## 腾讯云到阿里云的数据同步任务

当前生产自动同步是“阿里云主动拉取腾讯云”，不是腾讯云主动推送。

> 2026-08-16 03:18 观察页浏览器档案聚合腾讯云阶段发布：功能提交 `3d7cf5e` 已推送并由腾讯云 screen 加载。`/ob` 不再按 IP 合并旧会话；上线后的访问使用本域浏览器档案估算访客，可把同一浏览器切换 IP 后的访问合并，并逐次显示粗粒度设备、IP 和页面。实现不查询城市、经纬度，不保存完整 User-Agent，也不使用 Canvas、字体、GPU 等主动指纹。603 条旧会话保留为单独历史记录但不计入估算人数，稳定档案从上线后的真实浏览器访问开始累积。公网 `/ob` 返回 200，未授权 `/api/ob/data` 返回 401，服务器内鉴权接口返回 200、`Cache-Control: no-store`，数据字段检查未发现城市、经纬度或完整 UA。项目部署工具因腾讯云本机回连公网 SSH 无可用密钥而未执行远端步骤，随后直接核对本机 checkout 并重启 `snh48` screen；首次按标准命令启动触发既有 QA 预热导致短时等待，最终恢复既有 `QA_WARMUP_ON_STARTUP=false` 覆盖后本机和公网 `/ob` 分别约 0.04 秒和 0.05 秒返回。阿里云尚未部署，等待用户验收腾讯云页面后再继续。

> 2026-08-08 20:15 计分礼物送礼用户 Excel 导出腾讯云阶段发布：功能提交 `f423a38` 已推送并由腾讯云 screen 加载。`/score-gifts` 的“送礼用户分布”新增导出入口，新接口沿用当前来源、礼物、用户和日期筛选，返回“送礼用户汇总”与“投分明细”两个工作表；明细按用户分组，保留送礼时间、房间/直播来源、礼物、数量、单个分值和对应分数。真实 `score_gifts.json` 共 2098 条记录的导出为 542585 bytes，ZIP 完整性检查无错误。公网页面为 200、未授权新接口为 401、服务器内鉴权新接口为 200。项目部署工具因腾讯云本机回连公网 SSH 无可用密钥而未执行远端步骤，随后直接核对本机 checkout 为目标提交并仅重启 `snh48` screen；阿里云尚未部署，等待用户验收腾讯云页面后再继续。

> 2026-08-08 18:07 房间计分 PK 腾讯云阶段发布：网站功能提交 `d369a16` 和响应性修复 `8f09eb9` 已推送并由腾讯云 screen 加载。公网 `/pk` 返回 200，未授权数据 API 返回 401，服务器内鉴权请求返回 200；采样数据为陈嘉仪新增 `3847.9`、累计 `14544.0`，曾雪婷新增 `5595.6`、累计 `19214.4`。首次按默认命令重启时，既有 QA 启动预热再次使普通页面超时，随后按本文既有处置临时覆盖 `QA_WARMUP_ON_STARTUP=false` 恢复，PK 文件直接读取耗时约 0.001 秒。阿里云尚未部署网页，也未同步 `room_record/pk_scores/`；等待用户验收腾讯云页面后再单独确认，现有阿里云同步脚本未改动。

> 2026-07-21 15:31 翻牌网站 HTML 移除专项复核：网站仓库功能提交 `35a4134` 已推送并部署，随后文档提交 `9b0bce4` 以 `--no-restart` 快进到两端。腾讯云网站 screen 重启为 `1407658.snh48`、PID `1407675`；阿里云 `snh48-aliyun` 重启为 PID `3257540`。两端 `/flip-cards` 均为 200，旧 `/api/flip-cards/html` 均为 404，未登录 `/api/flip-cards/status` 均为 401，页面源码不再包含 `downloadHtmlLink`、`/api/flip-cards/html` 或“下载版”。阿里云旧 `/home/snh48-fan-hub/flip_chat.html` 副本已删除；已部署的动态同步脚本和 `deploy.py` 不再引用 `flip_chat.html`，后续 cron 不会重新拉取该 HTML。腾讯云 fan-hub 的 `flip_chat.html` 仍保留为本地下载查看产物，不作为网站同步项。

> 2026-07-21 15:12 用户确认腾讯云后复核阿里云发布。另一条协作流程已先把阿里云快进到 `5ea0077` 并于 15:06:33 重启 `snh48-aliyun`，因此本轮没有重复拉取或重启。阿里云每分钟 cron 仍启用；15:07、15:08 两轮日志均按 `room_voice_replays payload done` → `manifest committed` → `obsolete payload cleaned` 顺序完成并更新状态。公网 `/radio`、`/flip-cards` 为 200，页面含最新电台/翻牌交互统计代码，未登录电台 API 为 401。跨云健康检查确认最新会话 `rv_20260720_212821_main_36376935_cff7b6` 的消息与腾讯云一致，兼容版、原始音质版共 2 个媒体对象均可通过阿里云鉴权 Range 播放。共享状态角色为 `tencent True True True` / `aliyun False True True`，腾讯云持久 outbox 无积压；阿里云没有 outbox 文件积压。

> 2026-07-21 15:15 共享运行状态第二阶段专项复核：部署前把四个当前状态以 `0600` 权限备份到阿里云 `website/data/runtime_backups/shared-state-rollout-20260721T070349Z/`，并补齐显式 `SHARED_STATE_*` / `ACTION_INBOX_ROOT` 配置。首页背景词、房间忽略、计分业务和记忆页的 revision 与状态 SHA-256 在两端逐项一致；腾讯云向阿里云手动幂等重放四项均成功，阿里云向腾讯云幂等回送既有待办也成功，两端 outbox 均为 0。可靠待处理箱现有 9 条腾讯云来源事件，文件均为 `0600`；模板按 `origin_node` / `origin_label` 区分今后的腾讯云与阿里云请求。阿里云未发现可迁移的旧投诉或邮箱记录，因此没有制造测试待办。公网 `/`、`/scroller-admin`、`/room`、`/sg`、`/memories`、`/ob` 均为 200，首页词 API 返回 22 条，未认证的房间、计分、记忆、观察页及首页词写接口均为 401。

> 2026-07-20 21:54 翻牌应用页发布后，阿里云从 `b8da683` 快进到 `7d5c3b1` 并重启 `snh48-aliyun`。同轮累计补齐 `344f3a1` 至 `92a896c` 的共享运行状态、上麦回放原子同步和文档提交；阿里云配置已变为 `aliyun False True True`。随后在阿里云手动运行 `bash deploy/sync-from-tencent.sh dynamic`，日志确认 `flip_data/web/flip_cards.json done`、`flip_chat.html done`、`flip_data/audio done`、`flip_data/video done` 和 `All sync completed`。腾讯云与阿里云的 `flip_data/web/flip_cards.json` mtime 均为 2026-07-20 21:38 CST，阿里云受保护数据 API 验证通过。后续纯文档提交以 `--no-restart` 快进，公开烟测继续通过。

> 2026-07-20 18:06 上麦回放原子同步提交 `402551a` 已完成 Shell 语法、通用部署命令顺序和现有共享状态排除回归测试并推送。腾讯云网站 checkout 已包含该提交，手动推送兜底入口已更新但未执行；阿里云仍停留在 `2264e89`，其每分钟主动拉取暂未加载新脚本。原因是 `402551a` 的祖先包含尚待用户确认的共享运行状态提交 `344f3a1`，不能为本任务越过分阶段发布规则把无关功能一并上线。当前最新上麦会话已由腾讯云健康检查确认在阿里云完整可播；录音服务和网站服务均未因本次同步脚本改动重启。

> 2026-07-20 17:59 腾讯云先行部署 `344f3a1`：首页背景词、房间忽略、计分业务和记忆页各建立 1 个基线 revision；既有投诉/邮箱请求导入 9 条，来源均记录为“腾讯云 cjy.plus”，事件权限为 `0600`。阿里云尚未部署新接收脚本，因此腾讯云 outbox 暂有状态 4 项、待处理箱 9 项，属于分阶段发布的预期积压。当前阿里云 cron 仍按旧提交拉取 `memories.json` 和整个计分目录；用户验收后部署阿里云时，才会切换为四个可写状态只走 revision/outbox，并从普通 rsync 排除 `memories.json`、`live_business_fulfillments.json` 和锁文件。

> 2026-07-20 用户确认腾讯云双音质、加载/跳转状态和整行消息跳转体验后，阿里云从 `32bc7f1` 快进到 `2264e89`。由于累计提交包含双版本 Python API，16:18:04 只重启 `snh48-aliyun` 以加载新模块；16:21 采样 PID `3021633`、enabled、active/running、`NRestarts=0`。`/radio` 公网页面包含新交互，未登录 sessions API 为 401；鉴权详情返回 315 条消息和 `compatible/original`，兼容版与原始音质版经公网 Nginx 的 Range 请求均为 206。上麦 schema v2 manifest 和两个 M4A 此前已由阿里云每分钟 `dynamic` 拉取 cron 自动同步，本轮没有手动扩大数据同步范围。

> 2026-07-20 12:03 用户确认腾讯云计分礼物页面后，阿里云从 `643ad46` 快进到 `4369db9`，同时补齐此前尚未部署的翻牌记录页代码和 dynamic 同步清单；12:03:46 重启 `snh48-aliyun`。既有阿里云 cron 自动检测到变化并拉取必要数据，12:06:05 记录 `flip_data/audio done`、`flip_data/video done`、`All sync completed` 和 `state updated`。腾讯云与阿里云 `flip_chat.html` SHA-256 同为 `aae4347c71111e44c0443faf6cfb35a97587f50c951b0dbfae6aff90a867ab9c`；音频清单摘要同为 `ccbde5d7a00598467e22357beea47e72852201bce1c8b5b56e3b22be6b67ea89`、共 185 个文件，视频清单摘要同为 `3129f251859e67224872c14d5d7e3a6a75bf0c744e2633b9947faa6020b1abe8`、共 4 个文件。

> 2026-07-19 用户确认腾讯云页面后，阿里云已快进到 `3a7b05b` 并加载把 `room_voice_replays/` 纳入 `dynamic` 组的新脚本。04:50 手动同步成功，04:51 cron 又自动检测到 dynamic 变化并记录 `room_voice_replays done`、`state updated`。腾讯云与阿里云 `manifest.json` SHA-256 同为 `7679687352fc2cc210d3ecbbb55dcaa53a466556098d7680954aa8ff8bda2f82`，当时 `session_count=0`；原始 FLV 未同步。

| 项 | 当前值 |
|----|--------|
| 自动任务所在服务器 | 阿里云香港 |
| cron | `* * * * * bash /home/snh48_web/deploy/sync-from-tencent-if-changed.sh >> /var/log/snh48/sync-from-tencent.log 2>&1` |
| 轻量检查脚本 | `/home/snh48_web/deploy/sync-from-tencent-if-changed.sh` |
| 实际拉取脚本 | `/home/snh48_web/deploy/sync-from-tencent.sh` |
| 状态文件 | `/tmp/snh48_sync_from_tencent.state.core`、`/tmp/snh48_sync_from_tencent.state.dynamic` |
| 锁文件 | `/tmp/snh48_sync_from_tencent_change.lock`、`/tmp/snh48_sync_from_tencent.lock` |
| 同步日志 | `/var/log/snh48/sync-from-tencent.log` |
| 源服务器 | 腾讯云 `root@124.222.72.203` |
| 目标服务器 | 阿里云本机 |

脚本逻辑：

1. 阿里云每分钟 SSH 到腾讯云，分别计算 `core` 和 `dynamic` 两组源数据指纹。
2. 两组指纹都没有变化时只写入 `no source changes, skipped`。
3. 某组指纹变化时调用 `sync-from-tencent.sh <group>`，在一次同步内复用同一条 SSH ControlMaster 连接并用 `rsync` 拉取对应分组。
4. 同步成功后更新 `/tmp/snh48_sync_from_tencent.state.core` 和 `/tmp/snh48_sync_from_tencent.state.dynamic`。

同步内容：

| 腾讯云源路径 | 阿里云目标路径 | 说明 |
|--------------|----------------|------|
| `/home/snh48-fan-hub/schedule_record/chenjiayi_events.csv` | 同路径 | 事件/行程主文件，网站优先读取 |
| `/home/snh48-fan-hub/schedule_record/schedule.csv` | 同路径 | 兼容副本 |
| `/home/snh48-fan-hub/social_record/timeline/chenjiayi_social_timeline.json` | 同路径 | 微博/抖音已过滤的轻量时间轴数据；不包含原始社交 CSV、Cookie 或采集器 |
| `/home/snh48-fan-hub/live_push_replays/陈嘉仪_161808449/` | 同路径 | 直播回放汇总 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/live_covers/` | 同路径 | 直播封面 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/gift_replies/` | 同路径 | 礼物回复派生小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/messages_shards/` | 同路径 | 房间消息分片小数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/audio_transcripts/` | 同路径 | 语音转录文本数据 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/room_voice_replays/` | 同路径 | 密码保护的上麦回放发布包；包含兼容版/原始音质版派生 M4A、元数据和同期消息，原始 FLV 不同步 |
| `/home/snh48-fan-hub/room_record/陈嘉仪_161808449/score_gifts/` | 同路径 | 计分礼物只读派生文件；排除 `live_business_fulfillments.json` 和 `.*.lock`，可写业务状态走版本化共享状态 |
| `/home/snh48-fan-hub/flip_data/web/` | 同路径 | 脱敏账号清单、schema v4 账号 JSON 和默认兼容副本；逐条包含回复成员身份，`accounts.json` 最后原子提交，不含手机号、Token 或完整 metadata |
| `/home/snh48-fan-hub/flip_data/audio/{account_id}/`、`/home/snh48-fan-hub/flip_data/video/{account_id}/` | 同路径 | 账号级翻牌音视频依赖；不含 `metadata/`、`transcripts/`、登录会话或任务日志 |

同步分组：

| 分组 | 内容 | 典型频率 |
|------|------|----------|
| `core` | 统一事件/行程 CSV、社交时间轴、直播回放汇总、直播封面 | 低频或人工更新 |
| `dynamic` | 礼物回复、房间消息分片、语音转录、成员房间上麦回放发布包、计分礼物只读派生文件、脱敏翻牌 `web/`、账号级翻牌音视频 | 后台导出、上麦会话结束或翻牌批处理更新时变化 |

不作为常规同步项：

- `schedule_record/images/`：图片通过网站 `/image-proxy/` 访问。
- 完整原始房间消息、普通语音原文件、上麦原始 FLV、Cookie、Token、`.env`、`config/`、日志和缓存。
- 首页背景词、房间忽略、计分业务和记忆页是非 Git 版本化共享状态；腾讯云和阿里云均已启用统一提交、历史和 outbox。不得用普通 rsync 或 Git 覆盖这四个当前文件；腾讯云 outbox 如果短时保留待补发文件，应按共享状态工具排查，不要手工覆盖阿里云。
- 阿里云不是 `snh48-fan-hub` 的 Git checkout，不在阿里云生成 fan-hub 数据。

## 旧推送方案状态

腾讯云旧脚本仍保留为手动兜底：

```text
/home/snh48_web/deploy/sync-to-aliyun.sh
/home/snh48_web/deploy/sync-to-aliyun-if-changed.sh
/home/snh48_web/deploy/sync-to-aliyun-loop.sh
```

生产环境不应启用这些任务：

- 腾讯云 `crontab -l` 不应有未注释的 `sync-to-aliyun*` 任务。
- `/var/log/snh48/sync-to-aliyun.log` 不应持续更新。
- `ps` 不应长期出现 `sync-to-aliyun-loop.sh`、推送方向的 `rsync` 或连接阿里云 `8.210.188.184` 的同步进程。

2026-07-03 排查结论：

- 腾讯云 `sync-to-aliyun.sh` cron 已注释。
- 腾讯云没有发现 `sync-to-aliyun` 常驻进程。
- 旧推送日志最后更新时间停在 `2026-07-03 02:45:04 +0800`。
- 阿里云 `sync-from-tencent.log` 持续出现成功记录，说明新方案已经接管自动同步。

## 排查注意

- `source changed groups=dynamic, pulling...` 每分钟出现不一定异常。礼物回复、计分礼物、房间消息分片、语音转录、上麦发布包或翻牌应用数据等运行数据更新时，动态组源数据指纹会变化。
- `source changed groups=core,dynamic, pulling...` 如果长期每分钟出现，需要确认 `core` 组是否真的持续变化；否则检查状态文件是否被删除或无法写入。
- 稳定单向文件如 `chenjiayi_events.csv`、`schedule.csv` 和社交时间轴 JSON 应可以用 `sha256sum` 严格比对；四个可写共享状态改为核对 `_state.revision` 和 outbox，不能用普通 rsync 修复。
- 动态目录只能按同步日志、mtime 和 1 到 2 分钟延迟判断，不要要求瞬时 hash 完全一致。
- 修改同步目录、同步方向或云服务器 IP 时，必须同步更新 `doc/codex/project_profile.md`、`doc/daily_website_check.md`、`doc/security/security_baseline.md` 和 `AGENTS.md`。
- 如果新增同步目标或更换阿里云 IP，需要提醒用户更新腾讯云登录风险白名单。
