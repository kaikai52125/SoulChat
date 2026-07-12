## ADDED Requirements

### Requirement: LLM infers temporal validity during triplet extraction

三元组萃取时，LLM SHALL 从陈述句中推断 `valid_at` 和 `invalid_at` 时间戳。当陈述暗示时间范围时（如"最近在学"→ valid_at=当前、invalid_at=NULL；"之前在"→ valid_at=NULL、invalid_at=过去），填入 ISO8601 格式；不确定时填 NULL，禁止凭空编造。

#### Scenario: Statement implies recent start
- **WHEN** 陈述为"用户最近在学 Rust"，dialog_at 为 2025-06-01
- **THEN** 三元组的 valid_at 约为 2025-06-01，invalid_at 为 NULL

#### Scenario: Statement implies past state
- **WHEN** 陈述为"用户之前在腾讯工作"
- **THEN** 三元组的 invalid_at 为过去时间，valid_at 为 NULL

#### Scenario: Statement has no temporal signal
- **WHEN** 陈述为"用户喜欢咖啡"，无时间暗示
- **THEN** valid_at 和 invalid_at 均为 NULL

### Requirement: Retrieval filters by temporal validity

记忆检索时，关系列表 SHALL 按 `invalid_at` 过滤：含有 invalid_at 且 < 当前时间的关系排在列表末尾并标记 `[已过期]`。

#### Scenario: Expired relation marked in context
- **WHEN** 检索到实体有两个 RELATION 边，其中一个 invalid_at 已过期
- **THEN** 过期关系排在未过期关系之后，且文本标记为 `[已过期]`

#### Scenario: Active relations not affected
- **WHEN** 所有检索到的 RELATION 边 invalid_at 均为 NULL 或未来时间
- **THEN** 不添加任何过期标记

### Requirement: Retrieval weights down expired relations

在可靠性评分模式下，含有已过期 invalid_at 的关系 SHALL 将其可靠性分数乘以 0.5 的衰减因子。

#### Scenario: Expired relation has lower reliability
- **WHEN** 两个关系的原始分数相同，但一个已过期
- **THEN** 已过期关系排在未过期关系之后
