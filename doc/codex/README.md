# Codex 工作流说明

本目录用于沉淀可复用的 Codex 协作方式，目标是让安全审计、功能修复、新增功能和服务器部署都能按稳定流程执行。

## 文件分层

| 文件 | 类型 | 适合放什么 |
|------|------|------------|
| `AGENTS.md` | 项目入口规则 | 简短、长期有效的协作规则；任务路由；必须遵守的仓库约定 |
| `doc/codex/project_profile.md` | 本项目配置 | 域名、服务器、部署命令、运行时文件、项目验证命令、常见风险 |
| `doc/codex/workflows/*.md` | 可跨项目复用 | 安全审计、功能修复、部署、任务确认等流程 |
| `doc/codex/templates/*.md` | 可模板化迁移 | 新项目要填写的 profile、部署清单、安全检查清单 |
| `doc/security/security_baseline.md` | 本项目事实记录 | 当前网站已实施的安全措施、线上验证命令、已知取舍 |

## Codex 识别边界

- `AGENTS.md` 是 Codex 的仓库级指导文件，放在项目根目录是正确位置。
- `doc/codex/` 下的文件是普通项目文档，不是 Codex 原生 Skill，也不会仅因文件名被自动当作 Skill 加载。
- 当前设计是让 `AGENTS.md` 指向这些 workflow/profile 文档，Codex 在执行对应任务时读取它们。
- 如果未来要做成真正可安装、可跨仓库自动触发的 Skill，应单独创建带 `SKILL.md` 的 Skill，并安装到 Codex 的 skills/plugin 机制中；不要把普通项目文档误认为 Skill。
- `doc/codex/templates/` 是迁移模板，用于复制到其他项目后填写，不是运行时配置。

## 使用方式

1. 先读 `AGENTS.md`，确认当前任务类型。
2. 读 `project_profile.md`，拿到本项目的具体命令和环境。
3. 按对应 `workflows/` 文件执行。
4. 如果要迁移到其他网站，先看 `PORTABILITY.md`，再复制 `templates/`。

## 维护原则

- `AGENTS.md` 保持短，避免把完整部署手册塞进去。
- 具体命令和服务器信息放进 `project_profile.md`。
- 流程性经验放进 `workflows/`，尽量写成跨项目可复用。
- 当一次任务暴露出新的协作偏好或容易遗漏的步骤，优先更新这里。
