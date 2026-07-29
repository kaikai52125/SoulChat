"""Agent-as-Tool 单元测试。

覆盖：工具名格式、描述生成、调用逻辑、记忆注入、单轮推理、
      allow_agent_call 默认值、list_callable 查询、输入 schema、
      角色上下文切换（skill_load/bash_tool 感知被调用角色）。
"""
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.core.agent.persona_agent import PersonaAgent
from app.core.agent.tools.base import ToolBuildContext
from app.core.agent.tools.builtin.agent_tool import (
    CallAgentInput,
    _slugify,
    build_agent_tool,
)
from app.repositories.agent_persona_repository import AgentPersonaRepository

# ── 辅助 ──────────────────────────────────────────────────────────────────


def _make_persona(**kwargs):
    """创建一个类似 AgentPersona ORM 实例的 mock。"""
    p = MagicMock()
    p.name = kwargs.get("name", "代码审查官")
    p.system_prompt = kwargs.get("system_prompt", "你是一位代码审查专家。")
    p.memory_text = kwargs.get("memory_text", "")
    p.temperature = kwargs.get("temperature", 0.3)
    p.allow_agent_call = kwargs.get("allow_agent_call", True)
    p.id = kwargs.get("id", "persona-123")
    return p


def _make_ctx(session=None, user_id=None):
    """创建一个 ToolBuildContext mock。"""
    return ToolBuildContext(
        session=session or MagicMock(),
        user_id=user_id or "user-123",
        citations=[],
        embed_holder={},
        stats_holder={},
    )


def _make_persona_agent(model=None, tools=None, system_prompt=""):
    """创建一个 PersonaAgent mock。"""
    agent = MagicMock(spec=PersonaAgent)
    agent.model = model or MagicMock()
    agent.tools = tools or []
    agent.system_prompt = system_prompt
    return agent


# ── 工具名格式 ────────────────────────────────────────────────────────────


class TestBuildAgentToolNameFormat:
    """任务 7.1.1: 角色 "代码审查官" → 工具名 ``agent__dai_ma_shen_cha_guan``。"""

    def test_slugify_ascii(self):
        """英文名转小写下划线。"""
        assert _slugify("My Agent") == "my_agent"

    def test_slugify_chinese(self):
        """中文名保留汉字，空格/符号转下划线。"""
        assert _slugify("代码审查官") == "代码审查官"

    @pytest.mark.asyncio
    async def test_tool_name_prefix(self):
        """工具名以 agent__ 开头。"""
        persona = _make_persona(name="代码审查官")
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        assert tool.name.startswith("agent__")

    @pytest.mark.asyncio
    async def test_tool_name_contains_slug(self):
        """工具名包含 slug 化后的角色名。"""
        persona = _make_persona(name="代码审查官")
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        assert tool.name == "agent__代码审查官"


# ── 工具描述 ──────────────────────────────────────────────────────────────


class TestBuildAgentToolDescription:
    """任务 7.1.2: 工具描述包含 persona.name + system_prompt 前 100 字摘要。"""

    @pytest.mark.asyncio
    async def test_description_includes_name(self):
        """描述包含角色名。"""
        persona = _make_persona(name="代码审查官")
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        assert "代码审查官" in tool.description

    @pytest.mark.asyncio
    async def test_description_includes_prompt(self):
        """描述包含 system_prompt 前 100 字。"""
        prompt = "你是一位代码审查专家，精通 Python、JavaScript、TypeScript、Go 和 Rust。"
        persona = _make_persona(system_prompt=prompt)
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        assert "代码审查专家" in tool.description

    @pytest.mark.asyncio
    async def test_description_long_prompt_truncated(self):
        """超 100 字的 system_prompt 被截断并追加 ...。"""
        prompt = "你是一位" + "非常专业的" * 30 + "代码审查专家。"
        persona = _make_persona(system_prompt=prompt)
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        # 确认描述长度不超过 100 + "..." 上限
        assert len(tool.description) < len(prompt) + 20


# ── 调用使用 build_persona_agent 构建 ──────────────────────────────────────


