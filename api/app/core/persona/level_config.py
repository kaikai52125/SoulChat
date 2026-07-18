"""等级配置：XP 阈值表 + XP 获取规则 + 每日上限。

等级曲线采用类 Fibonacci 增长：前期快（Lv.1→5 只需 850 XP），后期慢（Lv.50 需 500,000 XP）。
"""

# ── 等级阈值表（累积 XP → 等级） ──
# 键=等级, 值=到达该等级所需的累积 XP
LEVEL_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 850,
    6: 1300,
    7: 1900,
    8: 2700,
    9: 3700,
    10: 5000,
    11: 6600,
    12: 8500,
    13: 10800,
    14: 13500,
    15: 16800,
    16: 20600,
    17: 25000,
    18: 30000,
    19: 35700,
    20: 42000,
    21: 49000,
    22: 56800,
    23: 65400,
    24: 74900,
    25: 85300,
    26: 97000,
    27: 110000,
    28: 124500,
    29: 140500,
    30: 158000,
    35: 280000,
    40: 380000,
    50: 500000,
}

# 最大等级
MAX_LEVEL = 50

# ── XP 获取规则 ──
# 每条规则: (weight_key, base_xp, description)
XP_RULES = {
    "base_interaction": 10,       # 基础对话轮次
    "deep_conversation": 5,       # 深度对话加成（会话超过 5 轮后每轮额外）
    "memory_reuse": 3,            # 引用 ≥30 天前的旧记忆
    "tool_usage": 2,              # 调用工具（知识库/联网/MCP）
    "emotion_positive": 5,        # 用户下一条消息情绪 valence > 0.6
    "consecutive_7_days": 10,     # 连续第 7 天互动奖励
    "first_milestone": 50,        # 首次达成各类里程碑
}

# 单角色每日 XP 上限
DAILY_XP_CAP = 200

# 深度对话触发阈值（会话内消息数）
DEEP_CONVERSATION_THRESHOLD = 5

# 记忆复用最低天数（记忆年龄 ≥ 此天数才算"旧记忆"复用）
MEMORY_REUSE_MIN_DAYS = 30


def xp_for_level(level: int) -> int:
    """返回升到指定等级所需的累积 XP（到达该等级的阈值）。"""
    return LEVEL_THRESHOLDS.get(level, LEVEL_THRESHOLDS[MAX_LEVEL])


def calculate_level(xp: int) -> int:
    """根据累积 XP 计算当前等级。"""
    current = 1
    for lv in sorted(LEVEL_THRESHOLDS.keys()):
        if xp >= LEVEL_THRESHOLDS[lv]:
            current = lv
        else:
            break
    return current


def xp_to_next_level(xp: int) -> tuple[int, int]:
    """返回 (距离下一级还需要的 XP, 当前等级升级所需的总 XP)。

    已满级时返回 (0, 0)。
    """
    current_level = calculate_level(xp)
    if current_level >= MAX_LEVEL:
        return 0, 0

    # 找下一个有定义的阈值等级
    next_threshold = None
    for lv in sorted(LEVEL_THRESHOLDS.keys()):
        if lv > current_level:
            next_threshold = lv
            break

    if next_threshold is None:
        return 0, 0

    need = LEVEL_THRESHOLDS[next_threshold] - xp
    total = LEVEL_THRESHOLDS[next_threshold] - LEVEL_THRESHOLDS[current_level]
    return max(need, 0), max(total, 1)
