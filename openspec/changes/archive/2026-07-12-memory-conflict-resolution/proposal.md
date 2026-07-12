## Why

SoulChat 的记忆系统当前采用「记忆不遗忘」设计——新事实无条件叠加在旧事实上，导致六个具体问题：低置信度覆盖高置信度、语义重复的 Statement 堆积、冲突的 RELATION 并存、valid_at/invalid_at 字段形同虚设、反思引擎不检测矛盾、人类修正后相同错误可被重新萃取。这些缺陷使记忆图谱随使用时间增长而退化，亟需在 Cypher 层→萃取管线→反思引擎→人类反馈闭环四个层面建立完整的冲突处理机制。

## What Changes

- **修复 confidence 无条件覆盖 bug**：ENTITY_SAVE、RELATION_SAVE、STATEMENT_SAVE 三个 Cypher 查询中 confidence 改为取 max（与 importance 对齐）
- **激活 valid_at/invalid_at 字段**：萃取提示词要求 LLM 推断时间信息，检索时按有效时间过滤和标记过期事实
- **新增 RELATION 冲突检测**：同 source+predicate 但不同 target 的关系标记 SUPERSEDES 边，DYNAMIC 谓词新事实自动使旧事实过期
- **新增 Statement 语义去重**：通过向量相似度检测图谱中已有的高度相似 Statement，避免重复堆积
- **反思引擎增加矛盾检测**：reflect.jinja2 提示词增强，输出 contradictions 数组，自动解决时间变迁、推送真正矛盾到审查队列
- **人类修正免疫记忆**：新增 CorrectionRecord Neo4j 节点，用户 confirm/correct/delete 后阻止相同实体被重新萃取

## Capabilities

### New Capabilities

- `confidence-max-merge`: confidence 字段在 MERGE 时取 max 而非无条件覆盖，保护人工确认的高置信度事实
- `temporal-validity`: valid_at/invalid_at 字段从死字段变为功能字段，LLM 推断时间范围，检索时过滤/标记过期事实
- `relation-conflict-detection`: 同 subject+predicate 不同 object 的 RELATION 自动检测冲突，DYNAMIC 谓词自动 supersede，冲突推人类审查
- `statement-semantic-dedup`: Statement 写入前向量相似度检查，避免语义重复的陈述节点堆积
- `reflection-contradiction-detection`: 反思引擎识别记忆清单中的矛盾事实并分类处理（自动解决 vs 推送审查）
- `correction-immune-memory`: 人类修正/删除实体后创建免疫记录，阻止萃取管线重新创建已修正的实体

### Modified Capabilities

（无现有 spec 被修改）

## Impact

- **Cypher 查询**: `ENTITY_SAVE`, `RELATION_SAVE`, `STATEMENT_SAVE`（confidence 合并逻辑变更，向后兼容）
- **图谱模型**: 新增 `SUPERSEDES`、`CONTRADICTS` 关系类型 + `CorrectionRecord` 节点标签
- **萃取管线**: `orchestrator.py` 新增冲突检测步骤 + Statement 向量去重步骤
- **去重层**: `dedup.py` 新增 CorrectionRecord 免疫检查
- **反思引擎**: `reflector.py` 解析 contradictions 输出并执行自动修复/推送审查
- **检索层**: `searcher.py` 按 valid_at/invalid_at 过滤和标记关系
- **提示词**: `extract_triplet.jinja2`（时间推断）、`reflect.jinja2`（矛盾检测）
- **服务层**: `memory_service.py` 修正操作同步写入 CorrectionRecord
- **本体论**: `ontology.py` 新增 `PREDICATE_MUTABILITY` 谓词变更分类
