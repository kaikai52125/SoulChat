"""技能脚本执行器：将 SKILL.md 声明的 tools 注册为 Agent 可调用的工具。

每个 tool 对应一个 scripts/ 下的 Python 脚本，执行时：
1. subprocess.run(["python", "script.py"], input=json_params, cwd=skill_dir)
2. stdin → JSON 参数，stdout → JSON 结果
3. 超时 30s，沙箱受限（仅 scripts/ 目录内可访问）
"""
import asyncio
import json
import os
import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.core.logging import get_logger

logger = get_logger(__name__)

SCRIPT_TIMEOUT = 30  # 脚本超时（秒）
MAX_OUTPUT_BYTES = 64 * 1024  # stdout 上限 64KB


async def _run_script(
    script_path: str, params: dict, cwd: str
) -> str:
    """子进程执行 Python 脚本，stdin 传入 JSON，stdout 接收 JSON。

    返回 stdout 文本（去首尾空白）。抛出 RuntimeError 如果超时/非零退出码。
    """
    input_json = json.dumps(params, ensure_ascii=False)

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_json.encode("utf-8")),
            timeout=SCRIPT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"脚本执行超时（>{SCRIPT_TIMEOUT}s）")

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip() or "(无错误输出)"
        raise RuntimeError(f"脚本退出码 {proc.returncode}: {err_msg}")

    output = stdout.decode("utf-8", errors="replace").strip()
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES] + "\n...(输出被截断)"
    return output


def _make_tool(
    tool_name: str,
    tool_desc: str,
    script_name: str,
    skill_dir: str,
    skill_id: uuid.UUID,
    record_call,
) -> StructuredTool:
    """为一个脚本创建 LangChain StructuredTool。

    动态生成 Pydantic 参数模型：所有参数都是可选的字符串。
    """

    class _SkillParams(BaseModel):
        params_json: str = "{}"

        class Config:
            json_schema_extra = {
                "description": "JSON 格式的参数字符串，例如 '{\"file_path\": \"/data.csv\"}'"
            }

    async def _run(params_json: str = "{}") -> str:
        # 记录调用
        if record_call and skill_id:
            try:
                await record_call(skill_id)
            except Exception:
                pass

        try:
            params = json.loads(params_json) if isinstance(params_json, str) else {}
        except json.JSONDecodeError:
            params = {}

        script_path = os.path.join(skill_dir, script_name)
        if not os.path.isfile(script_path):
            return f"错误：脚本 {script_name} 不存在"

        try:
            result = await _run_script(script_path, params, skill_dir)
            return result
        except RuntimeError as e:
            return f"脚本执行失败：{e}"

    return StructuredTool.from_function(
        name=f"skill__{tool_name}",
        description=tool_desc,
        func=_run,
        args_schema=_SkillParams,
    )


def build_skill_tools(
    skill_id: uuid.UUID,
    skill_config: dict,
    skill_dir: str,
    record_call=None,
    session=None,
    user_id: uuid.UUID | None = None,
) -> list[StructuredTool]:
    """从技能配置构建工具列表。

    skill_config["tools"] 格式：
      [
        {
          "name": "analyze_csv",
          "description": "分析CSV文件",
          "script": "scripts/analyze.py"
        }
      ]

    每个 tool 名称加 skill__ 前缀避免与内置工具冲突。
    session/user_id: 传入时后台计算工具 embedding 供 tool_search 语义搜索。
    """
    tools_def = skill_config.get("tools", [])
    if not tools_def:
        return []

    tools: list[StructuredTool] = []
    for td in tools_def:
        if not isinstance(td, dict):
            continue
        name = td.get("name")
        if not name:
            continue
        script = td.get("script", "")
        if not script:
            continue
        desc = td.get("description", f"执行技能脚本 {name}")

        tool = _make_tool(
            tool_name=name,
            tool_desc=desc,
            script_name=script,
            skill_dir=skill_dir,
            skill_id=skill_id,
            record_call=record_call,
        )
        tools.append(tool)

    # 后台计算 skill 工具 embedding（不阻塞调用方）
    if session is not None and user_id is not None and tools:
        _cache_skill_embeddings(tools, session, user_id)

    return tools


def _cache_skill_embeddings(
    tools: list[StructuredTool],
    session,
    user_id: uuid.UUID,
) -> None:
    """缓存 Skill 工具的 embedding（fire-and-forget）。"""
    import asyncio

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(_compute_skill_embeddings_bg(tools, session, user_id))


async def _compute_skill_embeddings_bg(
    tools: list[StructuredTool],
    session,
    user_id: uuid.UUID,
) -> None:
    """后台计算 Skill 工具 embedding 并写入 _TOOL_EMBEDDING_CACHE。"""
    try:
        from app.core.agent.tools.registry import _compute_and_cache_embedding

        for tool in tools:
            key = tool.name
            name = key.split("__")[-1] if "__" in key else key
            desc = (tool.description or "")[:300]
            await _compute_and_cache_embedding(key, name, desc, session, user_id)
    except Exception as e:
        from app.core.logging import get_logger

        get_logger(__name__).warning("计算 Skill 工具 embedding 失败（忽略）: %s", e)
