## 1. YAML Frontmatter 解析器修复

- [x] 1.1 删除 `_parse_frontmatter_yaml` 手写解析器，用 `yaml.safe_load` 替换 `_parse_frontmatter` 中的解析逻辑
- [x] 1.2 处理 `yaml.safe_load` 返回值的类型归一化：`tools` → `list[dict]`，`tool_keys` → `list[str]`，`triggers` → `list[str]`
- [x] 1.3 保留 `name` 必填校验和 `tool_keys`/`allowed-tools` 别名兼容逻辑
- [x] 1.4 用已有的 Skill zip 文件和内置模板做解析回归验证

## 2. SkillConfig Schema 补全

- [x] 2.1 `SkillConfig` Pydantic 模型新增 `is_resident: bool = Field(default=True)` 字段
- [x] 2.2 `SkillConfig` Pydantic 模型新增 `tools: list[dict] = Field(default_factory=list)` 字段
- [x] 2.3 `SkillUpdate` 的 `config` 字段保持 `dict | None`（足够灵活），但前端提交时按新 Schema 构造

## 3. Bash 执行工具

- [x] 3.1 新建 `api/app/core/agent/tools/builtin/bash_tool.py`，注册为 `bash` 内置工具（`layer="core"`，`default_enabled=true`）
- [x] 3.2 实现路径安全校验：`os.path.realpath` 解析 → 检查前缀是否在 Skill 目录内
- [x] 3.3 实现解释器自动识别：`.py`→`python`、`.sh`→`bash`、`.js`→`node`、`.R`→`Rscript`
- [x] 3.4 子进程资源控制：`asyncio.create_subprocess_exec`，timeout=30s，stdout 上限 64KB
- [x] 3.5 注册到 `tools/builtin/__init__.py`

## 4. skill_load 工具

- [x] 4.1 新建 `api/app/core/agent/tools/builtin/skill_load.py`，注册为 `skill_load` 内置工具（`layer="core"`）
- [x] 4.2 实现 `_run(name: str)` 逻辑：查当前角色的按需 Skill → 返回 prompt + tool_keys + 脚本清单 + bash 使用示例
- [x] 4.3 无匹配 Skill 时返回"未找到技能：X。可用技能：A, B, C"
- [x] 4.4 注册到 `tools/builtin/__init__.py`

## 5. chat_service 常驻/按需分流

- [x] 5.1 在工具构建阶段判断：常驻 Skill 走现有逻辑（prompt 注入 + tool_keys 过滤 + 脚本工具注册）；按需 Skill 跳过所有这些
- [x] 5.2 当存在按需 Skill 时，确保 `skill_load` 和 `bash` 工具在 Agent 工具列表中
- [x] 5.3 `_compose_system_prompt` 中只注入常驻 Skill 的 prompt
- [x] 5.4 `tool_keys` 白名单仅由常驻 Skill 贡献，按需 Skill 的 `tool_keys` 不作为过滤器

## 6. skill_executor 解释器扩展

- [x] 6.1 `_run_script` 支持显式指定解释器（通过参数传入），推导逻辑：后缀 → 默认解释器
- [x] 6.2 保留 `build_skill_tools` 函数不变（常驻 Skill 的脚本工具仍用现有逻辑）
- [x] 6.3 脚本工具描述中加入"可直接用 python/ bash 执行"的提示

## 7. 前端常驻/按需开关

- [x] 7.1 `SkillConfig` TypeScript 接口补全 `is_resident` 和 `tools` 字段
- [x] 7.2 角色 Skill 管理列表每个 Skill 添加 Switch 开关组件
- [x] 7.3 保存时将 `config.is_resident` 提交到后端

## 8. 集成验证

- [x] 8.1 准备一个带完整 `tools` 声明的 `.soulskill.zip` 测试文件
- [x] 8.2 验证导入后 `config.tools` 非空，脚本工具可被常驻模式注册
- [x] 8.3 验证按需模式下 `skill_load` 返回正确的 Skill 信息
- [x] 8.4 验证 bash 工具路径安全校验（合法路径通过、越狱路径拒绝）
- [x] 8.5 验证存量常驻 Skill 行为不变（向后兼容）
