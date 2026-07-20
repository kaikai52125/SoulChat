## ADDED Requirements

### Requirement: Agent 可通过 `skill_load` 工具按需加载 Skill

系统 SHALL 提供一个 `skill_load` 内置工具（注册在 `BUILTIN_REGISTRY`，`layer="core"`），Agent 调用时传入 Skill 名称或标识，返回该 Skill 的完整能力描述。仅当当前角色有 `is_resident=false` 的启用 Skill 时，该工具才被注册。

#### Scenario: 成功加载
- **WHEN** Agent 调用 `skill_load(name="stock_analysis")` 且当前角色有对应按需 Skill
- **THEN** 系统返回格式化的 Skill 能力描述，包含：Skill 名称、prompt 全文、建议的内置工具列表（tool_keys）、可用脚本清单（名称/描述/文件路径/参数说明）

#### Scenario: Skill 不存在
- **WHEN** Agent 调用 `skill_load(name="nonexistent")` 且名称不匹配任何按需 Skill
- **THEN** 系统返回提示"未找到技能：nonexistent。可用技能：stock_analysis, translate_polish"

#### Scenario: 无按需 Skill 时不暴露工具
- **WHEN** 角色没有任何 `is_resident=false` 的启用 Skill
- **THEN** `skill_load` 工具不在 Agent 的工具列表中

### Requirement: `skill_load` 返回结果包含脚本执行说明

`skill_load` 的返回内容 SHALL 明确告知 Agent 使用 `bash` 工具执行脚本，并说明每个脚本的参数格式和执行方式。

#### Scenario: 返回脚本清单
- **WHEN** 按需 Skill 的 `config.tools` 包含 2 个脚本声明
- **THEN** `skill_load` 返回结果中列出：脚本名称、描述、文件路径、参数说明，以及使用 `bash("python scripts/xxx.py --arg value")` 的示例
