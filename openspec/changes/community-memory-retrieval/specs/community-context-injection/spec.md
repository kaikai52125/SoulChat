## ADDED Requirements

### Requirement: Community summary in active recall context
`recall_context` SHALL 在命中实体的社区摘要满足条件时，注入"相关主题"背景块。

#### Scenario: Community block injected when threshold met
- **WHEN** 向量召回命中实体中，≥ 2 个实体属于同一社区
- **THEN** 系统 SHALL 在上下文开头（Insight 块之前）注入"相关主题："块
- **THEN** 每个相关社区 SHALL 格式化为 `· {name}：{summary}`
- **THEN** 同一社区去重（多个实体命中同一社区只注入一次）

#### Scenario: Threshold not met skips injection
- **WHEN** 向量召回命中实体中，每个社区仅被 ≤ 1 个实体命中
- **THEN** 系统 SHALL NOT 注入社区摘要块
- **THEN** 召回其他部分（Insight + 记忆实体）SHALL 正常产出

#### Scenario: Community recall failure does not block recall
- **WHEN** 社区摘要查询失败（超时、索引异常）
- **THEN** 系统 SHALL 降级跳过社区块，继续产出 Insight + 记忆实体
- **THEN** 日志 SHALL 记录降级原因（warning 级别）

### Requirement: Community context in formatted memory context
`format_memory_context` SHALL 可选输出社区标注。

#### Scenario: Memory context includes community label
- **WHEN** `search_memory` 结果包含 `community` 字段且不为 null
- **THEN** `format_memory_context` 输出 SHALL 在实体行之前插入 `【{community.name}】` 标注行
- **THEN** 同一社区多实体时 SHALL 合并为一个社区标注（不重复输出）
- **THEN** 无社区实体 SHALL 不显示社区标注行
