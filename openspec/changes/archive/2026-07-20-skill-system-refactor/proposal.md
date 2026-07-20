## Why

当前 Skill 系统的 YAML 解析器无法处理对象列表导致脚本工具声明的 Skill 导入后 `config.tools` 为空；所有 Skill 无条件全量注入 prompt 和工具造成 token 浪费和 LLM 认知负担；`tool_keys` 白名单在多 Skill 并存时语义混乱（并集=无限制）；Script 执行硬编码 `python` 无法运行其他语言的脚本。需要在修复解析器的同时，重构 Skill 的加载模型和执行能力。

## What Changes

- **修复 YAML 解析器**：将手写行级解析器 `_parse_frontmatter_yaml` 替换为 `yaml.safe_load`，支持嵌套对象列表（`tools` 数组）及完整 YAML 语法
- **常驻/按需双模式**：角色的每个 Skill 可通过开关切换模式。常驻模式行为不变（prompt 注入 + tool_keys 过滤 + 脚本工具注册）。按需模式不注入 prompt、不注册脚本工具，只暴露一个 `skill_load` 元工具
- **`skill_load` 工具**：Agent 按需调用，返回 Skill 的 prompt、可用脚本列表及参数说明，加载后 Agent 可自主使用 bash 工具依次执行脚本
- **bash 工具**：新增内置 Bash 执行工具，cwd 锁定在 Skill 的 `storage_path` 目录内，按脚本后缀自动选择解释器（Python/Shell/Node/Rscript 等），**安全沙箱**：拒绝越狱路径访问（如绝对路径、`../` 逃逸）
- **`tool_keys` 语义修正**：常驻模式下保留白名单行为（但改为声明式文档），按需模式下仅作为元数据返回给 Agent 参考
- **SkillConfig Schema 补全**：在 Pydantic 模型中正式加入 `tools` 字段，前后端统一

## Capabilities

### New Capabilities
- `skill-resident-on-demand`: 常驻/按需双模式，角色卡片上的开关控制，向后兼容（默认常驻）
- `skill-load-tool`: `skill_load` 工具，Agent 按需加载 Skill 的 prompt 和脚本清单
- `bash-execution-tool`: 内置 Bash 执行工具，安全沙箱限定 Skill 目录，按后缀自动选择解释器
- `yaml-frontmatter-parser`: 用 `yaml.safe_load` 替代手写解析器，支持完整 SKILL.md frontmatter 格式

### Modified Capabilities
<!-- No existing skill-related specs to modify -->

## Impact

- **Affected code**:
  - `api/app/services/skill_service.py` — YAML 解析器替换
  - `api/app/services/chat_service.py` — 按需 Skill 分支逻辑 + `skill_load` 注册
  - `api/app/core/agent/tools/skill_executor.py` — 按后缀识别解释器
  - `api/app/core/agent/tools/builtin/bash_tool.py` — 新增
  - `api/app/core/agent/tools/builtin/skill_load.py` — 新增
  - `api/app/schemas/skill_schema.py` — SkillConfig 加入 `tools` 字段
  - `web/` — 角色 Skill 管理页加常驻/按需开关
- **Breaking changes**: 无。存量 Skill 默认 `is_resident=True`，行为完全不变
- **Dependencies**: `pyyaml`（已安装）
