"""Skill ORM 模型 —— 角色专属技能。

每个技能归属于一个 Persona（角色），是角色的「任务能力包」：
专属提示词 + 工具白名单 + 可选绑定知识库 + 轻量配置（快捷提问/few-shot）。
对话时随角色自动挂载，也可临时覆盖。

支持三种来源：
- builtin：内置模板复制而来
- custom：用户手动创建
- imported：从 .soulskill.zip 压缩包导入
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 归属的角色
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_personas.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(256), default="")
    icon: Mapped[str] = mapped_column(String(16), default="🧩")
    # 专属任务提示词
    prompt: Mapped[str] = mapped_column(Text, default="")
    # 工具白名单：内置工具 key 列表，非空=只启用这些工具；空=不限定
    tool_keys: Mapped[list] = mapped_column(JSONB, default=list)
    # 可选绑定知识库（删库则置空）
    kb_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 轻量配置：{ quick_prompts: [str], few_shots: [{input, output}] }
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 是否在对话页技能选择器中显示
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 来源：'builtin' | 'custom' | 'imported'
    source: Mapped[str] = mapped_column(String(16), default="custom")
    # zip 导入时的去重指纹（SHA256(manifest + prompt)）
    import_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 是否公开到技能市场（其他用户可浏览并复制到自己的角色）
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 是否由内置模板复制而来（前端展示标记）
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    # 技能被调用次数（每次 Agent 执行该技能声明的工具时 +1）
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    # 成功次数（脚本 exit code 0）
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    # 失败次数（脚本 exit code != 0 或异常）
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    # 最近一次调用时间
    last_called_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 脚本文件存储路径（zip 导入时解压到 storage/skills/{skill_id}/）
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkillCallLog(Base):
    """技能调用日志 —— 每次工具执行记录一条，供统计图表使用。"""
    __tablename__ = "skill_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
