## Why

Community（社区聚类）是记忆图谱中投入最大但产出为零的子系统——LPA 聚类、LLM 摘要生成、全套索引和维护逻辑已就绪，但聚类结果从未接入检索和召回链路。Community 发现的是图结构 + 语义空间中涌现的隐性主题分组，这层信号恰好填补了 RELATION（太精确）和 Insight（太抽象）之间的空白。现在接入，让已有的聚类基础设施真正产生检索价值。

## What Changes

- Community 节点新增 `embedding` 属性并对 `name + summary` 做向量化，建向量索引，使 Community 可被语义检索
- `search_memory` 检索从二路融合（Entity 向量 + Entity 全文）升级为三路融合（+ Community 向量召回），Community 命中作为同社区实体加权信号，不替代 Entity 作为检索目标
- 检索结果附带实体所属社区的 `name` + `summary`，LLM 看到实体时同步获得主题上下文
- `recall_context` 主动召回注入"相关主题"摘要块，与 Insight 自然共存
- `LabelPropagationEngine` 构造器增加 `embed_client`，生成社区元数据时顺带完成 embedding
- 新增 3~4 条 Cypher 查询（Community 向量召回、批量取社区信息、同社区实体查询）

## Capabilities

### New Capabilities

- `community-embedding`: Community 节点支持向量化（name + summary embedding），建向量索引，支持语义检索
- `community-retrieval-boost`: 检索链路增加 Community 向量召回通路，匹配到的社区的成员实体获得排序加权
- `community-context-injection`: 检索结果和主动召回上下文附带社区名和摘要，作为 LLM 的额外背景信息

### Modified Capabilities

<!-- 无已有 capability 需要修改 —— Community 是全新接入，不改变现有检索语义 -->

## Impact

- **检索层** (`searcher.py`, `active_recall.py`): 核心改动，增加 Community 召回通路的融合逻辑
- **图谱仓储** (`memory_graph_repository.py`, `cypher_queries.py`): 新增社区召回/查询方法
- **图谱模型** (`graph_models.py`): CommunityNode 增加 embedding 字段
- **图谱 Schema** (`graph_schema.py`): 新增 Community 向量索引
- **聚类引擎** (`label_propagation.py`): 构造器增加 embed_client，生成元数据时写 embedding
- **前端**: 无破坏性变更，社区摘要会在对话上下文中自然呈现
