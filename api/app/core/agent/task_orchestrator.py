"""Task Orchestrator: Agent 驱动的任务编排器。

三个核心方法都是 Agent —— 通过 function calling 可调用 datetime/web_search 等工具：
1. decompose()  — Agent 分解任务 → DAG（可查日期、搜信息）
2. execute_stream() — 每个 subtask 角色也是 Agent（可调工具），实时产出执行轨迹
3. synthesize() — Agent 汇总黑板 finding → 最终报告

与裸 LLM 调用的区别：Orchestrator 现在是真正的 Agent，
知道自己能调用哪些工具，会在需要时主动使用。
"""
import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from pydantic import BaseModel

from app.core.agent.blackboard import BlackboardEntry, SharedBlackboard
from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

_SUBTASK_TIMEOUT = 120



def _datetime_context() -> str:
    """返回当前日期时间的上下文提示。"""
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    weekday_cn = ["一", "二", "三", "四", "五", "六", "日"]
    return (
        f"当前时间：{now.strftime('%Y年%m月%d日')} 星期{weekday_cn[now.weekday()]} "
        f"{now.strftime('%H:%M')}（北京时间 UTC+8）"
    )


class Subtask(BaseModel):
    id: str
    description: str
    assigned_persona: str
    dependencies: list[str] = []
    expected_output: str = ""


class TaskPlan(BaseModel):
    goal: str
    subtasks: list[Subtask]


