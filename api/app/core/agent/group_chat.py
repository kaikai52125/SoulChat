"""群聊编排：双模式——社交（多角色按主持人调度依次发言）+ 任务协作（Orchestrator-Worker 并行）。

社交模式（_run_social_mode / 当前默认）：
- 上下文用「文本 transcript」承载多方对话——每条消息带发言人前缀（【用户】/【角色名】），
  因为对某个角色而言，别人说的话既非自己（不能当 AIMessage）也非用户（不能当 HumanMessage），
  统一作为场景信息整段呈现最稳定。
- 每轮先调一次主持人 LLM 决定发言顺序（@ 指定时跳过主持人）。
- 角色依次发言，transcript 在一轮内动态累加，使后发言的角色能看到先发言角色刚说的话（接话）。
- 群聊不接工具、不做记忆萃取，纯人设对话。

任务协作模式（_run_task_mode / 新增）：
- Orchestrator 将用户任务分解为子任务 DAG。
- 按拓扑分层并行执行，每个角色用自己的 system_prompt 独立推理。
- SharedBlackboard 替代纯文本 transcript 成为角色间通信的核心数据结构。
- 最终产出经 Verifier 审查（可选）。
"""
from collections.abc import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.agent.blackboard import SharedBlackboard
from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.agent.task_orchestrator import TaskOrchestrator
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

# transcript 截断：最近多少条消息参与上下文（越短首字越快、越省 token）
MAX_TRANSCRIPT_MESSAGES = 18
# 单个角色人设简介（喂主持人用）截断长度
BRIEF_MAX_CHARS = 80
# 主持人最多看的近期消息条数
HOST_RECENT_MESSAGES = 8


def build_transcript(history: list[dict], limit: int = MAX_TRANSCRIPT_MESSAGES) -> str:
    """把多方历史消息渲染成带发言人前缀的文本 transcript。

    history 元素：{role, content, sender_name}（user 消息 sender_name 为「用户」）。
    """
    rows = history[-limit:] if limit else history
    lines: list[str] = []
    for m in rows:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        speaker = m.get("sender_name") or ("用户" if m.get("role") == "user" else "助手")
        lines.append(f"【{speaker}】{content}")
    return "\n".join(lines)


def _persona_brief(system_prompt: str) -> str:
    """从角色人设提取简介（喂主持人判断用），截断避免过长。"""
    text = (system_prompt or "").strip().replace("\n", " ")
    if len(text) > BRIEF_MAX_CHARS:
        text = text[:BRIEF_MAX_CHARS] + "…"
    return text or "（无特别设定）"


async def decide_speakers(
    host_model: ChatOpenAI,
    members: list[dict],
    transcript: str,
    user_text: str,
) -> list[str]:
    """主持人 LLM 决定本轮发言顺序，返回角色名列表。

    - 返回非空列表：这些角色按序发言。
    - 返回空列表：本轮 AI 不接话（如真人之间在互相聊天，无需 AI 插嘴）。
    - 解析失败/异常：兜底返回全体成员，保证对话不中断。
    members 元素：{id, name, system_prompt}。
    """
    member_names = [m["name"] for m in members]
    try:
        brief_members = [
            {"name": m["name"], "brief": _persona_brief(m.get("system_prompt", ""))}
            for m in members
        ]
        # 只给主持人看最近若干条，判断「该谁接话」足够
        recent = "\n".join(transcript.split("\n")[-HOST_RECENT_MESSAGES:])
        prompt = render_agent_prompt(
            "group_host.jinja2",
            members=brief_members,
            transcript=recent or "（暂无历史）",
            user_text=user_text,
        )
        resp = await host_model.ainvoke([HumanMessage(content=prompt)])
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        data = parse_json_object(content)
        speakers = data.get("speakers")
        # 字段缺失（解析失败）→ 兜底全员，保证对话不中断
        if speakers is None:
            return member_names
        # 过滤非法名字、去重保序；显式空列表表示「本轮 AI 不接话」，直接返回空
        valid: list[str] = []
        seen: set[str] = set()
        for name in speakers:
            if name in member_names and name not in seen:
                valid.append(name)
                seen.add(name)
        return valid
    except Exception as e:
        logger.warning("群聊主持人调度失败，回退全员发言: %s", e)
    return member_names


