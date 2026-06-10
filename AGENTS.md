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
- `.env` 不提交真实值。需要改服务器 `.env` 时，先更新 `.env.example`，再只在服务器上补齐必要项，且不要输出密码明文。
- 修改源 JS/CSS 后必须运行 `node script/obfuscate_js.cjs`，并提交 `website/static/js-dist/`、`website/static/css-dist/`。
- 修改 Nginx 配置时必须运行 `nginx -t`。部署验收按本次任务目标选择，不把专项检查固化成所有任务的通用标准。
- 网站运行依赖 `/home/snh48-fan-hub` 的行程、回放、直播封面和图片代理数据；修改 `/timeline`、回放、图片代理或相关环境变量前，先读本项目 profile 的数据工程段落和 `snh48-fan-hub/schedule_record/网站开发对接说明.md`。
- `snh48-fan-hub` 的腾讯云实例是全量代码和数据生成源；阿里云只接收网站需要的最小数据集。不要把阿里云当作数据生成环境，也不要从网站仓库覆盖 fan-hub 运行数据。
- 服务器上的运行数据文件不要删除或覆盖，除非用户明确要求并确认影响。

## Definition Of Done

每个任务要有自己的完成定义：

- 通用代码任务：相关代码已修改，必要测试/语法检查通过，变更说明清楚。
- 功能任务：目标页面/API/交互路径通过，关键回归点通过。
- 安全任务：本次列出的安全目标通过，并更新安全文档或维护说明。
- 部署任务：目标环境已同步到指定提交，服务已重启或重载，任务相关的线上烟测通过。

部署完成标准必须来自本次任务目标。不要把某次任务的专项检查写成所有部署的固定要求。
