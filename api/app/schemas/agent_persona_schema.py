"""对话人格（角色）请求/响应 schema。角色 = Agent 完整配置。"""
from pydantic import BaseModel, Field

# ── 字段名常量 ──
CONVERSATION_SCOPE_SHARED = "shared"
CONVERSATION_SCOPE_ISOLATED = "isolated"
CONVERSATION_SCOPE_VALUES = (CONVERSATION_SCOPE_SHARED, CONVERSATION_SCOPE_ISOLATED)


class PersonaCreate(BaseModel):
    """新增角色。name 必填，其余可选。"""

    name: str = Field(min_length=1, max_length=64)
    avatar_key: str | None = Field(default=None, max_length=512)
    system_prompt: str = Field(default="", max_length=20000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    memory_text: str = Field(default="", max_length=50000)
    tool_keys: list[str] = Field(default_factory=list)
    enable_knowledge: bool = Field(default=True)
    enable_memory: bool = Field(default=True)
    enable_web_search: bool = Field(default=False)
    enable_mcp: bool = Field(default=False)
    enable_active_recall: bool = Field(default=True)
    enable_cross_session: bool = Field(default=False)
    kb_ids: list[str] = Field(default_factory=list)
    conversation_scope: str = Field(default=CONVERSATION_SCOPE_SHARED)
    context_window: int = Field(default=20, ge=1, le=100)
    human_mode: bool = Field(default=False)
    show_avatar: bool = Field(default=False)


class PersonaUpdate(BaseModel):
    """编辑角色（全部可选，传啥改啥）。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_key: str | None = Field(default=None, max_length=512)
    system_prompt: str | None = Field(default=None, max_length=20000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    memory_text: str | None = Field(default=None, max_length=50000)
    tool_keys: list[str] | None = Field(default=None)
    enable_knowledge: bool | None = Field(default=None)
    enable_memory: bool | None = Field(default=None)
    enable_web_search: bool | None = Field(default=None)
    enable_mcp: bool | None = Field(default=None)
    enable_active_recall: bool | None = Field(default=None)
    enable_cross_session: bool | None = Field(default=None)
    kb_ids: list[str] | None = Field(default=None)
    conversation_scope: str | None = Field(default=None)
    context_window: int | None = Field(default=None, ge=1, le=100)
    human_mode: bool | None = Field(default=None)
    show_avatar: bool | None = Field(default=None)


class PersonaOut(BaseModel):
    """角色出参。"""

    id: str
    name: str
    avatar_key: str | None
    avatar_url: str | None
    system_prompt: str
    temperature: float
    is_active: bool

    memory_text: str
    tool_keys: list[str]
    enable_knowledge: bool
    enable_memory: bool
    enable_web_search: bool
    enable_mcp: bool
    enable_active_recall: bool
    enable_cross_session: bool
    kb_ids: list[str]
    conversation_scope: str
    context_window: int
    human_mode: bool
    show_avatar: bool
