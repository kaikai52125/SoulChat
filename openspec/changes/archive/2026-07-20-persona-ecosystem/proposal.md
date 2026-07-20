## Why

SoulChat 的角色系统（AgentPersona）目前是**完全静态的**——无论用户跟一个角色聊了 1 次还是 100 次，角色的行为、语气、对用户的了解程度毫无变化。角色的 MEMORY.md 完全靠用户手动编辑，角色在对话结束后就"消失"了，用户缺乏持续回来的动力。

同时，优质的人设配置（如内置的"深夜解忧小酒馆""A股投研天团"等场景）无法被社区发现和复用——技能（Skill）已经有了市场，角色市场是自然的下一步。

**核心问题**: 角色是"死的"——没有成长、没有记忆、没有社区。这让 SoulChat 停留在"工具"层面，而非"陪伴"层面。

## What Changes

### 角色成长系统（Persona Growth System）
- **新增**: 每个 (角色, 用户) 对有独立的成长数值——XP、等级(Lv.1~50)、亲密度(0~100)
- **新增**: 每次对话互动自动获得 XP，不同行为有不同 XP 权重（深度对话、记忆复用、情绪正反馈等有加成）
- **新增**: 7 种里程碑事件（初次相遇、深度长谈、记忆突破、情绪峰值、话题专注、连续互动、等级跃升）
- **新增**: 7 个可解锁特质（记忆达人、情绪感知、主动关心、幽默模块、深度洞察、记忆守护、风格镜映）——解锁后注入角色的 system prompt，改变角色行为
- **修改**: chat_service 在每次回答完成后自动记录成长数据

### 角色日记系统（Persona Diary）
- **新增**: 每天 23:00 Celery beat 触发，每个当天有互动的角色生成一篇"日记"
- **新增**: 日记以角色的第一人称视角，用角色的语气风格，写 200~400 字关于今天和用户互动的感受和观察
- **新增**: `/diaries` 页面——按角色筛选、日期分组、已读/未读标记
- **新增**: 首页仪表盘增加"今日日记"未读提醒卡片

### 角色市场（Persona Marketplace）
- **新增**: `/market` 页面——浏览、搜索、筛选社区发布的角色
- **新增**: 角色发布流程——用户可将自己的角色发布到市场（冻结配置快照）
- **新增**: 一键导入——从市场复制角色到自己的角色列表
- **新增**: 评分和评论系统
- **修改**: agent_personas 表加 `cloned_from_id`、`clone_count`、`is_listed` 三列

## Capabilities

### New Capabilities
- `persona-growth`: 角色成长数值追踪（XP/等级/亲密度）、交互后自动记录、等级曲线配置
- `persona-milestones`: 里程碑事件检测与生成，7 种里程碑类型，LLM 生成故事化描述
- `persona-traits`: 可解锁特质系统，特质注入 system prompt 改变角色行为
- `persona-diary`: 每日角色日记自动生成、Celery 定时调度、日记浏览与管理
- `persona-marketplace`: 角色市场的发布/浏览/搜索/导入/评分/评论

### Modified Capabilities
- （无）——所有现有能力保持不变，本 change 纯增量

## Impact

- **数据库**: 新增 5 张表（persona_growth, persona_milestones, persona_diaries, persona_market_listings, persona_market_reviews）；agent_personas 加 3 列
- **API**: 新增 4 个 controller（growth, diary, market, persona 扩展），约 15 个新端点
- **Celery**: 新增 1 个 beat 定时任务（generate_persona_diaries，每日 23:00）
- **chat_service**: 在 `_run_chat_turn_bg()` 末尾新增成长记录调用（~15 行增量改动）
- **前端**: 新增 2 个页面（DiaryPage, MarketPage）、5 个新组件、3 个新 API 模块
- **依赖**: 无新增外部依赖，全部基于现有基础设施（PostgreSQL, Celery, Neo4j, React/Ant Design）
