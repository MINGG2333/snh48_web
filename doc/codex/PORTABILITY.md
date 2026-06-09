# 跨项目复用说明

这些文件的目标不是只服务当前网站，也要方便迁移到其他网站项目。

## Codex 结构判断

当前结构符合 Codex 仓库指导的核心要求：根目录 `AGENTS.md` 作为入口规则，项目内文档作为可按需读取的补充资料。

需要注意：`doc/codex/workflows/` 和 `doc/codex/templates/` 是可复用文档，不是 Codex 原生 Skill。迁移到其他项目时可以复制它们；如果希望变成真正跨项目自动触发的 Skill，应把通用流程提炼为独立 `SKILL.md` 并通过 Codex skills/plugin 机制安装。

## 可直接跨项目复用

| 文件 | 复用方式 | 原因 |
|------|----------|------|
| `workflows/task_intake.md` | 直接复制 | 任务分类、利弊说明、确认方式、验收标准定义是通用协作流程 |
| `workflows/security_review.md` | 直接复制后少量调整检查项 | Web 安全审计的检查维度通用 |
| `workflows/feature_or_bugfix.md` | 直接复制 | 功能修复/新增功能的工程流程通用 |
| `workflows/deploy_via_git.md` | 直接复制，并改 profile 引用 | GitHub 同步、远端拉取、重启、烟测的结构通用 |

## 可模板化迁移

| 文件 | 迁移时要改什么 |
|------|----------------|
| `templates/project_profile.template.md` | 项目名、技术栈、域名、服务器、服务管理方式、部署命令、验证命令、运行时文件 |
| `templates/security_review.template.md` | 站点特有入口、鉴权方式、第三方资源、业务敏感端点、安全目标 |
| `templates/deployment_plan.template.md` | 目标环境、提交范围、回滚方式、任务特定验收项 |
| `templates/AGENTS.template.md` | 默认语言、部署方式、构建命令、测试命令、项目规则 |
| `AGENTS.md` | 项目名、默认部署方式、构建命令、团队偏好、任务路由 |

## 本项目特有，不建议直接复制

| 文件 | 原因 |
|------|------|
| `doc/codex/project_profile.md` | 包含当前项目的域名、IP、服务名、Nginx 路径 |
| `doc/security/security_baseline.md` | 记录的是当前网站已经实施的安全措施和取舍 |
| `deploy/TODO.md` | 是本项目的部署历史和运维手册 |
| `.env.example` | 包含本项目实际环境变量集合 |

## 迁移到另一个网站的步骤

1. 复制 `doc/codex/workflows/`、`doc/codex/templates/`。
2. 用 `templates/AGENTS.template.md` 填出新项目根目录的 `AGENTS.md`。
3. 用 `templates/project_profile.template.md` 填出新项目的 `doc/codex/project_profile.md`。
4. 用 `templates/security_review.template.md` 为新网站建立第一版安全检查清单。
5. 第一次安全审计后，新增该项目自己的 `doc/security/security_baseline.md`。
