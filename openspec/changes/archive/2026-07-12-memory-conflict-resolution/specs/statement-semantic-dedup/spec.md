## ADDED Requirements

### Requirement: Statement vector similarity check

系统 SHALL 支持通过向量相似度查询图谱中是否已有与给定 Statement 语义高度相似的已有陈述。相似度使用余弦相似度，阈值默认为 0.92。

#### Scenario: Nearly identical statement found
- **WHEN** 新 Statement "用户在北京工作"的向量与已有 Statement "用户在北京市工作"的余弦相似度为 0.95
- **THEN** 系统返回已有 Statement 的信息

#### Scenario: Different statement not matched
- **WHEN** 新 Statement "用户在北京工作"的向量与已有 Statement "用户喜欢喝咖啡"的余弦相似度为 0.3
- **THEN** 系统不返回匹配

### Requirement: Statement embedding saved on extraction

每次萃取写入 Statement 时，系统 SHALL 将 Statement 的向量 embedding 存入 Neo4j 节点的 `embedding` 属性，以便后续语义去重查询使用。

#### Scenario: Embedding persisted with statement
- **WHEN** 一条新的 Statement 写入图谱
- **THEN** 该 Statement 节点的 embedding 属性包含向量值

### Requirement: Semantic dedup runs asynchronously

Statement 语义去重 SHALL 不作为萃取热路径上的同步操作，而是由后台 Celery beat 任务定期扫描并合并高度相似的重复 Statement。

#### Scenario: Dedup task merges similar statements
- **WHEN** beat 任务发现两条余弦相似度 ≥ 0.92 的 Statement
- **THEN** 保留较早的 Statement，将较新的 Statement 链接到已有 Statement（加 SEMANTICALLY_SIMILAR_TO 边），被合并的 Statement 的 MENTIONS 边重定向
