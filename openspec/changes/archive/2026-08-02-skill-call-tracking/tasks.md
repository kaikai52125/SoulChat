## 1. 数据模型

- [ ] 1.1 Skill 模型加 `success_count`、`error_count`、`last_called_at` 字段
- [ ] 1.2 alembic migration：`alembic revision --autogenerate -m "skill add success_count error_count last_called_at"`
- [ ] 1.3 SkillRepository：`bump_call_count` 升级为 `record_call(skill_id, success)` 原子更新四个字段

## 2. 埋点接通

- [ ] 2.1 persona_agent.py：传入真实 `record_call` 回调（关联 session 和 skill_id）
- [ ] 2.2 bash_tool.py：`_find_skill_dir` 返回 `(skill_dir, skill_id)` tuple
- [ ] 2.3 bash_tool.py：`_run` 执行后根据 returncode 调 `record_call`（需要异步 session）

## 3. API 层

- [ ] 3.1 skill_service.py `to_out_dict` 暴露 `success_count`、`error_count`、`last_called_at`
- [ ] 3.2 skill_schema.py `SkillOut` 补上 `call_count`（已有但 schema 漏了）

## 4. 前端

- [ ] 4.1 PersonaEditModal.tsx：技能行展示 `成功 N · 失败 N · 最近 Xh前`（仅 call_count > 0 时）
- [ ] 4.2 chat.ts skills 类型加新字段

## 5. 验证

- [ ] 5.1 单聊：给角色配 stock-analysis skill → 发一条分析股票的消息 → 查 API 返回的 call_count > 0
- [ ] 5.2 群聊任务模式：给角色配 skill → 发任务 → bash 执行后 call_count +1，success_count/error_count 正确
- [ ] 5.3 PersonaEditModal 技能列表展示统计数据
- [ ] 5.4 `cd api && uv run ruff check .` 无新增 lint 错误
