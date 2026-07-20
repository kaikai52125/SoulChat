## ADDED Requirements

### Requirement: YAML Frontmatter 解析器支持标准 YAML 语法

Skill 的 SKILL.md frontmatter 解析 SHALL 使用 `yaml.safe_load` 替代手写行级解析器，支持嵌套对象列表、引号包裹的值、多行字符串等标准 YAML 语法。

#### Scenario: 解析对象列表
- **WHEN** SKILL.md frontmatter 包含 `tools: [{name: fetch_data, description: 获取数据, script: scripts/fetch.py}]`
- **THEN** `config.tools` 解析为 `[{"name": "fetch_data", "description": "获取数据", "script": "scripts/fetch.py"}]`

#### Scenario: 解析简单字符串列表（向后兼容）
- **WHEN** SKILL.md frontmatter 包含 `tool_keys: [knowledge_search, web_search]`
- **THEN** `meta["tool_keys"]` 解析为 `["knowledge_search", "web_search"]`

#### Scenario: 解析引号包裹的值
- **WHEN** SKILL.md frontmatter 包含 `description: "这是一个包含特殊字符: 的说明"`
- **THEN** 字段值正确保留冒号和引号内容

#### Scenario: 解析多行值
- **WHEN** SKILL.md frontmatter 使用 `|` 或 `>` 标记多行字符串
- **THEN** 多行字符串被正确保留，换行符按 YAML 规范处理

### Requirement: 空 frontmatter 容错

当 SKILL.md 的 frontmatter 不包含 `tools` 字段时，系统 SHALL 默认设为空数组 `[]`。

#### Scenario: 无 tools 字段
- **WHEN** SKILL.md frontmatter 只有 `name` 和 `description` 字段
- **THEN** `config.tools` 为 `[]`，Skill 正常工作（纯提示词 Skill）

### Requirement: 解析失败时明确报错

当 SKILL.md frontmatter 格式非法（YAML 语法错误、缺少必填字段 `name`）时，系统 SHALL 抛出明确的业务异常。

#### Scenario: YAML 语法错误
- **WHEN** SKILL.md frontmatter 包含非法 YAML（如缩进不一致）
- **THEN** 系统抛出异常，导入失败，错误信息包含"YAML 解析失败"和具体行号

#### Scenario: 缺少 name
- **WHEN** SKILL.md frontmatter 没有 `name` 字段
- **THEN** 系统抛出 `BizError`，错误信息"SKILL.md frontmatter 缺少必填字段 name"
