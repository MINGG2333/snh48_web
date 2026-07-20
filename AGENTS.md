# Codex Project Instructions

本文件记录本仓库的长期协作规则。更详细的流程见 `doc/codex/`。

## Communication

- 默认使用中文沟通。
- 先读代码和相关文档，再判断方案；不要只凭记忆修改。
- 如果用户的新消息改变方向，以最新消息为准。
- 对多项修复、改进或部署动作，先一次性列出每项的预期效果、可能坏处、是否建议实施。
- 默认等待用户逐项确认。只有用户明确表示“全部推进”“按推荐实施”或同等意思时，才批量执行。

## Task Routing

先判断任务类型，再采用对应工作流：

- 安全审计或安全修复：`doc/codex/workflows/security_review.md`
- 功能 bug 修复或新增功能：`doc/codex/workflows/feature_or_bugfix.md`
- 数据生成工程或跨仓库数据依赖：`doc/codex/workflows/data_dependency.md`
- 通过 GitHub 同步服务器：`doc/codex/workflows/deploy_via_git.md`
- 任务分解、确认方式、验收标准定义：`doc/codex/workflows/task_intake.md`

本项目的域名、服务器、部署命令、运行时文件和验证命令见 `doc/codex/project_profile.md`。

## Project Rules

- 默认通过 GitHub 同步服务器：本地提交推送后，服务器执行 `git pull`。不要用 `rsync` 覆盖代码，除非用户明确要求临时直传。
- 涉及网站页面、API、运行行为或用户可见功能的多服务器更新，默认分阶段发布：先让腾讯云 `cjy.plus` 生效并完成机器烟测，再把验证入口和结果发给用户，等待用户明确确认“腾讯云验证通过/可以同步阿里云”后，才同步或部署阿里云。等待用户验收期间不要执行 `deploy all`、`deploy aliyun` 或腾讯云到阿里云的数据同步。
- `.env` 不提交真实值。新增或修改环境变量时，必须先更新 `.env.example`；在让配置生效前，必须明确提醒用户按 `.env.example` 检查并修改服务器 `.env`。部署时只在服务器上补齐必要项，且不要输出密码明文。
- 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs`，并提交 `website/static/js-dist/`、`website/static/css-dist/`。
- 修改 Nginx 配置时必须运行 `nginx -t`。部署验收按本次任务目标选择，不把专项检查固化成所有任务的通用标准。
- 阿里云 HTTPS 证书由 Certbot 管理，月度提醒机制见 `doc/ops/https_certificate_reminder.md`；处理阿里云、HTTPS、Nginx 或证书问题时先读该文档并运行 `script/check_https_certificate.py`，证书仍有效时不要手动替换。
- 网站运行依赖 `/home/snh48-fan-hub` 的行程、回放、成员房间上麦发布包、翻牌页产物、直播封面和图片代理数据；修改 `/timeline`、直播/上麦回放、翻牌页、图片代理或相关环境变量前，先读本项目 profile 的数据工程段落、`snh48-fan-hub/schedule_record/网站开发对接说明.md` 和对应数据契约。
- `snh48-fan-hub` 的腾讯云实例是全量代码和数据生成源；阿里云只接收网站需要的最小数据集。不要把阿里云当作数据生成环境，也不要从网站仓库覆盖 fan-hub 运行数据。
- 腾讯云到阿里云的网站必要运行数据自动同步方式，以 `doc/codex/project_profile.md` 的“数据生成工程依赖/数据同步脚本”为准；当前应由阿里云 cron 主动从腾讯云拉取，不要恢复腾讯云侧 15 秒常驻同步循环或自动推送任务。改同步方向、频率、路径或目标服务器前，必须同时更新 `doc/daily_website_check.md`、`doc/running_status.md` 和 `doc/security/security_baseline.md`，并验证新旧 cron、日志和进程状态。
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
