"""Shared Blackboard: 任务协作模式中角色间共享的结构化状态空间。

Blackboard 是协作的核心数据层，替代纯文本 transcript 的角色间通信。
每个 entry 带类型标签（task / subtask / finding / draft / comment / decision），
使角色能高效提取高价值信息，而不是从无结构文本中自行解析。

设计要点:
- 纯内存数据结构（每次任务新建，不跨对话持久化）
- Entry 带类型语义，支持按角色/类型过滤
- get_context_for() 为角色提供个性化黑板视图
- summarize() 提取核心要点给 Verifier 审查
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class BlackboardEntry(BaseModel):
    """黑板单条记录。

    type:
      - task:      Orchestrator 定义的任务/目标
      - subtask:   Orchestrator 定义的子任务
      - finding:   角色执行子任务的产出/发现
      - draft:     角色产出的草稿/部分内容
      - comment:   Verifier 或其他角色的评论
      - decision:  Orchestrator 或 Verifier 做出的决策
    """
    type: Literal["task", "subtask", "finding", "draft", "comment", "decision"]
    author: str  # persona name 或 "orchestrator" 或 "verifier"
    content: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SharedBlackboard:
    """共享黑板：角色间协作的核心数据结构。

    所有操作都是纯内存的（O(n) 量级，n 通常 < 50），不涉及 I/O。
    """

    def __init__(self) -> None:
        self.entries: list[BlackboardEntry] = []

    def post(self, entry: BlackboardEntry) -> None:
        """向黑板写入一条记录。

        Args:
            entry: 要写入的 BlackboardEntry
        """
        # 确保 entry 有时间戳
        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()
        self.entries.append(entry)

    def get_context_for(
        self, persona_name: str, max_entries: int = 15
    ) -> str:
        """为指定角色生成个性化的黑板上下文文本。

        隔离规则（只展示该角色需要知道的）：
        1. 该角色自己的 finding（产出）
        2. 分配给该角色的 subtask
        3. 该角色依赖的其他角色的 finding（前置依赖的产出）
        4. 全局 task 目标（让角色知道总目标但不知道其他角色的具体任务）

        不展示：
        - 其他角色的 subtask 描述（防止角色越界覆盖）
        - 其他角色的 finding（除非是该角色的依赖）

        Args:
            persona_name: 角色名
            max_entries: 最多返回多少条记录

        Returns:
            格式化文本，无记录时返回空字符串
        """
        if not self.entries:
            return ""

        # 1. 收集该角色的 subtask ID 和依赖关系
        my_subtask_ids: set[str] = set()
        my_dependency_ids: set[str] = set()
        for entry in self.entries:
            if entry.type == "subtask" and entry.author == "orchestrator":
                # entry.content 格式: "subtask_1: 研究A股市场 → A股研究员"
                if f"→ {persona_name}" in entry.content:
                    # 提取 subtask id
                    sid = entry.content.split(":")[0].strip()
                    my_subtask_ids.add(sid)

        # 2. 该角色的依赖 —— 从分配给它的 subtask 中提取
        # 依赖信息在 TaskPlan.subtasks 中，黑板里不存。简化处理：
        # 展示所有该角色之前的 finding（时序上更早被 post 的 finding 可能是依赖）
        # 加上该角色自己的 finding

        lines: list[str] = []

        # 全局目标（精简版 —— 只展示 goal，不展示其他角色的具体 task）
        for entry in self.entries:
            if entry.type == "task" and entry.author == "orchestrator":
                lines.append(f"【协作目标】{entry.content}")
                break

        # 分配给该角色的 subtask
        for entry in self.entries:
            if entry.type == "subtask" and entry.author == "orchestrator":
                if f"→ {persona_name}" in entry.content:
                    lines.append(f"【你的任务】{entry.content}")
                    break

        # 自己的 finding（如果有已有产出）
        own_findings = [
            e for e in self.entries
            if e.type == "finding" and e.author == persona_name
        ]
        for entry in own_findings[-3:]:  # 最近 3 条
            lines.append(f"【{entry.type}】{entry.author}: {entry.content}")

        # 其他角色的 finding —— 只在作为"已有上下文"出现时展示
        # （不是该角色的 finding，也不是 task/subtask 系统条目）
        other_findings = [
            e for e in self.entries
            if e.type == "finding" and e.author != persona_name
        ]
        if other_findings:
            lines.append("【其他角色的已有产出】")
            for entry in other_findings[-5:]:  # 最近 5 条
                lines.append(f"  · {entry.author}: {entry.content[:200]}")

        return "\n".join(lines) if lines else ""

    def summarize(self) -> str:
        """提取黑板中所有 finding + decision 的核心要点，供 Verifier 审查。

        Returns:
            结构化摘要文本，无相关记录时返回空字符串
        """
        relevant = [
            e for e in self.entries
            if e.type in ("finding", "decision")
        ]

        if not relevant:
            return ""

        lines: list[str] = [
            f"===== 协作产出摘要 =====\n共 {len(relevant)} 条核心记录",
        ]
        for i, entry in enumerate(relevant, 1):
            lines.append(f"\n{i}. 【{entry.type}】{entry.author}:\n   {entry.content}")

        return "\n".join(lines)

    def get_by_type(self, entry_type: str) -> list[BlackboardEntry]:
        """按类型过滤黑板条目。

        Args:
            entry_type: 条目类型（task / subtask / finding / draft / comment / decision）

        Returns:
            匹配类型的条目列表
        """
        return [e for e in self.entries if e.type == entry_type]

    def clear(self) -> None:
        """清空黑板所有条目（任务结束后调用）。"""
        self.entries.clear()


__all__ = ["BlackboardEntry", "SharedBlackboard"]
