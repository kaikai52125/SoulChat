"""Bash 执行工具：在 Skill 脚本目录内安全执行命令，按后缀自动识别解释器。

Agent 通过此工具执行 Skill 声明的脚本文件（Python/Shell/Node/R 等）。
安全模型: os.path.realpath 解析路径 → 检查前缀是否在 Skill 目录内 → 拒绝越狱路径。
"""
import asyncio
import os
import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY = "bash"
SCRIPT_TIMEOUT = 30
MAX_OUTPUT_BYTES = 64 * 1024

# 后缀 → 解释器映射
_SUFFIX_INTERPRETER = {
    ".py": "python",
    ".sh": "bash",
    ".js": "node",
    ".r": "Rscript",
    ".rb": "ruby",
}


def _detect_interpreter(script_path: str) -> str:
    """根据文件后缀自动选择解释器，默认 python。"""
    _, ext = os.path.splitext(script_path)
    return _SUFFIX_INTERPRETER.get(ext.lower(), "python")


class _BashInput(BaseModel):
    query: str = Field(..., description="要执行的完整命令，如 'python scripts/fetch.py --arg value'")


async def _build(ctx: ToolBuildContext) -> StructuredTool | None:
    session = ctx.session
    user_id = ctx.user_id

    async def _run(query: str) -> str:
        """安全执行命令：查找 Skill 目录 → 路径校验 → 子进程执行。"""
        command = query.strip()
        if not command:
            return "错误：命令为空"

        # 1. 查找脚本所属的 Skill 目录
        parts = command.split()
        script_rel = None
        for part in parts:
            if part.startswith("-"):
                continue
            # 找第一个看起来像脚本路径的参数
            candidate = part.strip("\"'")
            if candidate.endswith(tuple(_SUFFIX_INTERPRETER)) or "/" in candidate or "\\" in candidate:
                script_rel = candidate
                break

        if script_rel is None:
            return (
                "错误：未在命令中找到脚本文件路径。"
                "请使用格式: python scripts/xxx.py <参数>"
            )

        # 2. 在所有 Skill 目录中查找脚本
        skill_dir = await _find_skill_dir(script_rel, session, user_id)
        if skill_dir is None:
            return (
                f"安全限制：未在任何技能目录中找到脚本「{script_rel}」。"
                "当前角色没有包含此脚本的技能，或脚本文件不存在。"
            )

        # 3. 安全检查：脚本必须在 skill_dir 内
        full_script = os.path.join(skill_dir, script_rel)
        try:
            real_script = os.path.realpath(full_script)
            real_skill = os.path.realpath(skill_dir)
        except (ValueError, OSError):
            return f"错误：无法解析路径 {full_script}"

        if not _is_within(real_skill, real_script):
            return (
                f"安全限制：脚本路径不在技能目录内，已拒绝执行。\n"
                f"  技能目录: {real_skill}\n"
                f"  请求路径: {real_script}"
            )

        # 4. 确定解释器 + 提取参数
        interpreter = parts[0] if parts[0] != script_rel else _detect_interpreter(script_rel)
        # Windows 上 create_subprocess_exec 找不到裸 'python'，用 sys.executable 兜底
        if interpreter == "python":
            import sys
            interpreter = sys.executable
        # 跳过解释器和脚本路径，只保留脚本后面的参数
        script_idx = next((i for i, p in enumerate(parts) if script_rel in p), 1)
        extra_args = parts[script_idx + 1:]

        # 5. 执行（使用 subprocess.run + 线程池，跨平台可靠）
        import subprocess
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # Windows 上避免 GBK 编码问题
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [interpreter, full_script, *extra_args],
                capture_output=True,
                text=False,
                timeout=SCRIPT_TIMEOUT,
                cwd=real_skill,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return f"脚本执行超时（>{SCRIPT_TIMEOUT}s）"
        except FileNotFoundError:
            return f"错误：解释器「{interpreter}」未找到。"
        except OSError as e:
            return f"错误：启动子进程失败 - {e}"
        except Exception as e:
            return f"错误：启动子进程异常 - {type(e).__name__}: {e}"

        out_text = result.stdout.decode("utf-8", errors="replace").strip()
        err_text = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode != 0:
            msg = f"命令退出码 {result.returncode}"
            if err_text:
                msg += f"\nstderr: {err_text[:500]}"
            if out_text:
                msg += f"\nstdout: {out_text[:500]}"
            return msg

        if len(out_text) > MAX_OUTPUT_BYTES:
            out_text = out_text[:MAX_OUTPUT_BYTES] + "\n...(输出已被截断)"

        return out_text or "(无输出)"

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description=(
            "命令执行：在技能脚本目录中安全执行命令。"
            "支持 Python(.py)/Shell(.sh)/Node(.js)/R(.R) 等脚本。"
            "示例: bash(\"python scripts/fetch_data.py --symbol 600519\")。"
            "注意：只能执行当前角色技能目录内的脚本文件，系统会自动校验路径安全性。"
        ),
        args_schema=_BashInput,
    )


def _is_within(parent: str, child: str) -> bool:
    """检查 child 路径是否在 parent 目录内。"""
    p = os.path.normpath(parent)
    c = os.path.normpath(child)
    return c == p or c.startswith(p + os.sep)


async def _find_skill_dir(
    script_rel: str, session, user_id: uuid.UUID
) -> str | None:
    """查找脚本所属目录：优先用上下文中的角色 ID，否则用活跃角色。"""
    from app.repositories.agent_persona_repository import AgentPersonaRepository
    from app.repositories.skill_repository import SkillRepository
    from app.core.agent.tools.builtin.persona_memory import get_current_persona_id

    try:
        cid = get_current_persona_id()
        if cid:
            persona = await AgentPersonaRepository(session).get(user_id, uuid.UUID(cid))
        else:
            persona = await AgentPersonaRepository(session).get_active(user_id)
        if persona is None:
            return None

        from app.services.skill_service import SKILL_STORAGE_ROOT
        skills = await SkillRepository(session).list_by_persona(persona.id)
        for sk in skills:
            sp = sk.storage_path
            if not sp:
                continue
            # storage_path 存的是相对路径 (./storage/skills/{id})
            # 用 os.path.realpath 统一解析为绝对路径
            if sp.startswith("./"):
                sp = sp[2:]
            skill_dir = os.path.realpath(os.path.join(SKILL_STORAGE_ROOT, os.path.basename(sp)))
            if not os.path.isdir(skill_dir):
                continue

            candidate = os.path.join(skill_dir, script_rel)
            if os.path.isfile(candidate):
                return skill_dir
    except Exception as e:
        logger.warning("查找 Skill 目录失败（忽略）: %s", e)

    return None


register_tool(
    ToolSpec(
        key=KEY,
        name="命令执行",
        description="在技能脚本目录中安全执行命令。支持 Python/Shell/Node/R 等脚本。路径自动校验，拒绝越狱访问。",
        icon="💻",
        builder=_build,
        default_enabled=True,
        layer="core",
    )
)
