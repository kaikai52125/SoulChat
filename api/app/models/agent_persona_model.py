"""AgentPersona ORM 模型 —— 角色 = Agent。

每个角色是一个完整的 Agent 实例：人设提示词 + 工具配置 + 知识库绑定 +
角色专属技能 + 角色记忆（MEMORY.md）+ 上下文管理 + 交互风格。
切换角色 = 切换一整套 AI 行为。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class AgentPersona(Base):
    __tablename__ = "agent_personas"

    # ── 基础 ──
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    avatar_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 人设提示词（system prompt 核心），对话时作为 system message 注入
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)

    # ── 角色记忆（MEMORY.md）──
    # 角色专属记忆文本，Markdown 格式，对话时注入 system prompt
    # 可在角色编辑页手动编辑，也可在对话中通过工具追加
    memory_text: Mapped[str] = mapped_column(Text, default="")

    # ── 工具层 ──
    # 工具白名单（内置工具 key 列表），空列表 = 不限制
    tool_keys: Mapped[list] = mapped_column(JSONB, default=list)
    enable_knowledge: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_web_search: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_mcp: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_active_recall: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_cross_session: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 知识库 ──
    # 默认检索的知识库 id 列表，空 = 全部可用
    kb_ids: Mapped[list] = mapped_column(JSONB, default=list)

    # ── 技能 ──
    # 该角色选用的技能 id 列表（引用 skills 表），切换角色时自动挂载
    skill_ids: Mapped[list] = mapped_column(JSONB, default=list)

    # ── 上下文管理 ──
    # 对话历史模式：'shared' = 所有对话可见；'isolated' = 仅本角色对话
    conversation_scope: Mapped[str] = mapped_column(String(10), default="shared")
    # 上下文窗口大小（历史轮数上限）
    context_window: Mapped[int] = mapped_column(Integer, default=20)

    # ── 交互风格 ──
    human_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    show_avatar: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 状态 ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    in_group_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
