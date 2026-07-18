"""ChatReflector --- 聊天专用轻量自我反思器。

在每次回答完成后，异步（非阻塞）做一次 3 维 self-check：
1. 完整性：有没有遗漏用户问题中的关键信息？
2. 工具利用：有没有该用但没调用的工具？
3. 用户满意度：回答是否直接命中了用户意图？

反思结果以 Markdown 块形式追加到角色 memory_text，供后续对话参考。
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.llm.chat_model import build_chat_model, get_default_chat_config, get_default_config_for_type
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)


class ReflectionResult(BaseModel):
    """ChatReflector 的 3 维反思结果。"""

    completeness: str = ""
    tool_usage: str = ""
    user_satisfaction: str = ""
    key_takeaway: str = ""
    should_remember: bool = False


def _format_reflection_block(result: ReflectionResult, user_msg_summary: str) -> str:
    """把反思结果格式化为 Markdown 反思块，包含时间戳和对话摘要。

    格式：
    --- reflection 时间戳 ---
    **对话**: 摘要
    **完整性**: ...
    **工具利用**: ...
    **用户满意度**: ...
    **经验**: ...
    ---
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    lines = [
        f"--- reflection {now} ---",
        f"**对话**: {user_msg_summary}",
        f"**完整性**: {result.completeness}",
        f"**工具利用**: {result.tool_usage}",
        f"**用户满意度**: {result.user_satisfaction}",
        f"**经验**: {result.key_takeaway}",
        "---",
    ]
    return "\n".join(lines)


class ChatReflector:
    """聊天专用轻量自我反思器。

    在每次回答完成后，异步调用 LLM 做一次 3 维 self-check，
    产生 ReflectionResult 并格式化为 Markdown 反思块。
    """

    def __init__(self, model: ChatOpenAI | None = None):
        self._model = model

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
        reflection_model: str | None = None,
    ) -> "ChatReflector":
        """工厂方法：构建 ChatReflector 实例。

        reflection_model：
          - None → 使用用户默认对话模型
          - "same" → 使用用户默认对话模型
          - 指定模型名 → 使用用户该名称的 model config（暂不支持单独指定，等价于 same）
        """
        if reflection_model and reflection_model not in (None, "same"):
            # 尝试按名称查找特定模型配置
            try:
                config = await get_default_config_for_type(
                    session, user_id, "chat", "反思"
                )
                model = build_chat_model(config, temperature=0.3, streaming=False)
                return cls(model=model)
            except Exception:
                logger.warning("未找到专用反思模型配置，降级复用聊天模型")

        # 默认：复用聊天模型
        config = await get_default_chat_config(session, user_id)
        model = build_chat_model(config, temperature=0.3, streaming=False)
        return cls(model=model)

    async def reflect(
        self,
        user_msg: str,
        assistant_answer: str,
        tool_calls_log: list[dict],
        persona_name: str,
        model_override: ChatOpenAI | None = None,
    ) -> ReflectionResult:
        """对刚刚的回答做 3 维 self-check。

        参数：
            user_msg: 用户本轮消息原文
            assistant_answer: 模型给出的完整回答
            tool_calls_log: 本轮工具调用日志列表
            persona_name: 角色名（用于 prompt 中的人称）
            model_override: 临时覆盖模型（用于测试 mock）
        返回：
            ReflectionResult
        """
        model = model_override or self._model
        if model is None:
            logger.warning("ChatReflector 无可用模型，跳过反思")
            return ReflectionResult()

        prompt = render_agent_prompt(
            "chat_reflection.jinja2",
            persona_name=persona_name,
        )

        # 组装要发给 LLM 的完整内容
        user_block = f"用户问题：{user_msg}\n\n我的回答：{assistant_answer}"
        if tool_calls_log:
            tool_block = "\n".join(
                f"- {tc.get('tool', '?')}({tc.get('query', '?')}) → {tc.get('status', '?')}"
                for tc in tool_calls_log
            )
            user_block += f"\n\n本轮工具调用：\n{tool_block}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_block},
        ]

        try:
            resp = await model.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception as e:
            logger.warning("ChatReflector 调用失败（跳过反思）: %s", e)
            return ReflectionResult()

        data: dict[str, Any] = parse_json_object(text)
        if not data:
            logger.warning("ChatReflector JSON 解析失败，返回空结果")
            return ReflectionResult()

        return ReflectionResult(
            completeness=(data.get("completeness") or "").strip(),
            tool_usage=(data.get("tool_usage") or "").strip(),
            user_satisfaction=(data.get("user_satisfaction") or "").strip(),
            key_takeaway=(data.get("key_takeaway") or "").strip(),
            should_remember=bool(data.get("should_remember", False)),
        )