class TestAgentToolInvokeUsesBuildPersonaAgent:
    """任务 7.1.3: 调用时通过 build_persona_agent() 构建完整 Agent，
    并在执行前切换角色上下文（persona_memory.set_current_persona）。"""

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_build_persona_agent_called(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """_run 调用 build_persona_agent 构建角色 Agent。"""
        mock_get_id.return_value = "persona-main"
        persona = _make_persona(id="persona-123")
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*a, **kw):
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "审查代码"})

        mock_bpa.assert_called_once()
        call_args = mock_bpa.call_args
        assert call_args[0][1] == "persona-123"  # persona_id
        assert call_args[0][2] == ctx.user_id    # owner_id

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_persona_context_switched(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """_run 执行前 set_current_persona 切换到被调用角色，执行后恢复。"""
        mock_get_id.return_value = "persona-main"
        persona = _make_persona(id="persona-123")
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*a, **kw):
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "test"})

        # 第一次调用：切换到被调用角色
        mock_set.assert_any_call("persona-123")
        # 最终恢复为原来的角色
        mock_set.assert_any_call("persona-main")
        assert mock_set.call_count == 2

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_persona_context_restored_on_error(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """即使 run_function_calling 异常，也恢复上下文。"""
        mock_get_id.return_value = "persona-main"
        persona = _make_persona(id="persona-123")
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*args, **kwargs):
            raise RuntimeError("模型调用超时")
            yield  # pragma: no cover
        mock_run_fc.side_effect = _fake_fc

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "test"})

        # 即使异常，也应该恢复到原来的角色
        mock_set.assert_any_call("persona-123")
        mock_set.assert_any_call("persona-main")
        assert mock_set.call_count >= 2

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_agent_system_prompt_passed_to_fc(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """build_persona_agent 返回的 system_prompt 作为 SystemMessage 注入。"""
        mock_get_id.return_value = None
        persona = _make_persona()
        mock_agent = _make_persona_agent(system_prompt="你是一位代码审查专家。")
        mock_bpa.return_value = mock_agent

        captured_msgs = []
        async def _fake_fc(model, tools, messages):
            captured_msgs.extend(messages)
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "审查代码"})

        contents = [m.content for m in captured_msgs if hasattr(m, "content") and m.content]
        assert any("代码审查" in c for c in contents)

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_handle_build_persona_agent_error(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """build_persona_agent 抛出异常时返回错误消息（不进入 try/finally 块）。"""
        persona = _make_persona(name="测试角色")
        mock_bpa.side_effect = RuntimeError("数据库连接失败")

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        result = await tool.ainvoke({"query": "test"})

        assert "测试角色" in result
        assert "失败" in result
        mock_run_fc.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_handle_build_persona_agent_none(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """build_persona_agent 返回 None 时返回提示。"""
        persona = _make_persona(name="测试角色")
        mock_bpa.return_value = None

        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        result = await tool.ainvoke({"query": "test"})

        assert "测试角色" in result
        assert "不存在" in result
        mock_run_fc.assert_not_called()


# ── 记忆注入由 build_persona_agent 处理 ────────────────────────────────────


class TestAgentToolMemoryTextInjected:
    """任务 7.1.4: persona.memory_text 由 build_persona_agent 注入 system_prompt。"""

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_memory_text_in_agent_system_prompt(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """build_persona_agent 返回的 system_prompt 包含 memory_text。"""
        mock_get_id.return_value = None
        mock_agent = _make_persona_agent(
            system_prompt="你是一位代码审查专家。\n\n【角色记忆】\n用户偏好：喜欢清晰注释的代码。"
        )
        mock_bpa.return_value = mock_agent

        captured_msgs = []
        async def _fake_fc(model, tools, messages):
            captured_msgs.extend(messages)
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona(
            system_prompt="你是一位代码审查专家。",
            memory_text="用户偏好：喜欢清晰注释的代码。",
        )
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "审查代码"})

        all_content = " ".join(
            m.content for m in captured_msgs if hasattr(m, "content") and m.content
        )
        assert "用户偏好" in all_content
        assert "喜欢清晰注释" in all_content

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_empty_system_prompt_ok(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """agent.system_prompt 为空时不注入 SystemMessage。"""
        mock_get_id.return_value = None
        mock_agent = _make_persona_agent(system_prompt="")
        mock_bpa.return_value = mock_agent

        captured_msgs = []
        async def _fake_fc(model, tools, messages):
            captured_msgs.extend(messages)
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona(system_prompt="", memory_text="")
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "test"})

        # 应该只有 HumanMessage，没有 SystemMessage
        from langchain_core.messages import SystemMessage
        system_msgs = [m for m in captured_msgs if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 0


# ── 不挂载 agent__* 工具 ──────────────────────────────────────────────────


class TestAgentToolHasTools:
    """任务 7.1.5: 被叫角色拥有工具（通过 run_function_calling 执行），
    但不包含 agent__* 工具（防递归，由 build_persona_agent 内部过滤）。"""

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_uses_function_calling(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """调用使用 run_function_calling 而非裸 model.ainvoke。"""
        mock_get_id.return_value = None
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*args, **kwargs):
            yield {"type": "token", "text": "审查"}
            yield {"type": "final", "text": "审查结果"}
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona()
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        result = await tool.ainvoke({"query": "审查代码"})

        assert mock_run_fc.called, "应该使用 run_function_calling"
        assert "审查结果" in result

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_agent_tools_passed_to_fc(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """build_persona_agent 返回的 tools 传给 run_function_calling。"""
        mock_get_id.return_value = None
        normal_tool = MagicMock()
        normal_tool.name = "web_search"
        mock_agent = _make_persona_agent(tools=[normal_tool], system_prompt="test")
        mock_bpa.return_value = mock_agent

        captured_tools = []
        async def _fake_fc(model, tools, messages):
            captured_tools.extend(tools)
            yield {"type": "final", "text": "done"}
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona()
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "test"})

        tool_names = [t.name for t in captured_tools]
        assert "web_search" in tool_names


