"""XP 引擎单元测试：验证 XP 计算、等级、亲密度、连续天数的正确性。"""
import pytest
from datetime import date, datetime, timedelta

from app.core.persona.level_config import (
    LEVEL_THRESHOLDS,
    MAX_LEVEL,
    calculate_level,
    xp_to_next_level,
    xp_for_level,
)
from app.core.persona.xp_engine import (
    calculate_xp_gain,
    check_level_up,
    compute_intimacy,
    update_consecutive_days,
)


class TestCalculateXP:
    def test_base_only(self):
        result = calculate_xp_gain()
        assert result["total"] == 10
        assert result["breakdown"]["base"] == 10

    def test_deep_conversation(self):
        result = calculate_xp_gain(conversation_turn_count=6)
        assert result["total"] == 15  # 10 + 5
        assert "deep" in result["breakdown"]

    def test_no_deep_bonus_at_threshold(self):
        result = calculate_xp_gain(conversation_turn_count=5)
        assert result["total"] == 10  # exactly at threshold, no bonus

    def test_memory_reuse(self):
        result = calculate_xp_gain(used_old_memory=True)
        assert result["total"] == 13  # 10 + 3

    def test_tool_usage(self):
        result = calculate_xp_gain(used_tools=True)
        assert result["total"] == 12  # 10 + 2

    def test_emotion_positive(self):
        result = calculate_xp_gain(emotion_valence=0.7)
        assert result["total"] == 15  # 10 + 5

    def test_emotion_not_positive(self):
        result = calculate_xp_gain(emotion_valence=0.6)
        assert result["total"] == 10  # exactly 0.6, no bonus

    def test_emotion_negative(self):
        result = calculate_xp_gain(emotion_valence=-0.5)
        assert result["total"] == 10  # negative, no bonus

    def test_consecutive_7(self):
        result = calculate_xp_gain(is_consecutive_7=True)
        assert result["total"] == 20  # 10 + 10

    def test_first_milestone(self):
        result = calculate_xp_gain(is_first_milestone=True)
        assert result["total"] == 60  # 10 + 50

    def test_all_bonuses(self):
        result = calculate_xp_gain(
            conversation_turn_count=8,
            used_old_memory=True,
            used_tools=True,
            emotion_valence=0.8,
            is_consecutive_7=True,
        )
        assert result["total"] == 35  # 10 + 5 + 3 + 2 + 5 + 10 = 35 (no milestone)
        assert len(result["breakdown"]) == 6  # base, deep, memory, tool, emotion, streak


class TestLevelProgression:
    def test_level_1_at_zero(self):
        assert calculate_level(0) == 1

    def test_level_2_at_100(self):
        assert calculate_level(100) == 2

    def test_level_5_at_850(self):
        assert calculate_level(850) == 5

    def test_level_10_at_5000(self):
        assert calculate_level(5000) == 10

    def test_level_50_at_500k(self):
        assert calculate_level(500000) == 50

    def test_level_capped_at_50(self):
        assert calculate_level(999999) == 50

    def test_xp_for_level(self):
        assert xp_for_level(2) == 100
        assert xp_for_level(10) == 5000
        assert xp_for_level(999) == 500000  # beyond defined max, returns MAX_LEVEL

    def test_xp_to_next(self):
        need, total = xp_to_next_level(0)
        assert need == 100  # Lv.1→2 needs 100
        assert total == 100

    def test_xp_to_next_mid_level(self):
        need, total = xp_to_next_level(200)
        assert need == 50  # 200 XP = Lv.2, need 50 more to Lv.3
        assert total == 150  # Lv.2→3 gap is 150

    def test_xp_to_next_at_max(self):
        need, total = xp_to_next_level(500000)
        assert need == 0
        assert total == 0

    def test_check_level_up(self):
        new_level, did_up = check_level_up(1, 100)
        assert new_level == 2
        assert did_up is True

    def test_check_no_level_up(self):
        new_level, did_up = check_level_up(1, 50)
        assert new_level == 1
        assert did_up is False


class TestIntimacy:
    def test_new_player(self):
        score = compute_intimacy(
            level=1, max_level=50, consecutive_days=0,
            milestone_count=0, avg_emotion_valence=0.0,
        )
        assert score == pytest.approx(0.8, abs=1.0)  # level 1/50*40=0.8

    def test_mid_game(self):
        score = compute_intimacy(
            level=10, max_level=50, consecutive_days=15,
            milestone_count=5, avg_emotion_valence=0.5,
        )
        expected = (10/50)*40 + min(15/30, 1)*20 + min(5/20, 1)*20 + 0.5*20
        assert score == pytest.approx(round(min(expected, 100), 2))

    def test_capped_at_100(self):
        score = compute_intimacy(
            level=50, max_level=50, consecutive_days=365,
            milestone_count=100, avg_emotion_valence=1.0,
        )
        assert score == 100.0


class TestConsecutiveDays:
    def test_first_interaction(self):
        new_cnt, reset = update_consecutive_days(0, None)
        assert new_cnt == 1
        assert reset is False

    def test_same_day_no_change(self):
        today = datetime.now()
        new_cnt, reset = update_consecutive_days(5, today)
        assert new_cnt == 5
        assert reset is False

    def test_yesterday_increment(self):
        yesterday = datetime.now() - timedelta(days=1)
        new_cnt, reset = update_consecutive_days(3, yesterday)
        assert new_cnt == 4
        assert reset is False

    def test_gap_resets(self):
        three_days_ago = datetime.now() - timedelta(days=3)
        new_cnt, reset = update_consecutive_days(10, three_days_ago)
        assert new_cnt == 1
        assert reset is True

    def test_month_boundary(self):
        """Verify timedelta-based yesterday detection works correctly (not broken replace).

        This tests the fix: the old code used `today.replace(day=today.day-1)` which
        fails on the 1st of each month. The fix uses `today - timedelta(days=1)`.
        We verify by passing a datetime exactly 1 day ago - it should be recognized as yesterday.
        """
        one_day_ago = datetime.now() - timedelta(days=1)
        new_cnt, reset = update_consecutive_days(10, one_day_ago)
        assert new_cnt == 11  # should increment
        assert reset is False

    def test_two_days_ago_resets(self):
        """Two days ago should reset the streak."""
        two_days_ago = datetime.now() - timedelta(days=2)
        new_cnt, reset = update_consecutive_days(100, two_days_ago)
        assert new_cnt == 1
        assert reset is True
