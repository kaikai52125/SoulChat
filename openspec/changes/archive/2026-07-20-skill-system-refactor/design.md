## Context

SoulChat 的 Skill 系统当前实现存在以下问题：

1. **YAML 解析器缺陷**：`_parse_frontmatter_yaml` 是手写行级解析器，只支持简单字符串列表（`- value`），无法解析对象列表（`- name: xxx`）。导入带脚本声明的 SKILL.md 后 `config.tools` 始终为空数组。
2. **全量注入模型**：所有 `enabled=True` 的 Skill 无条件注入 prompt + 工具白名单过滤 + 脚本工具注册，无法按需使用，造成 token 浪费和 LLM 认知负担。
3. **`tool_keys` 语义混乱**：多 Skill 并存时取并集做白名单，效果等价于无限制。
4. **Script 执行局限**：`skill_executor.py` 硬编码 `python` 解释器，无法执行 `.sh`/`.js`/`.R` 等脚本。
5. **Schema 不完整**：`SkillConfig` Pydantic 模型缺少 `tools` 字段。

现有基础设施可复用：
- `agent_tool.py` — Agent-as-Tool 模式，按需 Skill 的加载和执行直接复用其 Agent 包装模式
- `skill_executor.py` — 脚本工具注册，bash 工具可复用其 subprocess + 安全性设计
- `skill_service.py` — zip 导入/解压/市场/fork 流程不变，只替换解析器

## Goals / Non-Goals

**Goals:**
1. 修复 YAML 解析器：用 `yaml.safe_load` 替代手写解析器，支持完整 YAML 语法和嵌套对象列表
2. 常驻/按需双模式：角色 Skill 管理页面提供开关，默认常驻（向后兼容）
3. `skill_load` 工具：Agent 按需调用，返回 Skill 的 prompt + 可用脚本清单 + 执行参数说明
4. bash 执行工具：新增内置 `bash` 工具，安全沙箱限定 Skill 目录，按脚本后缀自动选择解释器
5. `tool_keys` 语义修正：按需模式下转为声明式元数据，不作为白名单过滤器
6. Schema 补全：`SkillConfig` 加入 `tools` 字段，前后端类型一致

**Non-Goals:**
- 不做 Skill 间的依赖编排（Skill A 调 Skill B）
- 不做按需 Skill 加载后的工具动态绑定（工具列表不变，Agent 通过 `skill_load` + `bash` 组合使用）
- 不做 Skill 执行结果的持久化缓存
- 不修改 Skill 市场/fork 逻辑

## Decisions

### Decision 1: 常驻/按需标记存在 `skills.config` JSONB 中

**选择**: 在 Skill 的 `config` JSONB 中增加 `is_resident` 字段，默认 `true`。

**理由**:
- 不需要 ALTER TABLE 加列，零迁移成本
- `config` 本身就是字典，加 key 自然
- 向后兼容：存量 Skill 的 `config.is_resident` 缺失 → 默认为 `true` → 常驻模式

**替代方案**: 在 `skills` 表加 `load_mode` 列。否决——加列需要 migration，且字段语义跟 `config` 里的运行时配置耦合度高；加关联表（`persona_skill_configs`）过于重量级。

### Decision 2: 按需 Skill 不动态绑定工具，通过 `skill_load` + `bash` 组合实现

**选择**: 按需 Skill 被调用时，Agent 先用 `skill_load` 获取 prompt 和脚本清单，再用 `bash` 工具逐个执行脚本。对话期间 Agent 的工具列表不变（不动态增删工具）。

**理由**:
- 动态工具绑定在 LangChain 的 `bind_tools` 模式下需要重新创建模型实例，复杂度高且不可靠
- `skill_load` 返回文本描述（类 ReAct Observation），Agent 基于此信息自主决定用 `bash` 执行哪些脚本
- 跟 Two-Speed Router 之前的讨论一致：Agent 的决策能力 + 工具并行执行 > 外部编排

**替代方案**: 动态加载 Skill 工具（`skill_load` 后即时 `bind_tools` 追加新工具）。否决——LangChain `bind_tools` 不支持增量追加，只能整体替换；且会导致前后轮次的工具契约不一致，LLM 行为不可预测。

### Decision 3: bash 工具的安全模型

