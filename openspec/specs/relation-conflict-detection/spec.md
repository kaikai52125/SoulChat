# relation-conflict-detection

## Purpose

Memory conflict resolution capability: 

## ADDED Requirements

### Requirement: Detect same-predicate different-target relations

当萃取管线生成新的 RELATION 边时，系统 SHALL 查询图谱中是否已有相同 (source_entity, predicate) 但不同 (target_entity) 的已有关系。

#### Scenario: Existing relation with different target
- **WHEN** 新关系为 (用户)-[位于]->(上海)，图谱中已有 (用户)-[位于]->(北京)
- **THEN** 系统识别到冲突，根据谓词变更特性决定后续处理

#### Scenario: No conflicting relation exists
- **WHEN** 新关系为 (用户)-[偏好]->(咖啡)，图谱中没有 (用户)-[偏好]->(任何其他)
- **THEN** 系统正常写入，不做冲突处理

### Requirement: Auto-supersede for dynamic predicates

当冲突谓词在 `PREDICATE_MUTABILITY` 中标注为 `dynamic` 且新陈述的 `temporal_type` 为 DYNAMIC 时，系统 SHALL 自动将旧关系标记为被取代：设 `invalid_at = now()` 并创建 `SUPERSEDES` 边从旧关系指向新关系。

#### Scenario: Location change auto-supersedes
- **WHEN** 新关系 (用户)-[位于]->(上海)，旧关系 (用户)-[位于]->(北京)，"位于"为 dynamic 谓词
- **THEN** 旧关系的 invalid_at 被设为当前时间，旧关系 -[SUPERSEDES]-> 新关系

### Requirement: Push static predicate conflicts to review queue

当冲突谓词在 `PREDICATE_MUTABILITY` 中标注为 `static` 时，系统 SHALL 降低新关系的 confidence（乘以 0.7），将其推送到人类审查队列，不断开旧关系。

#### Scenario: Alias conflict pushed to review
- **WHEN** 新关系 (别名X)-[别名属于]->(实体A)，旧关系 (别名X)-[别名属于]->(实体B)，"别名属于"为 static 谓词
- **THEN** 新关系 confidence 降低，旧关系不受影响，低置信度关系出现在审查列表中

### Requirement: New graph relation types added

图谱 SHALL 支持以下新增关系类型：
- `SUPERSEDES`：一条 RELATION 边取代另一条
- `CONTRADICTS`：两条 Statement/RELATION 之间存在矛盾

#### Scenario: SUPERSEDES chain stored in graph
- **WHEN** 关系 A 被关系 B 取代
- **THEN** 图谱中存在 `(A)-[:SUPERSEDES]->(B)` 边