# ── 辅助函数 ──


def _is_trivial_message(text: str) -> bool:
    """检测用户消息是否为寒暄/闲聊，跳过反思。

    复用 active_recall 模块中 _GREETING_RE 的检测逻辑。
    匹配纯寒暄、超短消息（长度 ≤ 2）、感谢、道别等。
    """
    import re

    t = (text or "").strip()
    if not t:
        return True
    if len(t) <= 2:
        return True
    greeting_re = re.compile(
        r"^(在吗|在不在|你好啊?|您好|hi|hello|嗨|哈喽|哈罗|早|早安|午安|晚安|晚上好|"
        r"早上好|中午好|下午好|好的?|好滴|行|可以|嗯+|哦+|噢+|额|啊+|哈+|呵+|嘿+|"
        r"拜拜|再见|谢谢|多谢|蟹蟹|thanks?|ok|okay)[。.!！?？~～\s]*$",
        re.IGNORECASE,
    )
    return bool(greeting_re.match(t))


def _should_skip_reflection(
    assistant_answer: str, tool_calls_log: list[dict]
) -> bool:
    """判断是否应跳过反思：
    - 回答未使用任何工具 且 回答长度 < 50 字
    """
    answer = (assistant_answer or "").strip()
    if not tool_calls_log and len(answer) < 50:
        return True
    return False


def _extract_recent_reflections(memory_text: str, max_count: int = 10) -> list[str]:
    """从 memory_text 中提取最近的 N 条反思块。

    反思块以 '--- reflection' 开头，以 '---' 结束。
    返回从最新到最旧的列表（memory_text 末尾是最新的）。
    """
    if not memory_text:
        return []

    # 按 "--- reflection" 分割
    blocks: list[str] = []
    for part in memory_text.split("---"):
        part = part.strip()
        if part.startswith("reflection "):
            # 找到对应的结尾 --- 后的完整内容
            blocks.append(part)

    # 如果内容跨多行在分割中，需要更精确的解析
    # 更健壮的方法：按行扫描
    lines = memory_text.split("\n")
    current_block: list[str] = []
    in_reflection = False
    all_blocks: list[list[str]] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--- reflection"):
            in_reflection = True
            current_block = [line]
        elif in_reflection:
            current_block.append(line)
            if stripped == "---":
                all_blocks.append(current_block)
                in_reflection = False
                current_block = []

    # 如果最后一个 reflection 块没有关闭，也加入
    if in_reflection and current_block:
        all_blocks.append(current_block)

    # 提取 key_takeaway 值
    # 方式：从每个反思块中提取"**经验**:"后的内容
    takeaways: list[str] = []
    for block in all_blocks:
        for bl in block:
            bl_stripped = bl.strip()
            if bl_stripped.startswith("**经验**:"):
                exp = bl_stripped[len("**经验**:"):].strip()
                takeaways.append(exp)
                break

    # 取最近的 max_count 条（末尾最新 → 反转取前 max_count）
    takeaways = takeaways[-max_count:]
    return takeaways


def _summarize_user_msg(text: str, max_len: int = 40) -> str:
    """截取用户消息前 N 字作为摘要（用于反思块标题）。"""
    t = (text or "").strip()
    if not t:
        return "(空)"
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"


# ── 反思蒸馏 ──

_MAX_RAW_REFLECTIONS = 15   # 原始反思保留上限
_KEEP_RECENT = 5            # 蒸馏后保留最近 N 条原文
_DISTILL_SUMMARY_HEADER = "## 经验总结\n"


