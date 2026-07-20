## ADDED Requirements

### Requirement: Skill 支持常驻与按需两种加载模式

系统 SHALL 支持每个 Skill 在角色上配置为"常驻"或"按需"模式，通过 `config.is_resident` 字段控制。默认值为 `true`（常驻），向后兼容存量 Skill。

#### Scenario: 默认常驻模式
- **WHEN** 用户导入或创建 Skill 且未显式设置 `is_resident`
- **THEN** 系统以常驻模式处理该 Skill，prompt 注入 system_prompt，tool_keys 参与过滤，脚本工具注册为 Agent 工具

#### Scenario: 切换为按需模式
- **WHEN** 用户在角色 Skill 管理页将某个 Skill 切换为按需模式（`is_resident=false`）
- **THEN** 该 Skill 的 prompt 不注入 system_prompt，脚本工具不注册，仅暴露 `skill_load` 工具供 Agent 调用

#### Scenario: 多 Skill 混合模式
- **WHEN** 角色同时有 2 个常驻 Skill 和 3 个按需 Skill 启用
- **THEN** 系统注入常驻 Skill 的 prompt 和工具，按需 Skill 仅通过 `skill_load` 可用，两种模式互不干扰

### Requirement: 按需 Skill 不参与 tool_keys 白名单过滤

按需模式下的 Skill 其 `tool_keys` SHALL 不作为内置工具的白名单过滤器。Agent 的工具列表保持完整（所有核心内置工具可用），`tool_keys` 仅作为元数据在 `skill_load` 返回时告知 Agent 该 Skill 建议使用的工具。

#### Scenario: 按需 Skill 不限制工具
- **WHEN** 按需 Skill 的 `tool_keys=["knowledge_search"]`
- **THEN** Agent 的工具列表仍包含 web_search、datetime 等所有核心工具，不受 Skill tool_keys 影响

### Requirement: 前端角色 Skill 管理支持模式切换

前端角色编辑页的 Skill 列表 SHALL 为每个 Skill 提供常驻/按需开关组件。

#### Scenario: 开关可见
- **WHEN** 用户打开角色编辑页的技能管理 Tab
- **THEN** 每个已挂载 Skill 右侧显示"常驻/按需"开关，当前模式清晰可辨

#### Scenario: 切换生效
- **WHEN** 用户点击某 Skill 的开关从常驻切换为按需并保存
- **THEN** 下次对话时该 Skill 以按需模式运行
