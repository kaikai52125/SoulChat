## Context

当前记忆图谱的检索链路（`search_memory` + `recall_context`）完全围绕 Entity 节点展开：向量/全文召回 Entity → 取 RELATION 一跳邻居 → 拼成 LLM 上下文。Community 子系统（LPA 聚类 + LLM 摘要 + 成员归属）已完整运行——每次萃取后增量聚类、生成社区名和摘要、实体挂 `IN_COMMUNITY` 边——但聚类结果在检索和召回链路中完全不可见。

**约束**：
- 不改变 Entity 作为唯一检索目标的定位（Community 是加权信号，不替代）
- 不改变 Insight 的现有行为（Community 与 Insight 共存）
- 不新增独立 Agent 工具（Community 能力融入现有 `search_memory`）
- 前端 MemoryPage 社区视图无需修改
- 新增向量索引需与现有 `embedding_dims` 配置一致

## Goals / Non-Goals

**Goals:**
- Community 节点可被语义检索（name + summary embedding → 向量索引）
- 检索时 Community 向量命中转化为同社区实体的排序加权
- 检索结果附带社区名 + 摘要作为上下文标注
- 主动召回注入"相关主题"社区摘要块
- 社区元数据生成时自动完成 embedding

**Non-Goals:**
- Community 节点不直接作为检索返回目标（只间接加权实体）
- 不修改聚类算法（LPA）本身
- 不修改社区元数据生成的 LLM prompt
- 不新增前端 UI 或 API 端点
- 不做跨社区桥接实体发现（后续 Phase 考虑）

## Decisions

### 决策 1：Community 召回作为加权信号，而非独立返回目标

**选择**：Community 向量命中 → 取其成员实体 → 对已在候选集中的实体加权，对未在候选集中的高重要度实体补录（低优先级追加）。

**理由**：LLM 最终需要的仍是"实体 + 关系"的精确事实。如果 Community 命中直接返回摘要文本而不带实体，等于回到了模糊摘要路线（与 Insight 重叠）。保持 Entity 为唯一返回载体，Community 作为"发现更多相关实体"的扩展通路。

**替代方案**（已拒绝）：Community 命中后直接返回社区摘要作为独立记忆条目 → 与 Insight 雷同，且丢失精确事实回溯能力。

### 决策 2：三路融合权重调整

**选择**：
```
_VECTOR_WEIGHT    = 0.45   (原 0.55，略降以容纳第三路)
_FULLTEXT_WEIGHT  = 0.25   (原 0.30)
_COMMUNITY_WEIGHT = 0.10   (新增：Community 命中 → 实体加成)
_IMPORTANCE_WEIGHT = 0.20  (原 0.15，略提让高质量实体更突出)
```

**理由**：Community 权重 10% 是"微弱加成"——足以让同社区实体在竞争中稍微靠前，但不至于主导排序（LPA 聚类有噪音）。重要度权重提到 0.20 是为了让经过巩固的长期实体在社区加权之外也有稳定优势。

### 决策 3：Community embedding 内容 = name + summary 拼接

**选择**：`embedding = embed(name + "：" + summary)`，在 `_generate_metadata()` 中生成 name/summary 后立即做 embedding。

**理由**：name 和 summary 分别是紧凑和展开的主题描述，拼接后 embedding 能同时捕获两种粒度。单独对 name 做 embedding 太短（≤10 字），单独对 summary 做太依赖 LLM 生成质量。拼接是最简单的融合方式。

### 决策 4：recall_context 社区摘要注入格式

**选择**：在"我对用户的理解"（Insight）之前插入"相关主题"块：
```
相关主题：
· 编程技能：用户是一名后端开发者，熟悉 Python、Go
· 生活方式：用户偏好早起跑步，注重工作生活平衡
```

去重逻辑：命中实体 ≥ 2 个属于同一社区时，才注入该社区摘要（单个实体命中社区视为信号不够强）。

**理由**：放在 Insight 之前是因为 Community 比 Insight 更"客观"（基于图结构聚类），可以作为背景先行；Insight 是"主观归纳"，放在后面形成递进。阈值设为 2 是为了避免单个偶然命中的社区被误认为相关。

### 决策 5：LabelPropagationEngine 依赖注入

**选择**：构造器签名从 `__init__(self, chat_client: LLMClient | None = None)` 改为 `__init__(self, chat_client: LLMClient | None = None, embed_client: LLMClient | None = None)`。

调用方（`orchestrator.py` 的 `run_extraction`）传入已有的 `embed_client`。

**理由**：`embed_client` 在 `orchestrator.py` 中已经存在于上下文中（entity name 向量化用的就是它），无需新建实例。`chat_client` 用于 LLM 生成 name/summary，`embed_client` 用于生成的文本做 embedding，职责清晰分开。

### 决策 6：新增 Cypher 查询

**选择**：新增 3 条查询，复用现有查询模式：

| 查询 | 用途 | 索引依赖 |
|------|------|----------|
| `COMMUNITY_VECTOR_SEARCH` | 按 query 向量召回 top-K 社区（返回 id + name + summary + score） | `community_embedding_index` |
| `COMMUNITY_GET_BY_IDS` | 批量取社区 name + summary（给定 id 列表） | `id IS UNIQUE` 约束 |
| `ENTITY_COMMUNITY_CONTEXT` | 取一批实体的 community_id + 社区名 + 同社区高重要度其他实体 | `user_id` 索引 |

## Risks / Trade-offs

- **[噪音放大]** LPA 聚类本身有噪音（错误归组），Community 召回会让错误归组的实体也获得加权 → **缓解**：Community 权重仅 10%，不会主导排序；且 LPA 有社区合并（余弦 > 0.85）和摘要 LLM 校验两层质量控制
- **[冷启动]** 新用户实体少时聚类结果不稳定，Community 召回可能引入随机性 → **缓解**：`recall_context` 的去重阈值（≥2 个实体命中同一社区）确保小样本时不注入
- **[embedding 成本]** 每次社区元数据生成多一次 embedding 调用（name + summary 文本很短，<100 字，成本可忽略）
- **[与 Insight 的边界模糊]** 两者都是高层摘要 → **接受**：LLM 自行判断如何使用两者，不对模型层做人为区分
