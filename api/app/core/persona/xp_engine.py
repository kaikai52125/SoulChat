"""XP 计算引擎：互动后计算 XP 收益、检查升级、更新亲密度和连续天数。

纯函数，不依赖数据库。调用方负责读写 persona_growth 记录。
"""
from datetime import date, datetime, timedelta

from app.core.persona.level_config import (
    DEEP_CONVERSATION_THRESHOLD,
    XP_RULES,
    calculate_level,
)


def calculate_xp_gain(
    *,
    conversation_turn_count: int = 1,
    used_old_memory: bool = False,
    used_tools: bool = False,
    emotion_valence: float = 0.0,
    is_consecutive_7: bool = False,
    is_first_milestone: bool = False,
) -> dict:
    """计算一次互动获得的 XP，返回明细。

    返回: {"total": int, "breakdown": {"base": int, ...}}
    """
    breakdown: dict[str, int] = {}
    total = 0

    # 基础对话
    base = XP_RULES["base_interaction"]
    breakdown["base"] = base
    total += base

    # 深度对话加成
    if conversation_turn_count > DEEP_CONVERSATION_THRESHOLD:
        deep = XP_RULES["deep_conversation"]
        breakdown["deep"] = deep
        total += deep

    # 记忆复用
    if used_old_memory:
        mem = XP_RULES["memory_reuse"]
        breakdown["memory"] = mem
        total += mem

    # 工具调用
    if used_tools:
        tool = XP_RULES["tool_usage"]
        breakdown["tool"] = tool
        total += tool

    # 情绪正反馈
    if emotion_valence > 0.6:
        emo = XP_RULES["emotion_positive"]
        breakdown["emotion"] = emo
        total += emo

    # 连续 7 天
    if is_consecutive_7:
        streak = XP_RULES["consecutive_7_days"]
        breakdown["streak"] = streak
        total += streak

    # 首次里程碑
    if is_first_milestone:
        milestone = XP_RULES["first_milestone"]
        breakdown["milestone"] = milestone
        total += milestone

    return {"total": total, "breakdown": breakdown}


def check_level_up(old_level: int, new_xp: int) -> tuple[int, bool]:
    """检查是否升级。返回 (new_level, did_level_up)。"""
    new_level = calculate_level(new_xp)
    return new_level, new_level > old_level


def compute_intimacy(
    *,
    level: int,
    max_level: int,
    consecutive_days: int,
    milestone_count: int,
    avg_emotion_valence: float,
) -> float:
    """计算亲密度分数 (0~100)。

    四个维度加权：
    - 等级贡献 40%（level / max_level * 40）
    - 连续互动贡献 20%（consecutive_days / 30 * 20，上限 20）
    - 里程碑贡献 20%（milestone_count / 20 * 20，上限 20）
    - 情绪正向度贡献 20%（avg_emotion_valence * 20）
    """
    from app.core.persona.level_config import MAX_LEVEL

    level_score = (level / MAX_LEVEL) * 40
    streak_score = min(consecutive_days / 30, 1.0) * 20
    milestone_score = min(milestone_count / 20, 1.0) * 20
    emotion_score = max(avg_emotion_valence, 0.0) * 20  # valence 可能是负的

    raw = level_score + streak_score + milestone_score + emotion_score
    return round(min(raw, 100.0), 2)


def update_consecutive_days(
    current_consecutive: int,
    last_interaction_at: datetime | None,
) -> tuple[int, bool]:
    """根据上次互动时间更新连续天数。返回 (new_consecutive, is_streak_reset)。

    规则：
    - 今天已互动过 → 不变
    - 昨天互动过 → +1 连续
    - 昨天之前互动过 → 重置为 1
    - 从未互动过 → 设为 1
    """
    today = date.today()

    if last_interaction_at is None:
        return 1, False

    last_date = last_interaction_at.date() if isinstance(last_interaction_at, datetime) else last_interaction_at

    if last_date == today:
        return current_consecutive, False

    if last_date == today - timedelta(days=1):
        return current_consecutive + 1, False

    return 1, True

