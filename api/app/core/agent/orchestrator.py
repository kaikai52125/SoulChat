"""Agent 编排：方案B 双路径工具循环，产出统一事件流。

- 强模型（支持 function calling）：bind_tools + 流式工具循环，原生决定调用哪个工具。
- 弱模型：ToolOrchestrator（prompt 模拟 ReAct），解析 Action/Action Input 手动调工具。

两条路径都产出统一事件 dict：
  {"type": "tool_start", "tool", "query"} /
  {"type": "tool_result", "tool", "query", "status", "text", "stats", "latency_ms"} /
  {"type": "token", "text"} / {"type": "final", "text"}
引用由工具执行时写入外部传入的 citations 列表，编排结束后由调用方读取。

工具统计（命中数 / 实体数 / 网页数 等）由各工具写入 ctx.stats_holder[tool_key]，
本编排器在产 tool_result 事件时读取并附在事件上，前端 chip 副文动态绑定。
"""
import asyncio
import ast
import json
import re
import time
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.agent.dag_executor import DAGExecutor, run_dag_with_events
from app.core.agent.planner import MicroPlanner, PlanError
from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.agent.router import AgentRouter, build_tools_summary
from app.core.agent.tracing import get_tracer
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 5
MAX_TOOL_RESULT_PREVIEW = 600