async def _compact_reflections(memory_text: str, model) -> str:
    """当原始反思超过上限时，LLM 蒸馏旧反思为经验总结。

    逻辑：
    1. 从 memory_text 中分离「非反思内容」和「反思块」
    2. 反思 > _MAX_RAW_REFLECTIONS 条时触发蒸馏
    3. LLM 将最旧的 (总数 - _KEEP_RECENT) 条反思蒸馏为一段"经验总结"
    4. 返回：非反思内容 + 经验总结 + 最近 _KEEP_RECENT 条原文

    蒸馏是异步的，失败时降级为纯截断（保留最近 _KEEP_RECENT 条）。
    """
    if not memory_text:
        return memory_text

    # 1. 分离反思块和非反思内容
    blocks = _parse_reflection_blocks(memory_text)
    if len(blocks) <= _MAX_RAW_REFLECTIONS:
        return memory_text  # 未超上限，无需蒸馏

    # 2. 取出待蒸馏的旧反思（最旧的 N - _KEEP_RECENT 条）
    to_distill = blocks[:-_KEEP_RECENT] if _KEEP_RECENT > 0 else blocks
    keep_raw = blocks[-_KEEP_RECENT:] if _KEEP_RECENT > 0 else []

    # 3. LLM 蒸馏
    distilled = await _run_distillation(to_distill, model)

    # 4. 重建 memory_text
    non_reflection = _extract_non_reflection_content(memory_text)
    parts: list[str] = []
    if non_reflection:
        parts.append(non_reflection)
    if distilled:
        parts.append(_DISTILL_SUMMARY_HEADER + distilled)
    for b in keep_raw:
        parts.append("\n".join(b))

    return "\n\n".join(parts)


def _parse_reflection_blocks(memory_text: str) -> list[list[str]]:
    """解析 memory_text 中的所有反思块，返回按时间顺序排列的块列表。

    每个块是以 '--- reflection' 开头、'---' 结尾的行组。
    """
    lines = memory_text.split("\n")
    blocks: list[list[str]] = []
    current: list[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--- reflection"):
            in_block = True
            current = [line]
        elif in_block:
            current.append(line)
            if stripped == "---":
                blocks.append(current)
                in_block = False
                current = []

    if in_block and current:
        blocks.append(current)
    return blocks


def _extract_non_reflection_content(memory_text: str) -> str:
    """提取 memory_text 中第一个反思块之前的所有内容（角色设定等）。"""
    idx = memory_text.find("\n--- reflection ")
    if idx < 0:
        idx = memory_text.find("--- reflection ")
    if idx < 0:
        return memory_text  # 没有反思块，全部是非反思内容
    return memory_text[:idx].rstrip()


async def _run_distillation(
    blocks: list[list[str]], model
) -> str:
    """调用 LLM 将一组反思块蒸馏为一段经验总结。

    blocks 是待蒸馏的反思块列表（每块是多行文本）。
    失败时返回空字符串。
    """
    if not blocks:
        return ""

    # 提取每条反思的"经验"作为蒸馏输入
    takeaways: list[str] = []
    for block in blocks:
        text = "\n".join(block)
        # 从反思块中提取经验行
        for line in block:
            stripped = line.strip()
            if stripped.startswith("**经验**:"):
                takeaways.append(stripped[len("**经验**:"):].strip())
                break
        else:
            # 没有显式经验行，用全文摘要
            takeaways.append(text[:200])

    if not takeaways:
        return ""

    prompt = render_agent_prompt(
        "reflection_compact.jinja2",
        takeaways=takeaways,
    )

    try:
        resp = await model.ainvoke([{"role": "user", "content": prompt}])
        result = resp.content if isinstance(resp.content, str) else str(resp.content)
        return result.strip()
    except Exception as e:
        logger.warning("反思蒸馏 LLM 调用失败（降级为截断）: %s", e)
        return ""


__all__ = [
    "ChatReflector",
    "ReflectionResult",
    "_format_reflection_block",
    "_is_trivial_message",
    "_should_skip_reflection",
    "_extract_recent_reflections",
    "_summarize_user_msg",
    "_compact_reflections",
    "_MAX_RAW_REFLECTIONS",
    "_KEEP_RECENT",
]