**选择**: `bash` 工具接受命令字符串，校验路径必须在 skill 目录内，cwd 锁定在 Skill 的 `storage_path`，按文件后缀自动匹配解释器。

**安全规则**:
1. 命令中提取的所有文件路径必须相对路径或以 `storage_path` 开头
2. 拒绝绝对路径指向 skill 目录外的任何文件（`/etc/passwd`、`C:\...`）
3. 拒绝 `../` 路径逃逸
4. cwd 固定为 `storage_path`
5. 子进程超时 30 秒，stdout 上限 64KB

**后缀 → 解释器映射**:
```
.py  → python
.sh  → bash
.js  → node
.R   → Rscript
.rb  → ruby
无后缀且无 shebang → bash -c
可执行文件 → 直接运行
```

**替代方案**: 完全信任 Agent 不注入恶意命令。否决——Agent 可能被 prompt injection 攻击。

### Decision 4: YAML 解析器替换为 `yaml.safe_load`

**选择**: 删除 `_parse_frontmatter_yaml` 手写解析器，直接用 Python 标准 YAML 库的 `yaml.safe_load`。

**理由**:
- `yaml.safe_load` 不支持任意 Python 对象反序列化，安全性好
- 支持完整 YAML 语法：嵌套对象、引号、多行字符串、注释
- 兼容 Claude Code / Cursor / Continue 等主流 SKILL.md 格式（它们都用标准 YAML frontmatter）
- pyyaml 已是项目中安装的依赖

**兼容性处理**: `yaml.safe_load` 返回的 `tools` 可能是 `list[dict]`、`list[str]` 或 `None`，需做类型归一化。

### Decision 5: `tool_keys` 语义修正

**选择**: 常驻模式下保留现有行为（白名单过滤），但过滤逻辑改为：仅当 Skill 显式声明 `tool_keys` 时生效，多 Skill 取并集。

按需模式下，`tool_keys` 不作为过滤器（因为 Agent 的工具列表不变），而是作为元数据在 `skill_load` 返回结果中展示："此技能通常需要以下内置工具：knowledge_search, web_search"。

**理由**: 按需模式下 Agent 的工具列表始终包含所有核心内置工具，`tool_keys` 过滤没有意义。改为声明式至少让 Agent 知道建议用什么工具。

## Risks / Trade-offs

**[R1] bash 工具的路径校验可能被绕过** → Agent 可能用奇怪的引用方式或编码绕过正则校验。
→ **缓解**: 不依赖正则校验，直接用 `os.path.realpath` 解析最终路径，再检查前缀是否在 `storage_path` 内。这是文件系统级别的校验，不可绕过。

**[R2] 每次调按需 Skill 都需要两轮对话（skill_load → bash 执行）** → 比常驻模式多一次 LLM 往返。
→ **缓解**: 可接受。按需 Skill 本身就不是高频调用场景：翻译、股票分析等通常每轮对话只触发一次。如果对话中反复使用同一个 Skill，Agent 可以一次 `skill_load` 后缓存信息（在上下文中），后续直接 `bash`。

**[R3] YAML 解析器切换可能影响现有 SKILL.md 格式** → 手写解析器的行为和 `yaml.safe_load` 对相同输入可能有不同解读。
→ **缓解**: 主要影响的是 `tool_keys`（简单字符串列表）和 `tools`（对象列表）。`yaml.safe_load` 对 `- value` 的解析结果与手写解析器一致。在切换前用现有内置 Skill 模板做回归测试。

**[R4] 并存的常驻和按需 Skill 可能产生 prompt 冲突** → 常驻 Skill A 的 prompt 说"你是 X"，按需加载的 Skill B 的 prompt 说"你是 Y"。
→ **缓解**: 按需 Skill 的 prompt 通过 `skill_load` 返回给 Agent 作为参考信息，不直接注入 system prompt。Agent 理解"我临时获得了 Y 能力，但我的底色仍是 X"。

## Open Questions

1. `skill_load` 返回的 prompt 是否需要持久的上下文记忆？即加载后，后续多轮对话是否还需要再次 `skill_load`？暂定每轮对话最多加载一次，Agent 自行判断是否需要重新加载。
2. bash 工具是否应该记录执行历史供 Agent 引用？暂定不记录，每次执行独立。
3. 是否需要支持"一键全部加载"（类似 `skill_load_all`）？暂定不做，先验证单 Skill 按需加载的体验。
