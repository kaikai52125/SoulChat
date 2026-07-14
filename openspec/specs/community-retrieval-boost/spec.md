# Community Retrieval Boost

## Purpose

将 Community 向量召回通路接入记忆检索管线，使语义匹配到的社区的成员实体获得排序加权。在 Entity 向量 + Entity 全文的基础上增加 Community 信号，形成三路融合检索。Community 作为加权信号而非独立检索目标。

## Requirements

### Requirement: Community vector recall in search_memory

`search_memory` SHALL 在向量/全文召回之外增加 Community 向量召回通路，使用与 Entity 向量召回相同的 query vector（复用，不额外 embedding）。

#### Scenario: Community recall enriches entity candidates
- **WHEN** `search_memory` 执行检索且 Community 有有效 embedding
- **THEN** 系统 SHALL 用 query vector 检索 `community_embedding_index`
- **THEN** 命中的社区的成员实体 SHALL 获得 community_boost 加权（融合权重 0.10）
- **THEN** Community 召回失败（如索引不支持或无匹配）SHALL 降级为仅 Entity 向量 + 全文融合，不阻断检索

### Requirement: Three-way fusion with community signal

检索最终分数 SHALL 由四部分融合：Entity 向量（0.45）、Entity 全文（0.25）、Community 加成（0.10）、重要度（0.20）。

#### Scenario: Community-matched entities receive ranking boost
- **WHEN** 实体 A 的社区被 Community 向量召回命中，实体 B 未被命中
- **THEN** 在相似向量/全文得分下，实体 A SHALL 排名高于实体 B
- **THEN** Community 加成不超过 0.10 × community_score，不足以覆盖显著的向量/全文得分差距

#### Scenario: No community hit degrades gracefully
- **WHEN** Community 向量召回无命中（score 过低或无有效 embedding）
- **THEN** 系统 SHALL 按原有 Entity 向量 + 全文 + 重要度三因素融合
- **THEN** 权重自动归一化为 0.56 / 0.31 / 0.13（与原行为等效）

### Requirement: Community context in search_memory results

`search_memory` 的每条返回结果 SHALL 附带实体所属社区信息。

#### Scenario: Entity result includes community field
- **WHEN** 检索结果实体拥有 `community_id` 且对应社区存在
- **THEN** 结果 dict SHALL 包含 `community: {id, name, summary}` 字段
- **THEN** 若实体无社区归属，`community` 字段 SHALL 为 `null`

### Requirement: MemoryGraphRepository community retrieval methods

`MemoryGraphRepository` SHALL 提供社区向量召回和批量查询方法。

#### Scenario: Search communities by vector
- **WHEN** 调用 `search_communities_by_vector(user_id, vector, top_k)`
- **THEN** 系统 SHALL 执行 `COMMUNITY_VECTOR_SEARCH` Cypher 查询
- **THEN** 返回 `[{id, name, summary, score}, ...]`

#### Scenario: Get communities by IDs
- **WHEN** 调用 `get_communities_by_ids(user_id, ids)`
- **THEN** 系统 SHALL 返回每个已存在社区的 `{id, name, summary}`
- **THEN** 不存在的 id SHALL 被静默忽略
