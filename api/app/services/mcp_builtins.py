"""内置 MCP Server 模板 —— 已验证可用，自动同步工具。"""
BUILTIN_MCP_TEMPLATES: list[dict] = [
    {
        "key": "cf-docs",
        "name": "Cloudflare 文档",
        "description": "Cloudflare 官方文档检索：API 参考、开发指南（已验证）",
        "icon": "📖",
        "transport": "sse",
        "url_template": "https://docs.mcp.cloudflare.com/sse",
        "auth_type": "none",
        "tools": [],
    },
]


def get_builtin_mcp(key: str) -> dict | None:
    for t in BUILTIN_MCP_TEMPLATES:
        if t["key"] == key:
            return dict(t)
    return None


__all__ = ["BUILTIN_MCP_TEMPLATES", "get_builtin_mcp"]
