## 1. 工具注册表扩展

- [ ] 1.1 `tools/registry.py`：新增 `_TOOL_EMBEDDING_CACHE: dict[str, list[float]]` 全局缓存
- [ ] 1.2 `tools/registry.py`：新增 `async def search_tools(intent: str, top_k: int = 5, session=None) -> list[dict]` 函数——计算 intent embedding，与缓存中所有工具做余弦相似度，返回 Top-K
- [ ] 1.3 `tools/registry.py`：`build_enabled_tools()` 新增 `layered: bool = True` 参数——True 时只返回核心工具 schema（不加载 MCP/Skill schema），False 时行为同旧版（全量加载）
- [ ] 1.4 `tools/registry.py`：新增 `_compute_and_cache_embedding(key, name, desc)` 辅助函数
- [ ] 1.5 `tools/registry.py`：工具注册时自动预计算核心工具 embedding（`register_tool` 或首次 `build_enabled_tools` 时）
- [ ] 1.6 `tools/base.py`：`ToolSpec` 新增 `layer: Literal["core", "extended"] = "core"` 字段，默认 core

## 2. tool_search 内置工具

- [ ] 2.1 `tools/builtin/tool_search.py`：实现 `tool_search` 工具（输入 intent + top_k，调用 `search_tools()` 返回格式化工具列表）
- [ ] 2.2 `tools/builtin/__init__.py`：注册 `tool_search` 到 `BUILTIN_REGISTRY`（key="tool_search", default_enabled=True, layer="core"）
- [ ] 2.3 tool_search 输出格式化：`name —— description\n  参数: param1(type, 必填/可选), param2(...)`

## 3. MCP 工具 embedding

- [ ] 3.1 `tools/mcp/loader.py`：`build_mcp_tools()` 加载时，为每个工具计算 embedding 并写入 `_TOOL_EMBEDDING_CACHE`
- [ ] 3.2 `tools/mcp/loader.py`：tools_cache fingerprint 刷新时，同步刷新对应工具 embedding
- [ ] 3.3 Skill 工具（`skill_executor.py`）同理，`build_skill_tools()` 时计算 embedding

## 4. chat_service 集成

- [ ] 4.1 `services/chat_service.py`：`_generate_events()` 中调用 `build_enabled_tools(layered=True)` 替代当前调用（核心工具直接注入，扩展工具按需发现）
- [ ] 4.2 system prompt 追加 tool_search 使用提示（仅当存在扩展工具时）："如果内置工具无法满足需求，请先使用 tool_search 查找扩展工具"
- [ ] 4.3 `services/group_chat_service.py`：群聊暂不启用 tool_search（群聊目前无工具），不改

## 5. 测试计划

### 5.1 单元测试 (`api/tests/test_tool_discovery.py`)

- [ ] 5.1.1 `test_search_tools_embedding_match`: Mock 5 个工具的 embedding cache，输入 intent="查询天气"，验证 `search_tools()` 返回 Top-3 按余弦相似度降序排列
- [ ] 5.1.2 `test_search_tools_top_k_truncation`: 缓存有 10 个工具，`top_k=3` 只返回 3 个
- [ ] 5.1.3 `test_search_tools_below_min_similarity`: 所有工具相似度 < 阈值（如 intent="随便说点什么"），验证返回空列表不报错
- [ ] 5.1.4 `test_embedding_cache_hit`: 工具 embedding 已在 `_TOOL_EMBEDDING_CACHE` 中，`search_tools()` 不再调 embedding API（Mock `embed_one` → `assert_not_called`）
- [ ] 5.1.5 `test_embedding_cache_miss_triggers_compute`: 缓存未命中时自动调 `embed_one()` 并写入缓存
- [ ] 5.1.6 `test_build_enabled_tools_layered_true`: `layered=True` 时只返回 `layer="core"` 的工具（knowledge/memory/web/datetime/persona_memory/tool_search），不含 MCP 工具
- [ ] 5.1.7 `test_build_enabled_tools_layered_false`: `layered=False` 时行为与旧版一致（全量返回）
- [ ] 5.1.8 `test_tool_search_tool_output_format`: `tool_search` 输出 `"找到 N 个相关工具：\n1. tool_name —— description\n  参数: ..."`
- [ ] 5.1.9 `test_toolspec_layer_default`: 新 ToolSpec 默认 `layer="core"`，MCP/Skill 工具显式设为 `"extended"`
- [ ] 5.1.10 `test_mcp_fingerprint_refresh_invalidates_embedding`: MCP 工具列表 fingerprint 变更后，缓存中旧 embedding 被清除并重新计算

### 5.2 集成测试

- [ ] 5.2.1 `test_core_tools_always_available`: 对话"帮我查一下知识库里的 Python 文档" → Agent 直接调用 knowledge_search（不先调 tool_search）
- [ ] 5.2.2 `test_extended_tool_discovered_and_used`: 挂载 test_mcp_server → 提问"查一下纽约的天气" → Agent 第 1 轮调 tool_search → 第 2 轮调获取到的 weather 工具 → 返回天气信息
- [ ] 5.2.3 `test_tool_search_cache_hit_same_turn`: 同一 turn 内 Agent 两次调用 tool_search("查询天气")，验证第二次直接从 `call_cache` 返回（event 标记 `"cached": true`）
- [ ] 5.2.4 `test_tool_search_not_called_for_simple_query`: 简单查询"现在几点"只触发 datetime 工具，不触发的 tool_search

### 5.3 回归测试

- [ ] 5.3.1 `test_layered_false_unchanged`: `build_enabled_tools(layered=False)` 行为与改动前完全一致（全量工具注入 prompt）
- [ ] 5.3.2 `test_existing_chat_unchanged`: 无 MCP Server 配置时，聊天行为不变（对话走核心工具，不走 tool_search）

### 5.4 性能验证

- [ ] 5.4.1 `search_tools()` 内存余弦计算 < 10ms（100 个工具 × 1536 维向量场景）
- [ ] 5.4.2 核心工具 prompt 占用对比：改动前（全量注入）vs 改动后（仅核心），在 3 个 MCP Server（~15 工具）时降幅 > 60%

### 5.5 Lint

- [ ] 5.5.1 `uv run ruff check .` 无新增 lint 问题