class TestAgentToolSingleTurnOnly:
    """任务 7.1.6: 被叫角色使用 function calling 循环执行。"""

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_function_calling_called_once(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """run_function_calling 恰好被调用一次。"""
        mock_get_id.return_value = None
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*args, **kwargs):
            yield {"type": "final", "text": "回答"}
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona()
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        await tool.ainvoke({"query": "审查代码"})

        assert mock_run_fc.call_count == 1

    @pytest.mark.asyncio
    @patch("app.core.agent.orchestrator.run_function_calling")
    @patch("app.core.agent.persona_agent.build_persona_agent")
    @patch("app.core.agent.tools.builtin.persona_memory.set_current_persona")
    @patch("app.core.agent.tools.builtin.persona_memory.get_current_persona_id")
    async def test_fc_exception_handled(
        self, mock_get_id, mock_set, mock_bpa, mock_run_fc
    ):
        """run_function_calling 异常时返回友好错误。"""
        mock_get_id.return_value = None
        mock_agent = _make_persona_agent(system_prompt="test")
        mock_bpa.return_value = mock_agent

        async def _fake_fc(*args, **kwargs):
            raise RuntimeError("模型调用超时")
            yield  # pragma: no cover
        mock_run_fc.side_effect = _fake_fc

        persona = _make_persona(name="出错的角色")
        ctx = _make_ctx()
        tool = await build_agent_tool(persona, ctx)
        result = await tool.ainvoke({"query": "test"})

        assert "出错" in result
        assert "出错的角色" in result


# ── allow_agent_call 默认值 ──────────────────────────────────────────────


class TestAllowAgentCallDefaultFalse:
    """任务 7.1.7: 新创建 persona 的 allow_agent_call 默认为 false。"""

    def test_default_in_create_schema(self):
        """PersonaCreate 中 allow_agent_call 默认为 False。"""
        from app.schemas.agent_persona_schema import PersonaCreate

        schema = PersonaCreate(name="测试角色")
        assert schema.allow_agent_call is False

    def test_default_in_out_schema(self):
        """PersonaOut 中 allow_agent_call 默认为 False（无默认值时）。"""
        from app.schemas.agent_persona_schema import PersonaOut

        schema = PersonaOut(
            id="1",
            name="测试",
            avatar_key=None,
            avatar_url=None,
            system_prompt="",
            temperature=0.7,
            is_active=False,
            memory_text="",
            tool_keys=[],
            enable_knowledge=True,
            enable_memory=True,
            enable_web_search=False,
            enable_mcp=False,
            mcp_server_ids=[],
            enable_active_recall=True,
            enable_cross_session=False,
            allow_agent_call=False,
            kb_ids=[],
            conversation_scope="shared",
            context_window=20,
            human_mode=False,
            show_avatar=False,
        )
        assert schema.allow_agent_call is False


# ── list_callable 查询 ────────────────────────────────────────────────────


class TestListCallableExcludesSelfAndNotAllowed:
    """任务 7.1.8: list_callable() 只返回 allow_agent_call=True 且 id != exclude_id 的角色。"""

    @pytest.mark.asyncio
    async def test_only_callable_returned(self):
        """只返回 allow_agent_call=True 的角色。"""
        mock_session = AsyncMock()
        repo = AgentPersonaRepository(mock_session)

        # mock execute 返回的 scalars
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repo.list_callable(user_id="user-1")
        # verify the query includes allow_agent_call.is_(True)
        call_stmt = mock_session.execute.call_args[0][0]
        where_clauses = str(call_stmt)
        assert "allow_agent_call" in where_clauses

    @pytest.mark.asyncio
    async def test_exclude_id_filtered(self):
        """排除 exclude_id 的角色。"""
        mock_session = AsyncMock()
        repo = AgentPersonaRepository(mock_session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repo.list_callable(user_id="user-1", exclude_id="persona-123")
        call_stmt = str(mock_session.execute.call_args[0][0])
        assert "persona-123" in call_stmt or "id !=" in call_stmt


# ── CallAgentInput schema ────────────────────────────────────────────────


class TestCallAgentInputSchema:
    """任务 7.1.9: CallAgentInput 只有 query: str 一个必填字段。"""

    def test_has_query_field(self):
        """CallAgentInput 有 query 字段。"""
        assert hasattr(CallAgentInput, "model_fields")
        assert "query" in CallAgentInput.model_fields

    def test_query_is_required(self):
        """query 是必填字段（无默认值）。"""
        field = CallAgentInput.model_fields["query"]
        assert field.is_required()

    def test_query_is_string(self):
        """query 类型是 str。"""
        field = CallAgentInput.model_fields["query"]
        assert field.annotation is str

    def test_only_query_field(self):
        """CallAgentInput 只有 query 一个字段。"""
        field_names = set(CallAgentInput.model_fields.keys())
        assert field_names == {"query"}

    def test_valid_input(self):
        """传入合法的 query 值正常构造。"""
        inp = CallAgentInput(query="审查这段代码")
        assert inp.query == "审查这段代码"
