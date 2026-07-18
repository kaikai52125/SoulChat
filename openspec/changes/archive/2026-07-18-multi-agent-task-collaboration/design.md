## Context

当前群聊架构：

```
用户 → Host LLM（decide_speakers）
         ↓
    角色A 发言（看到 transcript）
         ↓
    角色B 发言（看到 transcript + A 的发言）
         ↓
    返回用户
```

这是一个"社交对话模拟器"——角色们不是在协作解决问题，而是在**参与一场由文本驱动的轮流表演**。Transcript 是唯一的共享状态，它是无结构文本，角色从中提取高价值信息效率极低。

任务协作模式需要截然不同的架构：

```
用户 → Orchestrator（任务分解）
         ↓
    ┌─────────────────────────────┐
    │       Shared Blackboard     │
    │  ┌────────────────────────┐ │
    │  │ Task: 写竞品分析报告     │ │
    │  │ Subtask 1: 市场调研 [研究员] │ │
    │  │ Subtask 2: SWOT分析 [分析师]│ │
    │  │ Subtask 3: 报告撰写 [写手]  │ │
    │  │ Comments: [...]          │ │
    │  │ Draft: [...]             │ │
    │  └────────────────────────┘ │
    └─────────────────────────────┘
         ↓              ↓
    角色A(研究员)  角色B(分析师)    并行执行
         ↓              ↓
    写手 ← 汇总前两步结果 → 报告
         ↓
    Verifier 审查 → 修正 → 返回用户
```

**业界参考**：
- SE-Blackboard (IEEE 2026): 共享状态黑板在 50 SWE-bench Lite issues 上 — 信息保真度 +62%，正确文件定位 +27.5pp
- Mycelium (Cisco 2026): Rooms + pgvector/AgensGraph 双索引 + Cognition Engine 协商调解，93% 决策收敛率
- Boss Coordinator: 共享内存总线，4 维"上下文温度"度量，"95% 有效性恢复"

**约束**：
- 保留当前"社交模式"群聊不变（向后兼容）
- 任务模式是**显式激活**的（用户点击"开始任务"或通过 API 参数切换）
- 协作产出必须有 Verifier 审查（确保多角色拼装不会产生级联错误）
- 黑板数据是对话级别的（不跨对话持久化），但最终产出可保存

## Goals / Non-Goals

**Goals:**
- 群聊新增"任务协作模式"，用户可切换
- Orchestrator 将用户的任务分解为子任务，指派给角色组中合适的成员
- 被指派的角色并行执行子任务（读取黑板中的任务定义和依赖角色的输出）
- 共享黑板作为协作的核心数据层（取代纯文本 transcript 的角色间通信）
- 最终产出经过 Verifier 审查（复用现有 Verifier Loop 基础设施）

**Non-Goals:**
- 不修改社交模式群聊的任何行为
- 不做跨对话的持久化黑板（初版黑板生命周期 = 单次任务）
- 不做角色间的自由协商/辩论（那是后续的"协商模式"，本 proposal 聚焦 Orchestrator-Worker 的确定型协作）
- 不做外部角色（非群组成员的角色）动态加入

## Decisions

### 决策 1：双模式架构 —— 社交 vs 任务协作

**选择**：`group_chat.py` 内部按 `mode` 参数路由到不同的处理路径：

```python
async def run_group_chat(group, user_message, history, mode="social"):
    if mode == "social":
        return await _run_social_mode(group, user_message, history)
    elif mode == "task":
        return await _run_task_mode(group, user_message, history)
```

前端在群聊输入框旁加一个模式 toggle 开关（默认"社交"）。

**理由**：两种模式的目标、架构、质量要求完全不同，硬合并到一个模式会同时损害两者。社交模式保持简单（不做重构），任务模式全新实现（一个类 + 黑板数据结构）。

### 决策 2：Shared Blackboard 数据结构

**选择**：Blackboard 是一个结构化的 Pydantic model + 内存 dict：

```python
class BlackboardEntry(BaseModel):
    type: Literal["task", "subtask", "finding", "draft", "comment", "decision"]
    author: str  # persona name 或 "orchestrator" 或 "verifier"
    content: str
    attachments: list[dict] = []  # [{type: "citation", source: "..."}]
    timestamp: str

class SharedBlackboard:
    entries: list[BlackboardEntry]
    
    def post(self, entry: BlackboardEntry): ...
    def get_context_for(self, persona_name: str, max_entries: int = 15) -> str: ...
    def summarize(self) -> str: ...
```

