## Why

当前所有启用的工具 schema（内置 6 个 + MCP Server 工具 N 个 + Skill 工具 M 个）全量注入 system prompt。工具 schema 描述平均 300-600 token/个，当用户挂载 5 个 MCP Server（平均每个 Server 5 个工具）时，仅工具描述就可能吃掉 ~15000 token 的 prompt 空间。更严重的是，工具数量超过 20-30 个后，LLM 的选择准确率显著下降（"工具瘫痪"效应 —— MCPToolBench++ 和 BFCL v3 数据）。

参考 Anthropic 2025.12 的 "Tool Search Tool" 设计：为 Agent 提供一个元工具，动态返回 3-5 个最相关的工具，只把这些候选的 schema 注入系统 prompt。

## What Changes

- 新增内置工具 `tool_search` —— Agent 在需要时调用，输入自然语言意图描述，返回 Top-K 相关工具的描述和参数
- 工具注册表 (`registry.py`) 新增 `search_tools(query, user_id)` 方法：基于工具 key + name + description 做 embedding 语义匹配
- `build_enabled_tools()` 新增"延迟加载"模式：非核心工具（MCP/Skill）默认不在 schema 中，由 `tool_search` 按需返回
- `orchestrator.py` 支持在第一轮 LLM 调用前，将核心工具（knowledge/memory/web/datetime）直接注入，其余走 tool_search 按需发现
- 为 MCP 工具 schema 预计算 embedding（tools_cache 已存工具列表，扩展加 embedding），tool_search 不走 MCP Server 重连

## Capabilities

### New Capabilities

- `tool-search`: 语义工具检索，Agent 按需动态发现工具，避免全量 schema 注入
- `lazy-tool-loading`: MCP/Skill 工具延迟加载，核心工具始终直接可用

### Modified Capabilities

- `tool-registry`: `build_enabled_tools()` 支持分层注册（核心层直接注入 + 扩展层按需发现）

## Impact

- **工具层** (`tools/registry.py`, `tools/base.py`): 新增 `search_tools()` + `build_tool_search_tool()` + 分层返回逻辑
- **内置工具** (`tools/builtin/`): 新增 `tool_search.py`
- **MCP 加载器** (`tools/mcp/loader.py`): 工具缓存扩展 embedding 字段，支持快速语义匹配
- **编排器** (`orchestrator.py`): 无需改动（tool_search 就是普通工具，Agent 自行决定何时调用）
- **前端** (`PersonaEditModal`): 工具配置页可选展示"核心/扩展"分层（非必须，可后续加）