def _format_observation(observation: object) -> str:
    """把工具返回值格式化为人类与 LLM 都能读的文本。

    设计目标：
    - MCP 工具常返回 ``[{'type': 'text', 'text': '...'}]``（或其字符串形式），
      抽出 text 字段拼接，避免出现一坨 Python 字面量噪声。
    - 普通 dict / list 用 JSON 美化输出，保留结构感。
    - 字符串原样返回；若它本身是 Python 字面量字符串（容器），尝试 literal_eval 后递归格式化。
    - 任意对象优先取 ``text`` 属性（兼容 mcp.types.TextContent 等）。
    """
    # 字符串：先看是不是 Python 字面量序列化的形式（如 "[{'type': 'text', ...}]"）
    if isinstance(observation, str):
        text = observation.strip()
        if text and text[0] in "[{(" and text[-1] in "]})":
            try:
                parsed = ast.literal_eval(text)
                if not isinstance(parsed, str):
                    return _format_observation(parsed)
            except (ValueError, SyntaxError):
                pass
        return text

    # 列表：典型 MCP 多段内容；逐项抽 text，否则降级到 str
    if isinstance(observation, list):
        parts: list[str] = []
        for item in observation:
            if isinstance(item, dict):
                t = item.get("text") if isinstance(item.get("text"), str) else None
                if t is not None:
                    parts.append(t)
                    continue
            attr = getattr(item, "text", None)
            if isinstance(attr, str):
                parts.append(attr)
                continue
            try:
                parts.append(json.dumps(item, ensure_ascii=False, indent=2))
            except (TypeError, ValueError):
                parts.append(str(item))
        return "\n\n".join(p.strip() for p in parts if p)

    # 字典：优先 text 字段，否则 JSON 美化
    if isinstance(observation, dict):
        t = observation.get("text") if isinstance(observation.get("text"), str) else None
        if t is not None:
            return t
        try:
            return json.dumps(observation, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(observation)

    # 其他对象（如 mcp.types.TextContent）：尝试 text 属性
    attr = getattr(observation, "text", None)
    if isinstance(attr, str):
        return attr
    return str(observation)


def _truncate(text: str) -> str:
    """前端展示预览用：截断到 MAX_TOOL_RESULT_PREVIEW 长度。"""
    if len(text) <= MAX_TOOL_RESULT_PREVIEW:
        return text
    return text[:MAX_TOOL_RESULT_PREVIEW].rstrip() + "..."


async def run_function_calling(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """强模型路径：原生 function calling 流式工具循环。"""
    tool_map = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools) if tools else model
    full_text = ""
    stats_holder = stats_holder if stats_holder is not None else {}
    # 同一轮内的工具调用结果缓存：(工具名+参数) 相同则复用上次结果，
    # 不再重复握手+执行（消除模型用相同参数重复调同一工具的浪费）。
    call_cache: dict[str, str] = {}
    # 取真实 model_name 用于成本核算(LangChain ChatOpenAI 的 model_name 字段)
    chat_model_name = getattr(model, "model_name", None) or getattr(model, "model", "chat")
    tracer = get_tracer()

    for iteration in range(MAX_TOOL_ITERATIONS):
        # 每轮 LLM 流式调用包一个 llm_call span,流完后从 usage_metadata 抽 token
        # 抓最后一条 user/tool 消息做请求摘要
        last_msg_text = ""
        for m in reversed(messages):
            content = getattr(m, "content", None)
            if isinstance(content, str) and content:
                last_msg_text = content
                break
        async with tracer.llm_span(
            f"chat:{chat_model_name} (轮 {iteration + 1})",
            model_name=chat_model_name,
            attributes={
                "soulchat.chat.iteration": iteration + 1,
                "soulchat.chat.tools_bound": len(tools),
            },
        ) as lsp:
            lsp.set_payload("messages_count", len(messages))
            if last_msg_text:
                lsp.set_payload("request_summary", last_msg_text[:600])
            gathered = None
            iter_text = ""
            async for chunk in model_with_tools.astream(messages):
                if chunk.content:
                    text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    full_text += text
                    iter_text += text
                    yield {"type": "token", "text": text}
                gathered = chunk if gathered is None else gathered + chunk
            # 抽 token 用量(stream_usage=True 后流尾的 chunk 带 usage_metadata)
            usage = getattr(gathered, "usage_metadata", None) or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
            cached = int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0)
            lsp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=chat_model_name)
            tool_calls = getattr(gathered, "tool_calls", None) or []
            lsp.set_payload("tool_calls_count", len(tool_calls))
            if iter_text:
                lsp.set_payload("response_preview", iter_text[:600])
            elif tool_calls:
                # 没有文本输出但触发了工具:展示工具调用意图
                lsp.set_payload(
                    "response_preview",
                    "(本轮无文字输出,触发工具:" + ", ".join(tc.get("name", "?") for tc in tool_calls[:5]) + ")",
                )

        if not tool_calls:
            # 无工具调用 → 已是最终回答
            yield {"type": "final", "text": full_text}
            return

        # 有工具调用：执行后把结果回灌，继续循环
        messages.append(gathered)

        # Phase 1: 检查所有 tool_calls，区分即时结果与待并行执行
        # result_map: idx -> (observation, status, latency_ms, stats)
        result_map: dict[int, tuple[object, str, int, dict]] = {}
        exec_batch: list[tuple[int, StructuredTool, dict, str, str, str]] = []
        batch_dedup: dict[str, int] = {}  # cache_key -> original batch index

        for i, tc in enumerate(tool_calls):
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            query = args.get("query", "")
            try:
                cache_key = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
            except (TypeError, ValueError):
                cache_key = f"{name}:{args}"
            tool = tool_map.get(name)
            cached_text = call_cache.get(cache_key)
            if cached_text is not None:
                result_map[i] = (cached_text, "success", 0, {})
            elif cache_key in batch_dedup:
                # 本次执行批次内已存在同样工具+参数，不重复执行
                result_map[i] = (cache_key, "dedup", batch_dedup[cache_key], {})
            elif tool is None:
                result_map[i] = (f"未知工具：{name}", "error", 0, {})
            else:
                batch_dedup[cache_key] = i
                exec_batch.append((i, tool, args, cache_key, name, query))

        # Phase 2: 并行执行所有非缓存、非 null、非 dedup 的工具
        if exec_batch:

            async def _exec_one(
                tool: StructuredTool, args: dict, name: str, query: str
            ) -> tuple[object, str, int, dict]:
                t0 = time.monotonic()
                tr = get_tracer()
                async with tr.span(
                    f"工具:{name}",
                    span_type="agent_call" if name.startswith("agent__") else "mcp_call" if "__" in name else "tool_call",
                    attributes={
                        "soulchat.tool.name": name,
                        "soulchat.tool.query": str(query)[:200],
                    },
                ) as tsp:
                    try:
                        observation = await tool.ainvoke(args)
                        status = "success"
                    except Exception as e:
                        observation = f"工具执行失败：{e}"
                        status = "error"
                        tsp.mark_error(str(e))
                    obs_str = str(observation) if observation else ""
                    tsp.set_payload("status", status)
                    tsp.set_payload("output_chars", len(obs_str))
                    if obs_str:
                        tsp.set_payload("output_preview", obs_str[:600])
                    if query:
                        tsp.set_payload("tool_query", str(query)[:300])
                latency_ms = int((time.monotonic() - t0) * 1000)
                stats = stats_holder.pop(name, {}) if stats_holder is not None else {}
                return observation, status, latency_ms, stats

            coros = [
                _exec_one(tool, args, name, query)
                for _, tool, args, _, name, query in exec_batch
            ]
            raw_list = await asyncio.gather(*coros, return_exceptions=True)

            for (idx, _tool, _args, _ck, _name, _query), raw in zip(exec_batch, raw_list):
                if isinstance(raw, Exception):
                    result_map[idx] = (f"工具执行失败：{raw}", "error", 0, {})
                else:
                    result_map[idx] = raw

        # Phase 3: 先 yield 所有 tool_start 事件（通知前端全部已启动）
        for i, tc in enumerate(tool_calls):
            name = tc.get("name", "")
            query = tc.get("args", {}).get("query", "")
            yield {"type": "tool_start", "tool": name, "query": query}

        # Phase 4: 再按原始顺序 yield tool_result + 追加 ToolMessage
        for i, tc in enumerate(tool_calls):
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            query = args.get("query", "")

            if i in result_map:
                observation, status, latency_ms, stats = result_map[i]
            else:
                observation, status, latency_ms, stats = ("工具执行失败：未知错误", "error", 0, {})

            # 处理 dedup 情况：指向同一批次中首次执行的原始索引
            if status == "dedup":
                orig_idx = latency_ms  # latency_ms 字段暂存了原始索引
                if orig_idx in result_map:
                    observation, status, latency_ms, stats = result_map[orig_idx]
                else:
                    observation, status, latency_ms, stats = ("工具执行失败：未知错误", "error", 0, {})

            formatted = _format_observation(observation)
            try:
                cache_key = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
            except (TypeError, ValueError):
                cache_key = f"{name}:{args}"
            if status == "success":
                # dedup 的索引不重复写入缓存（第一次已写）
                call_cache[cache_key] = formatted
            yield {
                "type": "tool_result",
                "tool": name,
                "query": query,
                "status": status,
                "text": _truncate(formatted),
                "stats": stats,
                "latency_ms": latency_ms,
            }
            messages.append(
                ToolMessage(content=formatted, tool_call_id=tc.get("id", name))
            )

    # 达到最大迭代仍未收敛：用现有内容兜底
    yield {"type": "final", "text": full_text or "（未能生成回答）"}


