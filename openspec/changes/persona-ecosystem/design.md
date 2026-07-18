## Context

SoulChat 的 AgentPersona 系统已成熟：295 个 Python 文件中包含了完整的角色 CRUD、system prompt 管理、工具开关、知识库绑定、技能挂载。角色在对话中通过 `chat_service._compose_system_prompt()` 组装 system prompt 注入 LLM。

现有基础设施可复用：
- **PostgreSQL** — 所有业务数据，SQLAlchemy 2.0 async ORM
- **Redis + Celery** — 异步任务队列，已有 beat 定时调度（每日回顾、记忆巩固、社区聚类等）
- **Neo4j** — 记忆图谱，存有 Statement/Entity/Event 节点，可供日记收集上下文
- **AgentPersonaService.to_out_dict()** — 角色数据序列化入口，新增字段可在此统一注入
- **Skill 市场** — 已有完整的 marketplace CRUD + fork 模式（`skill_service.py`），角色市场直接复用模式
- **前端 PersonaEditModal** — 已有 Tab 结构（基础/工具/上下文/风格），可新增"成长"Tab

## Goals / Non-Goals

**Goals:**
1. 角色成长系统：每次对话互动自动记录 XP，计算等级和亲密度，触发里程碑，解锁特质
2. 角色日记：每天自动为有互动的角色生成第一人称日记，用户可浏览和标记已读
3. 角色市场：用户可发布角色到社区市场，其他人可浏览、搜索、评分、一键导入
4. 三个子系统联动：成长数据影响日记深度，市场展示成长统计，导入的角色从头开始成长
5. 最小侵入：chat_service 仅需 ~15 行增量，现有 API 零 breaking change

**Non-Goals:**
- 不做角色之间的"社交"（角色A和角色B互相影响）
- 不做付费市场（所有角色免费发布/导入）
- 不做角色的 AI 自动创建（用户手动创建角色后在市场发布）
- 不做实时市场通知（如"你发布的角色被导入了"）
- 不做角色版本管理和差异升级（导入后角色配置独立演进）

## Decisions

### Decision 1: 成长数据独立表而非 agent_personas 加列

**选择**: 新建 `persona_growth` 表，与 `agent_personas` 分离。

**理由**:
- agent_personas 是"角色模板"，persona_growth 是"(角色, 用户) 对"的实例数据
- 一个角色被多个用户使用时（市场导入），每个用户独立成长
- 保持 agent_personas 表干净，避免列膨胀（它已有 25 列）

**替代方案**: 在 agent_personas 上加 xp/level 列。否决——混淆了"模板"和"实例"的概念。

### Decision 2: XP 记录时机在 chat_service 消息落库后

**选择**: 在 `chat_service._run_chat_turn_bg()` 末尾、消息已落库后，调用 `record_interaction()`。

**理由**:
- 此时所有上下文（消息内容、工具调用结果、citation 列表）都完整
- 异步 fire-and-forget，不阻塞 SSE 流
- 已有 `_BG_TASKS` 模式可复用（见 chat_service 中的 `task.add_done_callback(_BG_TASKS.discard)` 模式）

**替代方案**: 在 controller 层记录。否决——需要在多个 controller（chat、group_chat）分散改动，且无法获取 LLM 内部状态。

### Decision 3: 日记用 Celery beat 定时生成而非实时

**选择**: 每天 23:00 Celery beat 触发 `generate_persona_diaries`。

**理由**:
- 日记是"今天的总结"，不是实时产物
- LLM 生成每篇日记需要 2-5 秒，多个角色 × 多个用户会需要较长时间——Celery worker 异步执行不阻塞用户
- 复用现有 beat 基础设施（daily_review 也在 Celery beat 中，每天 22:00）

**替代方案**: 用户主动触发生成。否决——增加用户操作负担，且与"惊喜感"的产品定位矛盾。

### Decision 4: 市场快照（snapshot）而非引用

**选择**: 发布时将角色完整配置序列化到 `persona_snapshot` JSONB 列中。

**理由**:
- 发布后卖家继续修改角色配置，不应影响已发布的版本
- 导入者获得的是发布时的精确副本
- JSONB 在 PostgreSQL 中可查询（如需按 system_prompt 长度筛选等）

**替代方案**: 只存 persona_id 引用。否决——卖家修改角色后，市场版本会变，影响用户信任。

### Decision 5: 特质通过 system prompt 注入实现

**选择**: 解锁的特质在 `chat_service._compose_system_prompt()` 中追加特质的注入提示词。

**理由**:
- 不需要修改 LLM 调用层，完全在 prompt 层面实现
- 每个特质对应一段设计好的提示词（在 `trait_config.py` 中集中管理）
- 不同特质可以组合注入（多个已解锁特质拼接在一起）

**替代方案**: 修改 LLM 参数或使用 function calling 实现。否决——过于复杂，且 prompt 注入更灵活可控。

### Decision 6: 市场复用 Skill marketplace 模式

**选择**: 遵循 `skill_service.py` 的 list_marketplace / fork 模式，新建 `persona_market_service.py`。

**理由**:
- 开发者已经熟悉这套模式，降低理解和维护成本
- API 设计一致（`GET /personas/marketplace` 对应 `GET /skills/marketplace`）
- 前端可复用类似的卡片布局和分页逻辑

### Decision 7: 日记内容隐私边界

**选择**: 日记 prompt 中明确指示 LLM 不暴露用户真实姓名/位置/联系方式。

**理由**:
- 即使用户在对话中提过，日记是"角色视角的观察"，不应包含 PII
- 日记存在数据库中，如果未来支持分享功能，PII 泄露风险更高

## Risks / Trade-offs

**[R1] LLM 调用成本增加** → 日记生成每天每角色一次 LLM 调用。假设 1000 个活跃用户、平均 3 个角色 = 3000 次/天额外调用。
→ **缓解**: 日记用用户自己的 chat 模型（不额外配置），每篇约 500 token 输出，成本可控。后续可加"跳过无互动角色"的早期返回优化。

**[R2] chat_service 改动可能引入延迟** → growth 记录在每次回答后触发，包括 DB 写操作。
→ **缓解**: 使用 `asyncio.create_task()` fire-and-forget，不影响 SSE 流的首字延迟。写入是单行 UPSERT，<5ms。

**[R3] 市场内容质量** → 低质量角色可能泛滥。
→ **缓解**: 第一版不审核，依赖评分系统自然筛选。未来可加"最小使用量"门槛（角色至少被使用 10 次才能发布）。

**[R4] 日记质量不稳定** → LLM 输出的日记可能过于模板化或不够"像那个角色"。
→ **缓解**: prompt 中注入角色的 system_prompt 前 200 字作为风格锚定，并用 level 数据限制洞察深度（低等级角色不做深层分析）。后续可加用户反馈机制（"这篇日记不像XX"）。

**[R5] 数据增长** → persona_diaries 表随用户数和时间线性增长。
→ **缓解**: 每用户每天最多 N 篇（N=活跃角色数），假设 3 角色 × 400 字/篇 × 365 天 = 438KB/年/用户。可接受。未来可加 TTL 清理（如 90 天后自动归档）。

## Open Questions

1. **日记是否需要支持用户回复？** — 如果角色写了日记，用户是否能"回复"日记？这会让日记变成一个异步对话。暂定 MVP 不做，观察用户行为后决定。
2. **市场是否需要"精选"推荐？** — 算法推荐 vs 人工精选？暂定按下载量/评分排序。
3. **特质是否可以跨角色迁移？** — 如果用户导入了市场角色，原角色的成长特质是否部分保留？暂定不保留，从零开始。
