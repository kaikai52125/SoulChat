## 1. 数据模型 & Schema

- [x] 1.1 `graph_models.py`：`CommunityNode` 增加 `embedding: list[float] | None = None` 字段，`DerivedFromEdge` 不涉及
- [x] 1.2 `graph_schema.py`：新增 `community_embedding_index` 向量索引（余弦，维度同 `embedding_dims`），注册到 `_VECTOR_INDEXES` 列表

## 2. Cypher 查询

- [x] 2.1 `cypher_queries.py`：新增 `COMMUNITY_VECTOR_SEARCH` —— 向量召回 Community 节点（`id`, `name`, `summary`, `score`），按 `user_id` 过滤
- [x] 2.2 `cypher_queries.py`：新增 `COMMUNITY_GET_BY_IDS` —— 批量取 Community 的 `id`, `name`, `summary`（给定 `user_id` + id 列表）
- [x] 2.3 `cypher_queries.py`：新增 `ENTITY_COMMUNITY_CONTEXT` —— 按 `user_id` + entity_id 列表取实体所属社区信息（`community_id`, `community_name`, `community_summary`）

## 3. 仓储层

- [x] 3.1 `memory_graph_repository.py`：新增 `search_communities_by_vector(user_id, vector, top_k)` 方法，封装 `COMMUNITY_VECTOR_SEARCH`
- [x] 3.2 `memory_graph_repository.py`：新增 `get_communities_by_ids(user_id, ids)` 方法，封装 `COMMUNITY_GET_BY_IDS`
- [x] 3.3 `memory_graph_repository.py`：新增 `get_entity_community_context(user_id, entity_ids)` 方法，封装 `ENTITY_COMMUNITY_CONTEXT`

## 4. 聚类引擎（Community embedding 生成）

- [x] 4.1 `label_propagation.py`：`LabelPropagationEngine.__init__` 增加 `embed_client: LLMClient | None = None` 参数
- [x] 4.2 `label_propagation.py`：`_generate_metadata()` 在 LLM 生成 name + summary 后，若 `embed_client` 不为 None，对 `{name}：{summary}` 调 `embed_client.embed_one()` 生成 embedding 写入 Community 节点
- [x] 4.3 `label_propagation.py`：`_generate_metadata()` 内部调用 `update_metadata` 时附上 embedding（需修改 `update_metadata` 或新增写回路径）
- [x] 4.4 `community_repository.py`：`update_metadata` 增加 `embedding: list[float] | None = None` 参数，更新 Cypher `COMMUNITY_UPDATE_META` 使其支持写 embedding 属性
- [x] 4.5 `orchestrator.py`：`run_extraction()` 中 `LabelPropagationEngine(...)` 调用传入已有的 `embed_client`

## 5. 检索增强（search_memory 三路融合）

- [x] 5.1 `searcher.py`：`search_memory()` 内新增 Community 向量召回步骤，复用已有 `query_vector` 或 `embed_client.embed_one(query)`
- [x] 5.2 `searcher.py`：实现 Community 召回 → 实体加权逻辑——命中社区的成员实体在融合分数中获得 community_boost（权重 0.10）
- [x] 5.3 `searcher.py`：调整融合权重常量 —— `_VECTOR_WEIGHT=0.45, _FULLTEXT_WEIGHT=0.25, _COMMUNITY_WEIGHT=0.10, _IMPORTANCE_WEIGHT=0.20`
- [x] 5.4 `searcher.py`：Community 召回失败或无命中时降级为原有二路融合（权重自动适配）
- [x] 5.5 `searcher.py`：检索结果 `results` dict 中每条增加 `community` 字段（`{id, name, summary}` 或 null），通过 `ENTITY_COMMUNITY_CONTEXT` 查询填充

## 6. 主动召回增强（recall_context 社区注入）

- [x] 6.1 `active_recall.py`：`_do_recall()` 内新增 `_recall_communities()` 协程——从向量召回的实体中提取 `community_id`，去重后批量取社区摘要
- [x] 6.2 `active_recall.py`：注入逻辑：命中实体 ≥ 2 个属于同一社区时，在上下文开头注入"相关主题："块（位于"我对用户的理解"之前）
- [x] 6.3 `active_recall.py`：格式 `· {community.name}：{community.summary}`，同社区去重
- [x] 6.4 `active_recall.py`：社区查询失败降级跳过（不阻断其他块），warning 日志

## 7. 记忆上下文格式化

- [x] 7.1 `searcher.py`：`format_memory_context()` 支持来自 `search_memory` 结果的 `community` 字段
- [x] 7.2 `searcher.py`：同社区多实体合并标注，格式 `【{community.name}】` 前置行，无社区实体不显示

## 8. 验证

- [x] 8.1 启动 Docker 服务（postgres, elasticsearch, neo4j, redis），确保 Neo4j schema 初始化成功（`ensure_graph_schema` 无报错）
- [x] 8.2 调用 `search_memory` 端到端验证：有 Community 时结果附带 `community` 字段，无 Community 时为 null
- [x] 8.3 调用 `recall_context` 端到端验证：满足阈值时上下文含"相关主题"块
- [x] 8.4 聚类触发验证：萃取一条记忆后，Neo4j 中 Community 节点 `embedding` 非空
