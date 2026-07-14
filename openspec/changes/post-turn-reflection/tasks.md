## 1. Reflector 模块

- [ ] 1.1 新建 `core/agent/reflector.py`：`ChatReflector` 类，包含 `reflect(user_msg, assistant_answer, tool_calls_log, persona_name) -> ReflectionResult` 方法
- [ ] 1.2 新建 `prompts/chat_reflection.jinja2`：3 维 self-check prompt，输出严格 JSON
- [ ] 1.3 `ReflectionResult` Pydantic model：`completeness, tool_usage, user_satisfaction, key_takeaway, should_remember`
- [ ] 1.4 实现 `_format_reflection_block(result, user_msg_summary) -> str` —— Markdown 反思块格式化函数

## 2. 聊天服务集成

- [ ] 2.1 `services/chat_service.py` `_run_chat_turn_bg()`：在 `bus.publish("done", ...)` 之后，`asyncio.create_task(_reflect_and_persist(...))`
- [ ] 2.2 实现 `_reflect_and_persist(persona_id, user_msg, answer, tool_calls, persona_name)` —— 独立 DB session，调 ChatReflector，写 memory_text
- [ ] 2.3 判断 trivial message 跳过反思（复用 `_recall_lagged` 中类似的判断逻辑，或新增 `_is_trivial_message`）
- [ ] 2.4 判断无需反思的场景（短回答 + 无工具调用）

## 3. System Prompt 注入

- [ ] 3.1 `services/chat_service.py` `_compose_system_prompt()`：从 `memory_text` 中提取 `--- reflection` 开头的块
- [ ] 3.2 取最近 10 条反思，注入 system prompt 末尾（"相关经验"区块，在 memory_text 主内容之后）
- [ ] 3.3 格式：`【近期反思与经验】\n- 经验教训1\n- 经验教训2\n...`

## 4. 配置

- [ ] 4.1 `config.py`：新增 `chat_reflection_enabled: bool = True`
- [ ] 4.2 `config.py`：新增 `chat_reflection_model: str | None = None`（None = 复用聊天模型）
- [ ] 4.3 `.env` 可选配置：`CHAT_REFLECTION_ENABLED=false` 关闭

## 5. 前端（可选，后续迭代）

- [ ] 5.1 `PersonaEditModal.tsx` Memory 标签页：展示反思分区（按时间倒序）
- [ ] 5.2 每个反思卡片展示：时间、对话摘要、关键经验教训

## 6. 测试计划

### 6.1 单元测试 (`api/tests/test_chat_reflection.py`)

- [ ] 6.1.1 `test_reflector_returns_valid_json`: 给定典型的 user_msg + assistant_answer + tool_calls_log，验证 `ChatReflector.reflect()` 返回合法 `ReflectionResult`（包含 completeness/tool_usage/user_satisfaction/key_takeaway/should_remember）
- [ ] 6.1.2 `test_reflector_should_remember_true`: 回答有明显遗漏时，`should_remember=true`，key_takeaway 非空
- [ ] 6.1.3 `test_reflector_should_remember_false`: 回答完整正确时，`should_remember=false`，key_takeaway 为 "本次回答无问题"
- [ ] 6.1.4 `test_reflection_block_format`: `_format_reflection_block()` 输出符合 Markdown `--- reflection 时间戳 ---` 格式，含对话摘要和三维评估
- [ ] 6.1.5 `test_is_trivial_message_detection`: "你好"→true, "谢谢"→true, "帮我写代码"→false, "今天天气怎么样"→false
- [ ] 6.1.6 `test_short_answer_no_tools_skips_reflection`: 回答 < 50 字且未使用工具时，`_should_skip_reflection()` 返回 true
- [ ] 6.1.7 `test_extract_recent_reflections`: 从包含 20 条 reflection 块的 memory_text 中，正确提取最近 10 条
- [ ] 6.1.8 `test_reflection_model_config_fallback`: `chat_reflection_model=None` 时，复用聊天模型构建 Reflector

### 6.2 集成测试

- [ ] 6.2.1 `test_e2e_reflection_appended_to_memory`: 发送需要多工具的问题 → 回答正常流式返回 → 等待 3 秒 → 检查 persona `memory_text` 末尾新增 `--- reflection` 块
- [ ] 6.2.2 `test_reflection_injected_next_turn`: 第一轮回答产生反思 → 下一轮对话的 system prompt 中出现 `【近期反思与经验】` 块和对应 key_takeaway
- [ ] 6.2.3 `test_trivial_message_no_reflection`: 发送"你好" → 确认不触发 reflector（日志无不必要的 LLM 调用）
- [ ] 6.2.4 `test_reflection_does_not_block_answer`: 反思任务使用 `asyncio.create_task`，回答流式返回的 `done` 事件在反思完成前就已发送（验证事件时间戳）

### 6.3 回归测试

- [ ] 6.3.1 `test_chat_behavior_unchanged_with_reflection_enabled`: 反思开启时，聊天质量和延迟不劣化（回答内容不变，反思是异步后置）
- [ ] 6.3.2 `test_chat_behavior_unchanged_with_reflection_disabled`: `chat_reflection_enabled=false` → 行为与改动前完全一致

### 6.4 可靠性测试

- [ ] 6.4.1 `test_reflector_exception_does_not_crash_chat`: Mock reflector 抛异常 → 主流程正常结束，日志有 warning
- [ ] 6.4.2 `test_db_write_failure_does_not_crash_chat`: Mock persona_repo.update_memory_text() 抛异常 → 不传播，日志有 error
- [ ] 6.4.3 `test_memory_text_not_exceed_50000_chars`: 模拟 300 条反思追加后，总长度不超 schema 限制，旧反思被截断

### 6.5 Lint

- [ ] 6.5.1 `uv run ruff check .` 无新增 lint 问题