_ACTION_RE = re.compile(r"Action\s*:\s*(.+)")
_ACTION_INPUT_RE = re.compile(r"Action\s*Input\s*:\s*(.+)")
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.*)", re.DOTALL)


async def run_react(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    user_text: str,
    history: list,
    system_prompt: str,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """弱模型路径：prompt 模拟 ReAct，手动解析并调用工具。"""
    tool_map = {t.name: t for t in tools}
    sys = render_agent_prompt(
        "react.jinja2",
        tools=[{"name": t.name, "description": t.description} for t in tools],
        system_prompt=system_prompt,
    )
    convo: list = [SystemMessage(content=sys), *history, HumanMessage(content=user_text)]
    stats_holder = stats_holder if stats_holder is not None else {}
    # 同一轮内工具结果缓存（工具名+query 相同则复用）
    call_cache: dict[str, str] = {}
    # 取真实 model_name 用于 token / cost 记账
    react_model_name = getattr(model, "model_name", None) or getattr(model, "model", "chat")
    tracer = get_tracer()

    for iteration in range(MAX_TOOL_ITERATIONS):
        async with tracer.llm_span(
            f"chat(ReAct):{react_model_name} (轮 {iteration + 1})",
            model_name=react_model_name,
            attributes={
                "soulchat.chat.iteration": iteration + 1,
                "soulchat.chat.mode": "react",
            },
        ) as lsp:
            resp = await model.ainvoke(convo)
            usage = getattr(resp, "usage_metadata", None) or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
            cached = int((usage.get("input_token_details") or {}).get("cache_read", 0) or 0)
            lsp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=react_model_name)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)

        final_match = _FINAL_RE.search(text)
        if final_match:
            answer = final_match.group(1).strip()
            yield {"type": "token", "text": answer}
            yield {"type": "final", "text": answer}
            return

        # 多 Action 解析：re.finditer 提取所有 Action / Action Input 对
        action_matches = list(_ACTION_RE.finditer(text))
        if not action_matches:
            # 没有 Action 也没有 Final，把整段当回答兜底
            yield {"type": "token", "text": text}
            yield {"type": "final", "text": text}
            return

        input_matches = list(_ACTION_INPUT_RE.finditer(text))

        # 按出现顺序配对 Action 和 Action Input
        pairs: list[tuple[str, str]] = []
        for j, am in enumerate(action_matches):
            t_name = am.group(1).strip().splitlines()[0].strip()
            inp_text = (
                input_matches[j].group(1).strip().splitlines()[0].strip()
                if j < len(input_matches)
                else None
            )
            pairs.append((t_name, inp_text or user_text))

        # Phase 1: 检查每个 Action，区分即时结果与待并行执行
        react_result_map: dict[int, tuple[object, str, int, dict]] = {}
        react_exec_batch: list[tuple[int, StructuredTool, str, str]] = []

        for j, (tool_name, query) in enumerate(pairs):
            cache_key = f"{tool_name}:{query}"
            tool = tool_map.get(tool_name)
            cached_text = call_cache.get(cache_key)
            if cached_text is not None:
                react_result_map[j] = (cached_text, "success", 0, {})
            elif tool is None:
                react_result_map[j] = (f"未知工具：{tool_name}", "error", 0, {})
            else:
                react_exec_batch.append((j, tool, tool_name, query))

        # Phase 2: 并行执行
        if react_exec_batch:

            async def _react_exec_one(
                tool: StructuredTool, name: str, query: str
            ) -> tuple[object, str, int, dict]:
                t0 = time.monotonic()
                tr = get_tracer()
                async with tr.span(
                    f"工具:{name}",
                    span_type="agent_call" if name.startswith("agent__") else "mcp_call" if "__" in name else "tool_call",
                    attributes={
                        "soulchat.tool.name": name,
                        "soulchat.tool.query": str(query)[:200],
                    },
                ) as tsp:
                    try:
                        observation = await tool.ainvoke({"query": query})
                        status = "success"
                    except Exception as e:
                        observation = f"工具执行失败：{e}"
                        status = "error"
                        tsp.mark_error(str(e))
                    obs_str = str(observation) if observation else ""
                    tsp.set_payload("status", status)
                    tsp.set_payload("output_chars", len(obs_str))
                    if obs_str:
                        tsp.set_payload("output_preview", obs_str[:600])
                    if query:
                        tsp.set_payload("tool_query", str(query)[:300])
                latency_ms = int((time.monotonic() - t0) * 1000)
                stats = stats_holder.pop(name, {}) if stats_holder is not None else {}
                return observation, status, latency_ms, stats

            coros = [
                _react_exec_one(tool, name, query)
                for _, tool, name, query in react_exec_batch
            ]
            raw_list = await asyncio.gather(*coros, return_exceptions=True)

            for (j, _tool, name, query), raw in zip(react_exec_batch, raw_list):
                if isinstance(raw, Exception):
                    react_result_map[j] = (f"工具执行失败：{raw}", "error", 0, {})
                else:
                    react_result_map[j] = raw

        # Phase 3: 按 pairs 原始顺序 yield 事件 + 收集 observation 用于回灌
        obs_parts: list[str] = []
        for j, (tool_name, query) in enumerate(pairs):
            yield {"type": "tool_start", "tool": tool_name, "query": query}

            observation, status, latency_ms, stats = react_result_map.get(
                j, ("工具执行失败：未知错误", "error", 0, {})
            )
            formatted = _format_observation(observation)
            cache_key = f"{tool_name}:{query}"
            if status == "success":
                call_cache[cache_key] = formatted
            yield {
                "type": "tool_result",
                "tool": tool_name,
                "query": query,
                "status": status,
                "text": _truncate(formatted),
                "stats": stats,
                "latency_ms": latency_ms,
            }
            obs_parts.append(formatted)

        # 把模型上一轮输出 + Observation(s) 回灌
        convo.append(AIMessage(content=text))
        if len(obs_parts) == 1:
            convo.append(HumanMessage(content=f"Observation: {obs_parts[0]}"))
        else:
            merged = "\n".join(
                f"Observation {j + 1}: {part}" for j, part in enumerate(obs_parts)
            )
            convo.append(HumanMessage(content=merged))

    yield {"type": "final", "text": "（多轮工具调用后仍未得到结论）"}


