# reflection-contradiction-detection

## Purpose

Memory conflict resolution capability: 

## ADDED Requirements

### Requirement: Reflection prompt includes contradiction detection

反思引擎的 LLM 提示词 SHALL 包含矛盾检测指令，要求 LLM 在输出中新增 `contradictions` 数组，识别记忆清单中的互斥矛盾和随时间变迁的更新。

#### Scenario: LLM identifies time-based update
- **WHEN** 记忆清单包含"用户在学 Java"（旧）和"用户最近在学 Rust"（新）
- **THEN** LLM 输出 contradictions 中包含 type="update"、resolved=true 的条目

#### Scenario: LLM identifies genuine conflict
- **WHEN** 记忆清单包含"用户在腾讯工作"和"用户在字节工作"，且无法从时间推断哪个更新
- **THEN** LLM 输出 contradictions 中包含 type="conflict"、resolved=false 的条目

### Requirement: Auto-resolve resolved contradictions

反思引擎 SHALL 对 `resolved=true` 的矛盾自动执行修复：连接 SUPERSEDES 边并设置旧事实的 invalid_at。

#### Scenario: Time-based update auto-resolved
- **WHEN** contradictions 中有一条 type="update"、resolved=true 的条目
- **THEN** 反思引擎自动调用 `mark_relation_superseded()` 标记旧关系

### Requirement: Push unresolved contradictions to review

反思引擎 SHALL 对 `resolved=false` 的矛盾事实降低其 confidence（乘以 0.7），使其出现在人类审查队列中。

#### Scenario: Conflict pushed to human review
- **WHEN** contradictions 中有一条 type="conflict"、resolved=false 的条目
- **THEN** 相关实体的 confidence 降低，在审查 UI 中显示为待确认