class TaskOrchestrator:
    """Agent 驱动的任务编排器。"""

    def __init__(
        self,
        model: ChatOpenAI,
        tools: list | None = None,
        session: object = None,
        owner_id: object = None,
    ) -> None:
        self.model = model
        self.tools = tools or []
        self.session = session  # AsyncSession，Worker 构建自己的 tools 用
        self.owner_id = owner_id  # 群主 user_id

    # ═══════════════════════════════════════════════════════════════
    # 核心方法：全部走 Agent 循环
    # ═══════════════════════════════════════════════════════════════

    async def decompose(
        self, user_message: str, member_capabilities: list[dict[str, str]],
    ) -> TaskPlan:
        """Agent 模式分解任务（可调 datetime/web_search 等工具）。"""
        prompt = render_agent_prompt(
            "task_orchestrator.jinja2",
            user_message=user_message,
            members=member_capabilities,
        )
        prompt = f"{_datetime_context()}\n\n{prompt}"
        try:
            print(f"\n{'─' * 50}", flush=True)
            print(f"[DECOMPOSE] decompose Agent 启动, 成员: {[m['name'] for m in member_capabilities]}, 工具: {len(self.tools)}个", flush=True)
            full_text = await self._run_agent([HumanMessage(content=prompt)], label="Orchestrator.decompose")
            data = parse_json_object(full_text)
            if not data:
                raise ValueError("Agent 返回空内容")
            print(f"[PLAN] decompose: goal={data.get('goal', '?')[:60]}", flush=True)
            for st in data.get("subtasks", []):
                print(f"   ↳ {st.get('id', '?')}: {st.get('description', '?')[:50]} → {st.get('assigned_persona', '?')}", flush=True)
            print(f"{'─' * 50}\n", flush=True)
        except Exception as e:
            logger.warning("任务分解失败: %s", e)
            raise ValueError(f"任务分解失败: {e}") from e

        goal = data.get("goal", user_message[:200])
        subtasks_raw = data.get("subtasks", [])
        if not subtasks_raw:
            subtasks = [
                Subtask(
                    id="subtask_1",
                    description=f"全面回答：{user_message}",
                    assigned_persona=member_capabilities[0]["name"],
                    dependencies=[],
                    expected_output=f"对「{user_message}」的完整回答",
                )
            ]
        else:
            subtasks = [
                Subtask(
                    id=s.get("id", f"subtask_{i + 1}"),
                    description=s.get("description", ""),
                    assigned_persona=s.get("assigned_persona", member_capabilities[0]["name"]),
                    dependencies=s.get("dependencies", []),
                    expected_output=s.get("expected_output", ""),
                )
                for i, s in enumerate(subtasks_raw)
            ]
        return TaskPlan(goal=goal, subtasks=subtasks)

    async def execute_stream(
        self, plan: TaskPlan, blackboard: SharedBlackboard,
        group_members: list[dict[str, Any]],
    ) -> AsyncGenerator[dict, None]:
        """并行执行子任务——每个 subtask 角色都是 Agent，实时产出执行轨迹。

        事件类型：
        - subtask_start: Worker 开始执行
        - subtask_tool_start: Worker 调了一个工具
        - subtask_tool_result: 工具调用完成
        - subtask_done: Worker 完成（含结果文本）
        """
        t_exec_start = time.perf_counter()
        name_to_member = {m["name"]: m for m in group_members}

        blackboard.post(BlackboardEntry(type="task", author="orchestrator", content=plan.goal))
        for st in plan.subtasks:
            blackboard.post(BlackboardEntry(
                type="subtask", author="orchestrator",
                content=f"{st.id}: {st.description} -> {st.assigned_persona}",
            ))

        layers = self._topological_layers(plan.subtasks)

        print(f"\n{'═' * 70}", flush=True)
        print(f"[START] TaskOrchestrator 开始执行", flush=True)
        print(f"   目标: {plan.goal}", flush=True)
        print(f"   子任务: {len(plan.subtasks)} 个, 分 {len(layers)} 层, 工具: {len(self.tools)}个", flush=True)
        for i, layer in enumerate(layers):
            names = ", ".join(f"{s.id}[{s.assigned_persona}]" for s in layer)
            print(f"   层{i + 1}: {names} {'||并行' if len(layer) > 1 else '串行(单任务)'}", flush=True)
        print(f"{'═' * 70}\n", flush=True)

        results: dict[str, str] = {}

        for layer_idx, layer in enumerate(layers):
            t_layer_start = time.perf_counter()
            layer_ids = [s.id for s in layer]

            print(f"--- 层 {layer_idx + 1}/{len(layers)} 开始 [{time.strftime('%H:%M:%S')}] ---", flush=True)
            if len(layer) > 1:
                print(f"  || {len(layer)} 个子任务并行执行: {layer_ids}", flush=True)

            # ── asyncio.Queue 汇聚并行 Worker 的事件 ──
            events_q: asyncio.Queue[dict] = asyncio.Queue()

            async def _run_one(st: Subtask) -> None:
                t_start = time.perf_counter()
                persona = name_to_member.get(st.assigned_persona)
                if persona is None:
                    await events_q.put({
                        "type": "subtask_done", "subtask_id": st.id,
                        "persona": st.assigned_persona,
                        "status": "error", "elapsed_ms": 0,
                        "error": f"未找到角色「{st.assigned_persona}」",
                    })

                    return

                print(f"  >> {st.id} ({st.assigned_persona}) 启动", flush=True)
                await events_q.put({
                    "type": "subtask_start",
                    "subtask_id": st.id,
                    "persona": st.assigned_persona,
                })

                # ── 构建该角色的完整 Agent（与单聊一致）──
                try:
                    from app.core.agent.persona_agent import build_persona_agent
                    import uuid as _uuid
                    worker = await build_persona_agent(
                        self.session, _uuid.UUID(persona.get("id", "")), self.owner_id,
                    )
                    if worker is None:
                        raise ValueError(f"角色 {st.assigned_persona} 不存在")
                    worker_model = worker.model
                    worker_tools = worker.tools
                    worker_system_prompt = worker.system_prompt
                    print(f"[TASK-WORKER] {st.assigned_persona}: tools={[t.name for t in worker_tools]} has_skill={'stock' in worker_system_prompt.lower()} has_skill_load={'skill_load' in [t.name for t in worker_tools]}", flush=True)
                except Exception as e:
                    logger.warning("构建 Worker Agent 失败: %s err=%s", st.assigned_persona, e)
                    print(f"[TASK-WORKER] {st.assigned_persona}: FALLBACK to orchestrator tools! err={e}", flush=True)
                    worker_model = self.model
                    worker_tools = self.tools
                    worker_system_prompt = persona.get("system_prompt", "") or "你是一个助手。"

                context = blackboard.get_context_for(st.assigned_persona)
                task_prompt = (
                    f"团队总目标：{plan.goal}\n\n"
                    f"你在协作任务中承担的角色：{st.description}\n\n"
                    f"预期产出：{st.expected_output}\n\n"
                    f"当前黑板内容：\n{context}"
                )
                messages = [
                    SystemMessage(content=worker_system_prompt),
                    SystemMessage(content=task_prompt),
                    HumanMessage(content=(
                        f"你的唯一任务是：「{st.description}」\n\n"
                        f"团队总目标是：「{plan.goal}」\n\n"
                        f"重要规则：\n"
                        f"1. 如果你的系统提示中包含操作步骤和脚本路径，必须使用 bash "
                        f"工具按步骤执行脚本，不要跳过直接回答\n"
                        f"2. 只完成上面这个任务，不要涉及其他领域或其他角色的工作\n"
                        f"3. 如有其他领域的信息需要补充，会有其他角色负责\n"
                        f"4. 请聚焦输出你的发现或分析"
                    )),
                ]

                # ── 工具回调：实时推送事件到队列 ──
                def _on_tool_ev(ev: dict) -> None:
                    events_q.put_nowait({
                        "type": f"subtask_{ev['type']}",  # subtask_tool_start / subtask_tool_result
                        "subtask_id": st.id,
                        "persona": st.assigned_persona,
                        "tool": ev.get("tool", "?"),
                        "query": ev.get("query", ""),
                        "status": ev.get("status"),
                        "latency_ms": ev.get("latency_ms"),
                    })

                try:
                    # 切换上下文：让 Worker 的 skill_load/bash_tool 感知到当前角色
                    from app.core.agent.tools.builtin.persona_memory import (
                        set_current_persona, get_current_persona_id,
                    )
                    prev_pid = get_current_persona_id()
                    pid_str = persona.get("id")
                    if pid_str is not None:
                        set_current_persona(str(pid_str))
                    try:
                        result_text = await asyncio.wait_for(
                            self._run_agent(
                                messages, model=worker_model, tools=worker_tools,
                                label=f"Worker.{st.assigned_persona}",
                                tool_events=_on_tool_ev,
                            ),
                            timeout=_SUBTASK_TIMEOUT,
                        )
                    finally:
                        set_current_persona(prev_pid)
                except asyncio.TimeoutError:
                    result_text = "执行超时"
                    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                    blackboard.post(BlackboardEntry(type="finding", author=st.assigned_persona, content=result_text))
                    await events_q.put({
                        "type": "subtask_done", "subtask_id": st.id,
                        "persona": st.assigned_persona, "status": "error",
                        "elapsed_ms": elapsed_ms, "error": "超时",
                    })

                    return
                except Exception as e:
                    result_text = f"执行失败：{e}"
                    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                    blackboard.post(BlackboardEntry(type="finding", author=st.assigned_persona, content=result_text))
                    await events_q.put({
                        "type": "subtask_done", "subtask_id": st.id,
                        "persona": st.assigned_persona, "status": "error",
                        "elapsed_ms": elapsed_ms, "error": str(e),
                    })

                    return

                elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                print(f"  V {st.id} ({st.assigned_persona}) 完成 ({elapsed_ms}ms)", flush=True)
                blackboard.post(BlackboardEntry(type="finding", author=st.assigned_persona, content=result_text))
                results[st.id] = result_text
                await events_q.put({
                    "type": "subtask_done", "subtask_id": st.id,
                    "persona": st.assigned_persona, "status": "ok",
                    "elapsed_ms": elapsed_ms,
                })
                done_count[0] += 1

            # 启动所有 Worker（并行）
            worker_tasks = [asyncio.ensure_future(_run_one(st)) for st in layer]

            # 主循环：从队列取事件 yield，计数 subtask_done
            done_count = 0
            while done_count < len(layer):
                try:
                    ev = await asyncio.wait_for(events_q.get(), timeout=0.5)
                    yield ev
                    if ev["type"] == "subtask_done":
                        done_count += 1
                except asyncio.TimeoutError:
                    pass

            # 确保所有 task 完成（防御）
            await asyncio.gather(*worker_tasks, return_exceptions=True)

            t_layer_elapsed = time.perf_counter() - t_layer_start
            print(f"--- 层 {layer_idx + 1}/{len(layers)} 完成 ({t_layer_elapsed:.1f}s) ---", flush=True)

        t_exec_total = time.perf_counter() - t_exec_start
        print(f"OK 全部完成: {len(results)}/{len(plan.subtasks)} 成功 ({t_exec_total:.1f}s)\n", flush=True)
        self._last_results = results

    async def synthesize(self, blackboard: SharedBlackboard, task_goal: str = "") -> str:
        """Agent 模式汇总黑板 finding → 最终报告。"""
        findings = blackboard.get_by_type("finding")
        t0 = time.perf_counter()
        total_chars = sum(len(e.content) for e in findings)
        print(f"\n[SYNTH] synthesize Agent 启动: {len(findings)} 个 finding, 共 {total_chars} 字符", flush=True)
        if not findings:
            return "（无协作产出可供汇总）"

        prompt = render_agent_prompt(
            "blackboard_summarizer.jinja2",
            task_goal=task_goal or "协作任务",
            findings=[{"author": e.author, "type": e.type, "content": e.content} for e in findings],
        )
        prompt = f"{_datetime_context()}\n\n{prompt}"
        print(f"   prompt: {len(prompt)} 字符", flush=True)

        try:
            # synthesize 不走工具循环——纯汇总，避免迭代被工具消耗导致空返回
            result = await asyncio.wait_for(
                self._run_agent([HumanMessage(content=prompt)], tools=[], label="Orchestrator.synthesize"),
                timeout=120,
            )
            print(f"   OK synthesize 完成 ({time.perf_counter() - t0:.1f}s), {len(result)} 字符", flush=True)
            return result.strip()
        except asyncio.TimeoutError:
            print(f"   [TIMEOUT] synthesize 超时!", flush=True)
            logger.warning("汇总产出超时")
            return "\n\n".join(f"## {e.author}\n{e.content[:500]}" for e in findings)
        except Exception as e:
            print(f"   ❌ synthesize 失败: {e}", flush=True)
            logger.warning("汇总产出失败: %s", e)
            return "\n\n".join(f"## {e.author}\n{e.content[:500]}" for e in findings)

    # ═══════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════

    async def _run_agent(
        self, messages: list, model: ChatOpenAI | None = None, tools: list | None = None,
        label: str = "Agent",
        tool_events: object = None,
    ) -> str:
        """运行 function calling Agent，收集最终文本。

        decompose / synthesize / subtask 三个场景共用此方法。
        不传 model/tools 时用 self.model + self.tools（Orchestrator 自身）。

        Args:
            tool_events: 可选回调 callable(ev)，收到 tool_start/tool_result 时调用。
                         用于 execute_stream 实时推送 Worker 的工具调用事件。
        """
        from app.core.agent.orchestrator import run_function_calling

        _model = model or self.model
        _tools = tools if tools is not None else self.tools

        collected = ""
        async for ev in run_function_calling(_model, _tools, messages):
            if ev["type"] == "final":
                collected = ev.get("text", "")  # final 是完整文本，替换而非追加
            elif ev["type"] == "token":
                collected += ev.get("text", "")
            elif ev["type"] in ("tool_start", "tool_result"):
                if tool_events is not None:
                    tool_events(ev)
                elif ev["type"] == "tool_start":
                    tool = ev.get("tool", "?")
                    query = ev.get("query", "")[:60]
                    print(f"     [TOOL] [{label}] 调工具: {tool}({query})", flush=True)
        return collected.strip()

    @staticmethod
    def _topological_layers(subtasks: list[Subtask]) -> list[list[Subtask]]:
        deps: dict[str, set[str]] = {}
        id_to_subtask: dict[str, Subtask] = {}
        all_ids: set[str] = set()
        for s in subtasks:
            all_ids.add(s.id)
            deps[s.id] = set(s.dependencies or [])
            id_to_subtask[s.id] = s

        executed: set[str] = set()
        layers: list[list[Subtask]] = []
        while len(executed) < len(subtasks):
            remaining = all_ids - executed
            ready_ids = [sid for sid in remaining if deps[sid].issubset(executed)]
            if not ready_ids:
                ready_ids = list(remaining)
            executed.update(ready_ids)
            layers.append([id_to_subtask[sid] for sid in ready_ids])
        return layers


__all__ = ["TaskOrchestrator", "TaskPlan", "Subtask"]