def build_speaker_messages(
    persona_prompt: str,
    self_name: str,
    member_names: list[str],
    transcript: str,
    with_tool_hint: bool = False,
    human_mode: bool = False,
) -> list:
    """构造某角色发言的 LLM 消息：人设 + 群聊场景说明 + 当前 transcript。

    with_tool_hint：群聊开了工具时传 True，附带"时效问题应联网"的引导。
    human_mode：该角色开了真人模式时叠加「真人聊天风格」段（口语短句、可多气泡）。
    """
    system = render_agent_prompt(
        "group_speaker.jinja2",
        persona_prompt=(persona_prompt or "").strip(),
        self_name=self_name,
        member_names="、".join(member_names),
        transcript=transcript or "（暂无历史）",
        human_mode=human_mode,
    )
    # 注入当前日期，让角色知道"今天"是哪天（开工具时对时效问题才会联网）
    from app.core.agent.context_hint import current_context_block

    system = system + "\n\n" + current_context_block(with_tool_hint=with_tool_hint)
    if human_mode:
        system = system + "\n\n" + render_agent_prompt("human_style.jinja2")
    return [SystemMessage(content=system)]


async def stream_speaker(
    model: ChatOpenAI,
    persona_prompt: str,
    self_name: str,
    member_names: list[str],
    transcript: str,
    human_mode: bool = False,
) -> AsyncGenerator[str, None]:
    """流式产出某角色的发言 token。"""
    messages = build_speaker_messages(
        persona_prompt, self_name, member_names, transcript, human_mode=human_mode
    )
    # 追加一条 user 轮次提示：部分 provider（智谱/通义等）不接受「只有 system、无 user」
    # 的消息数组（报 messages 参数非法），故显式补一条用户消息触发本角色发言。
    messages = [
        *messages,
        HumanMessage(
            content=f"现在轮到你「{self_name}」发言，请基于上面的群聊记录自然接话。"
        ),
    ]
    async for chunk in model.astream(messages):
        if chunk.content:
            text = (
                chunk.content
                if isinstance(chunk.content, str)
                else str(chunk.content)
            )
            yield text


def parse_mention(user_text: str, member_names: list[str]) -> str | None:
    """解析用户消息里的 @某角色，命中则返回角色名（跳过主持人，只让他回）。"""
    text = user_text or ""
    if "@" not in text:
        return None
    for name in member_names:
        if f"@{name}" in text:
            return name
    return None


# ── 任务协作模式 ──────────────────────────────────────────────


