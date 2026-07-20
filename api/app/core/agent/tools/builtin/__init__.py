"""导入各内置工具模块，触发其 register_tool 注册到 BUILTIN_REGISTRY。"""
from app.core.agent.tools.builtin import (  # noqa: F401
    bash_tool,
    datetime_tool,
    knowledge,
    memory,
    persona_memory,
    schedule,
    skill_load,
    tool_search,
    web_search,
)
