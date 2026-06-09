# Codex Project Instructions

复制到新项目根目录并命名为 `AGENTS.md` 后填写。

## Communication

- 默认沟通语言：TODO。
- 先读代码和相关文档，再判断方案；不要只凭记忆修改。
- 如果用户的新消息改变方向，以最新消息为准。
- 对多项修复、改进或部署动作，先一次性列出每项的预期效果、可能坏处、是否建议实施。
- 默认等待用户逐项确认。只有用户明确表示“全部推进”“按推荐实施”或同等意思时，才批量执行。

## Task Routing

先判断任务类型，再采用对应工作流：

- 安全审计或安全修复：`doc/codex/workflows/security_review.md`
- 功能 bug 修复或新增功能：`doc/codex/workflows/feature_or_bugfix.md`
- 部署同步：`doc/codex/workflows/deploy_via_git.md`
- 任务分解、确认方式、验收标准定义：`doc/codex/workflows/task_intake.md`

项目特有信息见 `doc/codex/project_profile.md`。

## Project Rules

- 默认部署方式：TODO。
- 真实 `.env` / secrets 不提交。需要改服务器配置时，先更新模板文件：TODO。
- 前端构建命令：TODO。
- 后端测试或语法检查命令：TODO。
- Nginx/代理配置变更验证命令：TODO。
- 服务器运行时文件不要删除或覆盖，除非用户明确要求并确认影响。

## Definition Of Done

每个任务要有自己的完成定义：

- 通用代码任务：相关代码已修改，必要测试/语法检查通过，变更说明清楚。
- 功能任务：目标页面/API/交互路径通过，关键回归点通过。
- 安全任务：本次列出的安全目标通过，并更新安全文档或维护说明。
- 部署任务：目标环境已同步到指定提交，服务已重启或重载，任务相关的线上烟测通过。

不要把某一次安全任务的检查项固定成所有部署任务的通用完成标准。