async def _run_task_mode(
    user_message: str,
    members: list[dict],
    history: list[dict],
    model: ChatOpenAI,
    tools: list | None = None,
) -> AsyncGenerator[dict, None]:
    """任务协作模式：Orchestrator 分解 → 并行执行 → 汇总 → (Verifier)。

    产出事件流（与 run_group_chat 的格式一致）：
    - {"type": "task_plan", "goal": str, "subtasks": list}
    - {"type": "subtask_start", "subtask_id": str, "persona": str}
    - {"type": "subtask_done", "subtask_id": str, "persona": str}
    - {"type": "synthesize_start"}
    - {"type": "token", "text": str}
    - {"type": "final", "text": str}

    Args:
        user_message: 用户发送的任务描述
        members: 群组成员列表 [{id, name, system_prompt, ...}]
        history: 群聊历史消息
        model: 语言模型
    """
    blackboard = SharedBlackboard()
    orchestrator = TaskOrchestrator(model, tools=tools)

    print(f"\n{'>>' * 35}", flush=True)
    print(f"[TASK-MODE] 进入任务协作模式 _run_task_mode", flush=True)
    print(f"   用户消息: {user_message[:100]}", flush=True)
    print(f"   成员: {[m['name'] for m in members]}", flush=True)
    print(f"{'>>' * 35}\n", flush=True)

    # 成员能力摘要
    member_capabilities = [
        {"name": m["name"], "brief": _persona_brief(m.get("system_prompt", ""))}
        for m in members
    ]

    # Step 1: 分解
    try:
        plan = await orchestrator.decompose(user_message, member_capabilities)
        yield {
            "type": "task_plan",
            "goal": plan.goal,
            "subtasks": [st.model_dump() for st in plan.subtasks],
        }
    except ValueError as e:
        # 降级：第一个成员直接回答
        logger.warning("任务分解失败，降级为单角色回答: %s", e)
        yield {"type": "task_plan", "goal": user_message, "subtasks": []}
        try:
            transcript = _build_transcript_from_history(history)
            sys_prompt = members[0].get("system_prompt", "你是一个助手。")
            messages = [
                SystemMessage(content=sys_prompt),
                HumanMessage(
                    content=(
                        f"用户的需求：{user_message}\n\n"
                        f"对话历史：{transcript}\n\n"
                        f"请直接回答用户的问题。"
                    )
                ),
            ]
            resp = await model.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            yield {"type": "token", "text": text}
            yield {"type": "final", "text": text.strip()}
        except Exception as e2:
            yield {"type": "final", "text": f"（任务协作执行失败：{e2}）"}
        return

    # Step 2: 执行（yield 所有 subtask_start 后，每个 subtask 完成即刻 yield done）
    for st in plan.subtasks:
        yield {"type": "subtask_start", "subtask_id": st.id, "persona": st.assigned_persona}
    async for done_event in orchestrator.execute_stream(plan, blackboard, members):
        yield done_event

    # Step 3: 汇总
    yield {"type": "synthesize_start", "flush": True}
    print(f"\n[SYNTH] 开始汇总 synthesize...", flush=True)
    try:
        output = await orchestrator.synthesize(blackboard, task_goal=plan.goal)
    except Exception as e:
        logger.warning("汇总产出失败: %s", e)
        output = f"（任务协作完成，但汇总失败：{e}）"
        print(f"❌ synthesize 异常: {e}", flush=True)

    print(f"📤 产出 final 事件, 文本长度={len(output)}", flush=True)
    yield {"type": "final", "text": output or "（空结果）"}


def _build_transcript_from_history(history: list[dict]) -> str:
    """从历史消息列表构建纯文本 transcript（用于任务模式的降级路径）。"""
    rows = history[-MAX_TRANSCRIPT_MESSAGES:] if history else []
    lines: list[str] = []
    for m in rows:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        speaker = m.get("sender_name") or ("用户" if m.get("role") == "user" else "助手")
        lines.append(f"【{speaker}】{content}")
    return "\n".join(lines)


# ── 双模式入口 ─────────────────────────────────────────────────


async def run_group_chat(
    user_message: str,
    members: list[dict],
    history: list[dict],
    model: ChatOpenAI,
    mode: str = "social",
    tools: list | None = None,
) -> AsyncGenerator[dict, None]:
    """群聊双模式入口。

    根据 mode 参数路由到社交模式或任务协作模式。

    Args:
        user_message: 用户发送的消息
        members: 群组成员列表 [{id, name, system_prompt, ...}]
        history: 群聊历史消息
        model: 语言模型
        mode: "social"（社交对话）或 "task"（任务协作），默认 "social"

    社交模式下，调用方需自行处理 speaker 调度与消息落库；
    任务协作模式下，产出编排好的协作结果。
    """
    if mode == "task":
        async for event in _run_task_mode(user_message, members, history, model, tools=tools):
            yield event
    else:
        # 社交模式：保持完全兼容
        # 调用方（stream_group_chat）直接使用现有的 inline 逻辑
        # 这里作为一个占位路由，实际的社交逻辑仍在 group_chat_service 中
        return


__all__ = [
    "MAX_TRANSCRIPT_MESSAGES",
    "build_transcript",
    "decide_speakers",
    "stream_speaker",
    "parse_mention",
    "run_group_chat",
    "_run_task_mode",
]
