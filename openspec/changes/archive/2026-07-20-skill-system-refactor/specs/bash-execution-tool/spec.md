## ADDED Requirements

### Requirement: 内置 bash 工具支持安全命令执行

系统 SHALL 提供一个 `bash` 内置工具（注册在 `BUILTIN_REGISTRY`，`layer="core"`，`default_enabled=true`），Agent 可调用它执行 Skill 脚本目录内的命令。cwd 锁定在 Skill 的 `storage_path` 目录。

#### Scenario: 执行 Python 脚本
- **WHEN** Agent 调用 `bash(command="python scripts/fetch_data.py --symbol 600519")` 且脚本路径在 Skill 目录内
- **THEN** 系统以 `storage_path` 为 cwd 启动子进程执行命令，捕获 stdout 并返回

#### Scenario: 执行 Shell 脚本
- **WHEN** Agent 调用 `bash(command="bash scripts/setup.sh")`
- **THEN** 系统按 `.sh` 后缀识别解释器为 bash 并执行

#### Scenario: 执行 Node.js 脚本
- **WHEN** Agent 调用 `bash(command="node scripts/process.js --input data.json")`
- **THEN** 系统成功执行 Node.js 脚本

### Requirement: bash 工具路径安全校验

bash 工具 SHALL 使用 `os.path.realpath` 解析命令中的所有文件路径，拒绝任何解析后不在 `storage_path` 目录内的访问。

#### Scenario: 拒绝越狱路径
- **WHEN** Agent 调用 `bash(command="python ../../../etc/malicious.py")`
- **THEN** 系统返回错误"安全限制：脚本路径不在技能目录内，已拒绝执行"

#### Scenario: 拒绝绝对路径
- **WHEN** Agent 调用 `bash(command="python /etc/passwd")`
- **THEN** 系统返回错误"安全限制：脚本路径不在技能目录内，已拒绝执行"

#### Scenario: 接受子目录内的合法路径
- **WHEN** Agent 调用 `bash(command="python scripts/subdir/deep_script.py")`
- **THEN** 系统正常执行该脚本（路径解析后在 storage_path 内）

### Requirement: 子进程资源限制

bash 工具的每次调用 SHALL 设置子进程超时 30 秒，stdout 上限 64KB。超时或超出上限时向 Agent 返回明确错误信息。

#### Scenario: 超时
- **WHEN** 脚本执行超过 30 秒
- **THEN** 系统终止子进程，返回"脚本执行超时（>30s）"

#### Scenario: 输出过大
- **WHEN** 脚本 stdout 超过 64KB
- **THEN** 系统截断输出并追加"...(输出已被截断)"

### Requirement: 解释器自动识别

bash 工具 SHALL 支持从命令中提取文件路径，根据文件后缀自动推荐解释器。如果 Agent 未显式指定解释器（如直接传 `scripts/xxx.py`），系统自动推导。

#### Scenario: 后缀映射
- **WHEN** 脚本后缀为 `.py` 且 Agent 未指定解释器
- **THEN** 系统默认使用 `python` 执行
- **WHEN** 脚本后缀为 `.sh`
- **THEN** 系统默认使用 `bash` 执行
- **WHEN** 脚本后缀为 `.js`
- **THEN** 系统默认使用 `node` 执行
- **WHEN** 脚本后缀为 `.R`
- **THEN** 系统默认使用 `Rscript` 执行
