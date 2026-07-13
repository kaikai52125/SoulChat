## ADDED Requirements

### Requirement: Community node has embedding field
Community 节点 SHALL 拥有 `embedding` 属性，存储 `float` 列表，维度与系统 `embedding_dims` 配置一致。

#### Scenario: Community node schema includes embedding
- **WHEN** `LabelPropagationEngine._generate_metadata()` 完成社区 name 和 summary 生成
- **THEN** 系统 SHALL 对 `{name}：{summary}` 拼接文本调用 `embed_client.embed_one()` 生成 embedding
- **THEN** 生成的 embedding SHALL 写入 Community 节点的 `embedding` 属性
- **THEN** 若 `embed_client` 为 None，embedding 字段 SHALL 保持为 null 且不报错

### Requirement: Community vector index
Neo4j 中 SHALL 存在 Community 节点的向量索引 `community_embedding_index`，维度与 `embedding_dims` 一致，余弦相似度。

#### Scenario: Vector index is created on schema init
- **WHEN** `ensure_graph_schema()` 在应用启动时被调用
- **THEN** 系统 SHALL 幂等创建 `community_embedding_index` 向量索引
- **THEN** 索引类型为 VECTOR INDEX，覆盖 `Community.embedding`，余弦相似度

#### Scenario: Community vector search returns matching communities
- **WHEN** 调用 Community 向量检索查询，传入 query vector 和 top_k
- **THEN** 系统 SHALL 返回 top_k 个余弦相似度最高的 Community 节点，包含 `id`, `name`, `summary`, `score`
- **THEN** 结果 SHALL 按 `user_id` 过滤确保多租户隔离

### Requirement: Embed client injection into clustering engine
`LabelPropagationEngine` 构造器 SHALL 接受 `embed_client: LLMClient | None` 参数。

#### Scenario: Clustering engine receives embed client
- **WHEN** `run_extraction()` 在萃取完成后调用 `LabelPropagationEngine(chat_client=..., embed_client=...)`
- **THEN** 引擎 SHALL 在 `_generate_metadata()` 中复用该 `embed_client` 为社区生成 embedding
- **THEN** 若未传入 `embed_client`，元数据生成 SHALL 正常完成（兜底名称拼接），仅跳过 embedding 步骤
