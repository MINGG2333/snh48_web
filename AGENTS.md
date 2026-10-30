# Codex Project Instructions

本文件记录本仓库的长期协作规则。更详细的流程见 `doc/codex/`。

<!-- cjy-project-maintenance:start -->
## 安全桥普通维护能力

- 本节适用于以 `codex-feishu` 运行的安全桥普通维护 Agent。首次接手、恢复旧 thread 或准备交给 root 前，先运行 `id -un`、`command -v cjy-project`、`cjy-project --help` 和 `cjy-project doctor`，以当前节点的实际结果为准。
- 先读数据工程的 `doc/codex/project_maintainer_permissions.md`；在网站工程中读 `../snh48-fan-hub/doc/codex/project_maintainer_permissions.md`。不要沿用旧 thread 的只读判断，也不要仅因文件属于 root 就判定无法操作。
- 服务维护用 `cjy-project service <status|start|stop|restart> UNIT`、`cjy-project logs UNIT`；只操作本节点已部署且与任务有关的白名单服务。通知等级用 `cjy-project notification-level <show|info|warning|error|none|default>`；只读任务不为验证权限执行重启或设置变更。
- 源码修改、提交用普通 Git；推送用 `cjy-project git push <fan-hub|web>`，随后先 `cjy-project peer status <fan-hub|web>`，确认无覆盖风险后 `cjy-project peer pull <fan-hub|web>`。跨节点入口是受限普通账号同步，不提供任意 SSH shell。
- 文件写入被拒绝时先核对节点和授权目录；对已授权目录可运行 `cjy-project permissions` 修复后重试。行程产出仅在阿里云权威端修改。`doctor` 成功不等于每个路径、GitHub 或对端操作都成功，仍需验证实际目标。
- 现有授权不包含首次安装、维护策略/服务定义变更、系统软件、账号、网络、防火墙或 root 凭据。业务批准和严格凭据更新流程仍适用；已有工具也不替代用户对具体任务的授权。
- 写“待 root”交接前，先检查上述入口；确实越界或受阻时写清目标、尝试的命令、脱敏错误和缺少的权限。不要只因普通账号身份把日常维护交给 root。
<!-- cjy-project-maintenance:end -->

## Communication

- 默认使用中文沟通。
- 先读代码和相关文档，再判断方案；不要只凭记忆修改。
- 如果用户的新消息改变方向，以最新消息为准。
- 对多项修复、改进或部署动作，先一次性列出每项的预期效果、可能坏处、是否建议实施。
- 默认等待用户逐项确认。只有用户明确表示“全部推进”“按推荐实施”或同等意思时，才批量执行。

## Task Routing

先判断任务类型，再采用对应工作流：

- 安全审计或安全修复：`doc/codex/workflows/security_review.md`
- 新增或修改带密码页面、管理后台鉴权、登录 Cookie/Token 会话：`doc/security/password_page_best_practices.md`
- 功能 bug 修复或新增功能：`doc/codex/workflows/feature_or_bugfix.md`
- 数据生成工程或跨仓库数据依赖：`doc/codex/workflows/data_dependency.md`
- 安全桥普通维护账号的权限、服务维护、GitHub 与跨节点同步：`../snh48-fan-hub/doc/codex/project_maintainer_permissions.md`；优先检查和使用 `cjy-project`。
- 通过 GitHub 同步服务器：`doc/codex/workflows/deploy_via_git.md`
- 任务分解、确认方式、验收标准定义：`doc/codex/workflows/task_intake.md`

本项目的域名、服务器、部署命令、运行时文件和验证命令见 `doc/codex/project_profile.md`。

## Project Rules

