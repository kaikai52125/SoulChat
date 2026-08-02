## Context

`call_count` 字段、`bump_call_count()` 方法、`skill_executor` 的 `record_call` 回调早已存在，但 `persona_agent.py:102` 传入 `record_call=None`，从未被调用。bash 路径完全无埋点。本次主要是**接通**而非新建。

## Goals / Non-Goals

**Goals:**
- 每次通过 `skill__xxx` 工具或 `bash` 执行 skill 脚本时，对应 Skill 的计数 +1
- 区分成功/失败计数
- 记录最近调用时间
- 前端技能列表可见统计

**Non-Goals:**
- 不建 `skill_call_log` 明细表——统计数字足够
- 不新增 API 端点——现有 `GET /personas/{id}/skills` 加字段即可

## Decisions

### 1. 埋点位置

两处：

**skill__xxx 工具（skill_executor）**：`persona_agent.py` 把 `record_call=None` 改成真回调。利用已有的 `_make_tool._run` 钩子（在脚本执行前调 `record_call`）。

**bash 工具**：`_find_skill_dir` 同时返回 `(skill_dir, skill_id)`，`_run` 在执行后根据 `returncode` 调 `record_call(skill_id, success=True/False)`。

### 2. 数据模型

Skill 表加：
```python
call_count: int = 0        # 已有，总调用
success_count: int = 0     # 新增
error_count: int = 0       # 新增
last_called_at: datetime | None = None  # 新增
```

`record_call(skill_id, success)` 原子更新所有四个字段。

### 3. 前端展示

PersonaEditModal 的技能行已有 `调用 {s.call_count} 次`。改为：

```
📊 {s.call_count} 次 · 成功 {s.success_count} · 失败 {s.error_count} · {s.last_called_at 相对时间}
```

仅当 `call_count > 0` 时展示。

## Risks / Trade-offs

- **[风险] 单次 script 执行可能被重复计数**：skill_executor 和 bash 路径互斥（脚本工具通过 skill__xxx 注册，bash 是备选路径），不会双重计数。
  → 但如果同一个脚本被 skill__xxx 和 bash 各调一次，会各计一次——这是正确的，因为两次独立执行。
- **[风险] `last_called_at` 精度**：用 UTC datetime，前端转相对时间（"2小时前"）。无需时区处理。