**理由**：类型化的 entry 让黑板上的信息不只是文本，而是有语义标签的结构化记录——角色写入"finding"（研究发现），Orchestrator 写入"task"（任务定义），Verifier 写入"comment"（审查意见）。`get_context_for()` 方法为每个角色提供个性化的黑板视图（按角色过滤 + 全局摘要）。

### 决策 3：Orchestrator 工作流

**选择**：Orchestrator 分三步：

```
Step 1: 任务分解
  Input: 用户消息 + 群组成员能力（persona.system_prompt 摘要）
  Output: {goal, subtasks: [{id, description, assigned_persona, dependencies, expected_output}]}
  Model: 用一个 LLM 调用来分解任务

Step 2: 并行委派
  for subtask in subtasks:  (分层层内并行)
    被指派角色读取黑板 → 独立推理（用 person.system_prompt）→ 写入 finding/draft
  依赖处理：有依赖的 subtask 等依赖完成后再启动

Step 3: 汇总 & 验证
  Orchestrator 读取黑板中的所有 finding → 组装最终产出
  Verifier 审查（复用 rubric）→ 修正 → 返回用户
```

**与 Two-Speed Planner 的关系**：Orchestrator 的任务分解逻辑和 `MicroPlanner` 有概念重叠（都生成子任务 DAG），但粒度不同——Two-Speed Planner 分解的是"工具调用步骤"，Orchestrator 分解的是"角色职责"。初版独立实现，后续可抽象统一的 Planning 接口。

### 决策 4：角色执行子任务的方式

**选择**：被指派角色使用 `agent-as-tool` 的同一执行模式——纯 LLM 推理（不挂工具，不 ReAct loop）。

```
for subtask in ready_subtasks:
    persona = group.get_member(subtask.assigned_persona)
    context = blackboard.get_context_for(persona.name)
    result = await model.ainvoke([
        SystemMessage(persona.system_prompt),
        SystemMessage(f"你在协作任务中的角色：{subtask.description}\n\n当前黑板内容：\n{context}"),
        HumanMessage(subtask.expected_output_prompt)
    ])
    blackboard.post(BlackboardEntry(type="finding", author=persona.name, content=result))
```

**理由**：和 agent-as-tool 的设计一致——专业角色被调动时不需要额外的工具，它的价值在于"用自己独特的人设和知识视角给出判断"。任务分解已经由 Orchestrator 完成，角色只需在自己的专业领域内产出内容。

### 决策 5：现有群聊基础设施的复用

**选择**：
- **Persona Groups** 表 (`persona_groups`) 复用，`member_persona_ids` 字段不变
- **成员能力描述**：复用 persona 的 `system_prompt` 前 200 字作为能力摘要（传给 Orchestrator 用于任务分配）
- **群聊 message 存储**：复用现有的 `group_messages` 表，每条消息额外存 `task_role` 字段（`"orchestrator"` / `"worker"` / `"verifier"` / `"user"`）
- **前端 GroupChatPage**：复用三分之二（消息列表、输入框、成员侧栏），新增右侧黑板面板

## Risks / Trade-offs

- **[角色输出不一致]** 被指派的角色在独立推理时可能产出相互矛盾的结论 → **缓解**：(1) Orchestrator 的汇总步骤负责发现和标记矛盾；(2) Verifier 审查时用 `faithfulness` 维度检查；(3) 这是多视角协作的**天然特征**而非 bug——Orchestrator 的选择是"呈现不同观点"还是"挑选最可靠的一个"取决于任务类型（竞品分析通常呈现多观点，事实性报告挑选最可靠）
- **[延迟]** 角色并行执行 + 汇总 + 验证比单个角色回答慢得多 → **缓解**：(1) 任务模式是可选的（用户显式选择"我需要多角色协作"而非默认启用）；(2) 提示用户等待时间（前端展示黑板状态："研究员正在调研..."）；(3) 简单任务用户不会用协作模式
- **[黑板噪音]** 角色往黑板写入过多无关内容 → **缓解**：(1) `BlackboardEntry.type` 限制和 prompt 指导控制写入质量；(2) `get_context_for()` 取最近 15 条 + 摘要，不会全量回填角色 prompt
- **[级联错误]** Orchestrator 的错误任务分解会导致所有角色的产出跑偏 → **缓解**：(1) Orchestrator 的任务分解只有一级（不做多层嵌套），上限清晰；(2) 用户能在前端看到任务分解结果并人工修正
