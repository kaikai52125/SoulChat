## Why

Skill 表已有 `call_count` 字段、`bump_call_count()` 方法、`skill_executor` 里的 `record_call` 回调钩子——整条链路都写好了，但 `persona_agent.py` 传的是 `record_call=None`，导致调用次数永远为 0。bash 执行路径完全没埋点。技能市场排序、角色详情统计、用户感知全部失效。本次接通已存在的链路并补齐 bash 路径的埋点。

## What Changes

- **接通** `persona_agent.py:102` 的 `record_call` 回调，让 `skill__xxx` 脚本工具的调用次数开始计数
- **新增** `bash_tool.py` 埋点：执行脚本时识别所属 skill，按 returncode 计成功/失败
- **新增** Skill 模型字段：`success_count`、`error_count`、`last_called_at`
- **展示** 前端角色编辑弹窗技能列表显示调用次数/成功/失败/最近调用时间
- **迁移** alembic migration 加新字段 + 现有 `call_count` 默认值 0

## Capabilities

### New Capabilities

- `skill-call-tracking`: 技能调用统计——记录每次技能脚本执行的调用次数、成功/失败数、最近调用时间，并在角色技能列表中展示

### Modified Capabilities

<!-- 无现有 spec 需要修改 -->

## Impact

- 模型变更：`skills` 表加 `success_count`、`error_count`、`last_called_at`
- 后端文件：
  - `api/app/models/skill_model.py` — 加字段
  - `api/app/repositories/skill_repository.py` — `bump_call_count` 升级为 `record_call(skill_id, success)`
  - `api/app/core/agent/persona_agent.py` — 传真实 `record_call` 回调
  - `api/app/core/agent/tools/builtin/bash_tool.py` — `_find_skill_dir` 返回 skill_id + `_run` 埋点
  - `api/app/services/skill_service.py` — `to_out_dict` 暴露新字段
- 前端文件：
  - `web/src/pages/agent/PersonaEditModal.tsx` — 技能行展示统计