# ── Two-Speed Router 相关函数 ──────────────────────────────────────────


async def stream_plain(
    model: ChatOpenAI,
    messages: list,
) -> AsyncGenerator[dict, None]:
    """纯 LLM 流式输出（不挂工具）。

    适用于 trivial/chat 路由。产出 token / final 事件。
    """
    full_text = ""
    async for chunk in model.astream(messages):
        if chunk.content:
            text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
            full_text += text
            yield {"type": "token", "text": text}
    yield {"type": "final", "text": full_text or "（未生成回答）"}


async def run_two_speed(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
    persona=None,
    router_model: str | None = None,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Two-Speed 编排入口：Router 分类 → 按路由分发。

    路由策略：
    - trivial / chat → stream_plain（纯 LLM，不挂工具）
    - single_tool   → run_function_calling（当前默认行为）
    - multi_step    → MicroPlanner.plan() → DAGExecutor.execute() → 综合

    Router / Planner 异常时自动 fallback 到 run_function_calling()。
    """
    # 从 messages 中提取最后一条 user 消息
    user_message = ""
    for m in reversed(messages):
        if hasattr(m, "content") and isinstance(m.content, str) and m.content:
            user_message = m.content
            break
        if isinstance(m, dict) and m.get("role") == "user":
            user_message = m.get("content", "")
            break

    tools_summary = build_tools_summary(tools)

    # 构建 Router 模型（router_model 为 None 时复用聊天模型）
    router_llm = model
    if router_model:
        try:
            router_llm = ChatOpenAI(
                model=router_model,
                api_key=getattr(model, "openai_api_key", "") or "",
                base_url=(
                    getattr(model, "openai_api_base", "")
                    or getattr(model, "base_url", "")
                    or ""
                ),
                temperature=0.0,
                streaming=False,
            )
        except Exception as e:
            logger.warning("构建 Router 模型失败，复用聊天模型: %s", e)
            router_llm = model

    router = AgentRouter(router_llm)

    # Step 1: Router 分类
    try:
        route_result = await router.classify(user_message, tools_summary)
        route = route_result.route
        logger.info(
            "Two-Speed Router: route=%s confidence=%.2f reason=%s",
            route, route_result.confidence, route_result.reason,
        )
    except Exception as e:
        logger.warning("Router 分类异常，fallback 到 run_function_calling: %s", e)
        route = "single_tool"

    # Step 2: 按路由分发
    if route in ("trivial", "chat"):
        # 纯 LLM 路径：不挂工具
        async for event in stream_plain(model, messages):
            yield event

    elif route == "single_tool":
        # 单工具路径：使用现有 function calling 循环
        async for event in run_function_calling(
            model, tools, messages, stats_holder=stats_holder,
        ):
            yield event

    else:  # multi_step
        # 多步路径：Planner → DAGExecutor → 综合
        try:
            planner = MicroPlanner(model)
            plan = await planner.plan(user_message, tools_summary)

            logger.info(
                "Two-Speed Planner: goal=%s steps=%d",
                plan.goal[:80], len(plan.steps),
            )

            # 使用带事件的 DAG 执行
            async for event in run_dag_with_events(
                DAGExecutor(), plan, model, tools, messages, persona,
            ):
                yield event

            # 综合各步骤结果为最终回答
            # 这里我们直接在 run_dag_with_events 中处理了合成，
            # 但需要从 DAG 结果中构建最终答案
            # 由于 run_dag_with_events yield step_done 而不 yield final，
            # 我们重新运行 DAG 获取结果用于合成
            executor = DAGExecutor()
            step_results = await executor.execute(
                plan, model, tools, messages, persona,
            )

            # 找到综合步（tool_hint=None）或最后一步作为最终回答
            synthesis_steps = [s for s in plan.steps if s.tool_hint is None]
            if synthesis_steps:
                # 综合步已经由 executor 执行并得到结果
                final_step = synthesis_steps[-1]
                final_text = step_results.get(final_step.id, "")
                if final_text:
                    yield {"type": "token", "text": final_text}
                    yield {"type": "final", "text": final_text}
                else:
                    # 如果没有综合步结果，用 executor 的全部结果构建回答
                    assembled = _assemble_dag_results(plan, step_results)
                    yield {"type": "token", "text": assembled}
                    yield {"type": "final", "text": assembled}
            else:
                # 没有综合步，拼接所有结果
                assembled = _assemble_dag_results(plan, step_results)
                yield {"type": "token", "text": assembled}
                yield {"type": "final", "text": assembled}

        except PlanError as e:
            logger.warning("Planner 失败，fallback 到 run_function_calling: %s", e)
            async for event in run_function_calling(
                model, tools, messages, stats_holder=stats_holder,
            ):
                yield event
        except Exception as e:
            logger.warning(
                "multi_step 路径异常，fallback 到 run_function_calling: %s", e,
            )
            async for event in run_function_calling(
                model, tools, messages, stats_holder=stats_holder,
            ):
                yield event


def _assemble_dag_results(plan, step_results: dict[str, str]) -> str:
    """拼接 DAG 执行结果为最终文本（无综合步时的兜底方案）。"""
    parts: list[str] = []
    for s in plan.steps:
        result = step_results.get(s.id, "").strip()
        if result:
            parts.append(f"【{s.description}】\n{result}")
    if parts:
        return "\n\n".join(parts)
    return "（多步执行完成）"


__all__ = [
    "run_function_calling", "run_react", "run_two_speed", "stream_plain",
    "MAX_TOOL_ITERATIONS",
]
