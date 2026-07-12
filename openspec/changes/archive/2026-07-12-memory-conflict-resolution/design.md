## Context

SoulChat 的记忆系统基于 Neo4j 图谱，采用四层溯源结构（Dialogue → Chunk → Statement → Entity）加语义层（Entity→RELATION→Entity, Event, Insight）。当前所有写入使用 `MERGE ... SET` 模式，但 confidence 字段无条件覆盖已有值，valid_at/invalid_at 始终为 NULL，且无任何冲突检测机制。

本次设计在不变更现有架构的前提下，在四个层面逐层修补：Cypher 查询层（confidence max）、萃取管线（时间推断 + Statement 去重 + RELATION 冲突检测）、反思引擎（矛盾识别）、人类反馈闭环（免疫记忆）。

现有相关文件：
- `api/app/core/memory/graph_models.py` — 节点/边 Pydantic 模型
- `api/app/repositories/neo4j/cypher_queries.py` — 所有 Cypher 语句
- `api/app/repositories/neo4j/memory_graph_repository.py` — Neo4j 数据访问层
- `api/app/core/memory/extraction/orchestrator.py` — 萃取编排器
- `api/app/core/memory/extraction/dedup.py` — 实体去重消歧
- `api/app/core/memory/reflection/reflector.py` — 反思引擎
- `api/app/core/memory/retrieval/searcher.py` — 记忆检索
- `api/app/core/memory/ontology.py` — 受控词表
- `api/app/core/memory/prompts/` — LLM 提示词模板
- `api/app/services/memory_service.py` — 记忆服务（人类反馈）

## Goals / Non-Goals

**Goals:**
- 修复 confidence 被低置信度新事实覆盖的 bug
- 使 valid_at/invalid_at 成为功能字段（LLM 推断 + 检索消费）
- 同 subject+predicate 不同 object 的 RELATION 自动检测冲突并标记
- Statement 语义去重防止重复节点堆积
- 反思引擎检测记忆矛盾并自动解决/推送审查
- 人类修正后阻止相同实体被重新萃取

**Non-Goals:**
- 不改变现有四层溯源架构
- 不引入新的外部依赖
- 不修改 API 接口签名（只增强行为）
- 不做完整的贝叶斯置信度累积模型（留待后续）
- 不做 LLM 驱动的复杂冲突仲裁 Agent（留待后续）

## Decisions

### D1: confidence 取 max 而非加权平均

**选择**: MERGE 时 confidence 取 `MAX(existing, new)`，与 importance 一致。

**理由**: confidence 表示"最高确定性快照"。置信度不应被不确定的新事实稀释。加权平均需要记录源数量做分母，复杂度高且语义不清晰。

**替代方案**: Bayesian 更新（需要 prior/posterior 模型）→ 过于复杂，搁置。

### D2: SUPERSEDES 边 + invalid_at 时间戳双重标记

**选择**: 检测到同 predicate 冲突时，在旧关系上同时设 `invalid_at = now()` 并连 `SUPERSEDES` 边到新关系。

**理由**: 两个标记各有用途——`invalid_at` 在 Cypher 查询中容易过滤（`WHERE r.invalid_at IS NULL`），`SUPERSEDES` 边保留溯源链（谁取代了谁）。单用一种会丢失信息。

**替代方案**: 仅用 invalid_at（丢失溯源链）、仅用 SUPERSEDES 边（查询不便）→ 双重标记代价极小（一条 SET + 一条 CREATE），收益最大化。

### D3: PREDICATE_MUTABILITY 分类驱动自动/手动仲裁

**选择**: 在 `ontology.py` 新增 `PREDICATE_MUTABILITY` 字典，标注每个谓词为 `static`/`dynamic`/`semi-dynamic`。DYNAMIC 谓词的新事实自动 supersede 旧事实，STATIC 谓词的冲突推人类审查。

**理由**: "位于"（搬家）和"别名属于"（名字从不变化）不应同等处理。静态属性出现冲突说明出了严重问题（LLM 幻觉或用户说谎），需要人类介入。动态属性冲突是正常的人生变化。

**替代方案**: 完全依赖 LLM 判断（不可靠、非确定性）、全部自动 supersede（静态属性冲突被静默吞掉）→ 分类驱动是最佳折中。

### D4: Statement 语义去重在后台异步执行

**选择**: 萃取时不做同步向量查询（会增加延迟），改为每次萃取正常写入 Statement embedding，由 Celery beat 定时任务扫描重复。

**理由**: 萃取在对话热路径上，每次 Statement 都做一次 Neo4j 向量查询会显著增加延迟。Statement 去重是"锦上添花"而非"紧急修复"，后台异步完全够用。目前先落地 embedding 写入 + 仓库查询方法，beat 任务后续再加。

**替代方案**: 同步去重（延迟增加）→ 搁置，先异步。

### D5: CorrectionRecord 存在 Neo4j 中而非仅查 PostgreSQL

**选择**: 人类修正后除了 PostgreSQL `memory_corrections` 审计表，额外在 Neo4j 创建 `CorrectionRecord` 节点。去重层查询时直接查 Neo4j（单次 Cypher），不走跨库 JOIN。

**理由**: 萃取管线全在 Neo4j 侧操作，如果每次去重都要跨库查 PostgreSQL 会引入延迟和复杂度。CorrectionRecord 作为 Neo4j 节点与 Entity 在同一图中，一次查询即可完成。

**替代方案**: 仅依赖 PostgreSQL `memory_corrections`（跨库查询复杂、慢）→ Neo4j 侧冗余存储是最简方案。

### D6: 反思矛盾检测输出使用结构化数组

**选择**: reflect.jinja2 提示词新增 `contradictions` 数组输出，包含 type/description/resolved/newer_statement/older_statement 字段。反思引擎解析后分流处理。

**理由**: 结构化输出便于程序化处理。`resolved` 字段让 LLM 判断是否可以自动解决——简单时间变迁（"之前…现在…"）可自动 supersede，真正矛盾需要人类判断。

## Risks / Trade-offs

- **[LLM 时间推断不准]** → Prompt 中强调"不确定就填 NULL，不要瞎编"
- **[SUPERSEDES 边累积]** → 定期清理或限制保留最近 N 跳
- **[CorrectionRecord 节点增长]** → 按 user_id 索引，定期 TTL 清理（如保留 90 天）
- **[反思矛盾检测误报]** → `resolved=true` 仅对高置信度矛盾执行自动修复；低置信度矛盾只标记不操作
- **[confidence max 语义变更]** → 已有 human_verified 实体 confidence=1.0 不受影响（新值 ≤1.0 不会覆盖），向后兼容