- 默认通过 GitHub 同步服务器：本地提交推送后，服务器执行 `git pull`。不要用 `rsync` 覆盖代码，除非用户明确要求临时直传。
- 涉及网站页面、API、运行行为或用户可见功能的多服务器更新：腾讯云 `cjy.plus` 部署并机器烟测后**直接同步部署阿里云**，不用再等用户确认（2026-10-10 用户改定）。例外：涉及账号/密钥/隐私数据/对外数据契约变更的敏感改动，仍走"腾讯云先验→用户确认→阿里云"的分阶段流程。
- `.env` 不提交真实值。新增或修改环境变量时，必须先更新 `.env.example`；在让配置生效前，必须明确提醒用户按 `.env.example` 检查并修改服务器 `.env`。部署时只在服务器上补齐必要项，且不要输出密码明文。
- 密码保护页面和后台不得把密码写入 `localStorage`/`sessionStorage`，不得使用 `autocomplete="current-password"`；新页面默认使用路径限定的 HttpOnly Cookie 登录会话，详见 `doc/security/password_page_best_practices.md`。
- 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs`，并提交 `website/static/js-dist/`、`website/static/css-dist/`。
- 修改 Nginx 配置时必须运行 `nginx -t`。部署验收按本次任务目标选择，不把专项检查固化成所有任务的通用标准。
- 阿里云 HTTPS 证书由 Certbot 管理，月度提醒机制见 `doc/ops/https_certificate_reminder.md`；处理阿里云、HTTPS、Nginx 或证书问题时先读该文档并运行 `script/check_https_certificate.py`，证书仍有效时不要手动替换。
- 网站运行依赖 `/home/snh48-fan-hub` 的行程、回放、成员房间上麦发布包、翻牌页产物、直播封面和图片代理数据；修改 `/timeline`、直播/上麦回放、翻牌页、图片代理或相关环境变量前，先读本项目 profile 的数据工程段落、`snh48-fan-hub/schedule_record/网站开发对接说明.md` 和对应数据契约。
- `snh48-fan-hub` 的腾讯云实例是全量代码、采集与归档源；2026-10-16 起"数据加工/AI 生成"迁到阿里云，阿里云同时是派生数据的产地。不要从网站仓库覆盖 fan-hub 运行数据。
- 腾讯云与阿里云之间的网站必要运行数据自动同步方式，以 `doc/codex/project_profile.md` 的“数据生成工程依赖/数据同步脚本”为准；当前为双向拉取：阿里云 cron 主动从腾讯云拉取采集与网站数据（`core`/`dynamic`/`hub`），腾讯云 cron 主动从阿里云拉取派生数据（`derived`/`notify`），不要恢复腾讯云侧 15 秒常驻同步循环或自动推送任务。改同步方向、频率、路径或目标服务器前，必须同时更新 `doc/daily_website_check.md`、`doc/running_status.md` 和 `doc/security/security_baseline.md`，并验证新旧 cron、日志和进程状态。
- 翻牌多账号同步只允许复制脱敏 `flip_data/web/` 和账号级 `audio/`、`video/`；`web/accounts.json` 必须最后原子提交。不得把 `metadata/`、`transcripts/`、手机号、Token、网页登录会话或刷新任务日志加入阿里云同步。
- 首页背景词、房间消息忽略状态、计分礼物业务核实状态和记忆页数据都是非 Git 运行状态。两个域名都可接受操作，但由腾讯云统一串行提交版本，随后复制到阿里云；不得恢复 Git 提交或两个节点互相覆盖整份文件。实现、配置、恢复和巡检见 `doc/shared_runtime_state.md`。
- 投诉和 QA 邮箱请求进入 `website/data/action_inbox/events/` 的不可变事件待处理箱，并记录 `origin_node` / `origin_label`；观察页必须明确展示请求来自腾讯云还是阿里云。旧 JSONL/Markdown 仅作兼容视图，不是跨服务器权威数据源。
- `interaction_logs/`、`ip_clients.json`、`read_notifications.json`、`ip_daily_quota.json`、`balance_log.csv` 等日志、观测、已读和限额状态保持服务器本地，不纳入业务状态复制；不能用双向整目录同步合并这些文件。
- 停用阿里云、替换服务器或新增运行数据同步目标时，先读 `doc/codex/project_profile.md` 的云安全与登录白名单记录，并提醒用户删除腾讯云主机安全旧白名单 IP 或新增新服务器 IP。
- 服务器上的运行数据文件不要删除或覆盖，除非用户明确要求并确认影响。

## Definition Of Done

每个任务要有自己的完成定义：

- 通用代码任务：相关代码已修改，必要测试/语法检查通过，变更说明清楚。
- 功能任务：目标页面/API/交互路径通过，关键回归点通过。
- 安全任务：本次列出的安全目标通过，并更新安全文档或维护说明。
- 部署任务：目标环境已同步到指定提交，服务已重启或重载，任务相关的线上烟测通过。

部署完成标准必须来自本次任务目标。不要把某次任务的专项检查写成所有部署的固定要求。

## 公演数据同步补充

用户已授权将陈嘉仪参演公演的公开互动文本保存到阿里云。`performance_record/陈嘉仪_161808449/` 属于明确白名单，仅同步JSON/JSONL/CSV/LRC；不复制公演视频、采集运行状态、验收诊断、配置和凭据，也不自动增加公开网页入口。
