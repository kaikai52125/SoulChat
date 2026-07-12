# confidence-max-merge

## Purpose

Memory conflict resolution capability: 

## ADDED Requirements

### Requirement: Entity confidence uses max on merge

当通过 `ENTITY_SAVE` Cypher 写入实体时，confidence 字段 SHALL 取已有值与新值的较大者，而非无条件覆盖。

#### Scenario: New entity with higher confidence
- **WHEN** 图谱中已有实体 confidence=0.5，新萃取写入同一实体 confidence=0.9
- **THEN** 最终 confidence 为 0.9

#### Scenario: New entity with lower confidence
- **WHEN** 图谱中已有实体 confidence=0.9（或 human_verified=true 的 1.0），新萃取写入同一实体 confidence=0.3
- **THEN** 最终 confidence 保持 0.9（或 1.0）

#### Scenario: New entity with no existing confidence
- **WHEN** 图谱中不存在该实体（MERGE 创建新节点）
- **THEN** confidence 使用新写入的值

### Requirement: Relation confidence uses max on merge

当通过 `RELATION_SAVE` Cypher 写入关系时，confidence 字段 SHALL 取已有值与新值的较大者。

#### Scenario: New relation with higher confidence
- **WHEN** 图谱中已有关系 confidence=0.6，新萃取写入同一关系 confidence=0.85
- **THEN** 最终 confidence 为 0.85

#### Scenario: New relation with lower confidence
- **WHEN** 图谱中已有关系 confidence=0.9，新萃取写入同一关系 confidence=0.4
- **THEN** 最终 confidence 保持 0.9

### Requirement: Statement confidence uses max on merge

当通过 `STATEMENT_SAVE` Cypher 写入陈述时，confidence 字段 SHALL 取已有值与新值的较大者。

#### Scenario: Statement confidence not degraded
- **WHEN** 图谱中已有陈述 confidence=0.8，新写入同一陈述 confidence=0.5
- **THEN** 最终 confidence 保持 0.8
