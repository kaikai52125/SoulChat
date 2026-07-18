"""协作模式 Rubric:6 维加权，调整权重适配多角色协作产出。

与 research rubric 使用相同的 6 维框架，但调整权重分配：
- 「覆盖度」权重降低（0.20→0.15）：协作模式下多个角色分别覆盖不同子问题，
  Orchestrator 汇总时天然覆盖更全面，不需要给太高权重
- 「引用对齐」权重降低（0.25→0.20）：协作模式不依赖外部引用，更注重内部一致性
- 「论证深度」权重提高（0.15→0.20）：多角色协作的核心价值是深度分析
- 「内部一致性」新增（0→0.15）：多角色产出拼装后是否逻辑一致、无矛盾
- 「相关性」权重提高（0.15→0.20）：各角色输出是否紧扣自身任务、不离题

| 维度           | 权重 | 单维硬门槛(0~5) |
|---------------|------|------------|
| 覆盖度          | 0.15 | < 2       |
| 引用对齐         | 0.20 | < 2       |
| 论证深度         | 0.20 | < 2       |
| 内部一致性(新增)   | 0.15 | < 3       |
| 相关性          | 0.20 | < 3       |
| 结构与可读        | 0.10 | < 2       |
"""
from app.core.agent.loop.models import RubricDef, RubricDim

# 单维原始分量纲：0~5（verifier prompt 也按这个量纲打分）
_RAW_MAX = 5.0

COLLABORATION_RUBRIC = RubricDef(
    name="collaboration",
    raw_max=_RAW_MAX,
    pass_threshold=0.7,
    dims=[
        RubricDim(
            key="coverage",
            label="覆盖度",
            weight=0.15,
            threshold=2.0,
            desc=(
                "0~5，所有子任务的问题面是否被实质回答。"
                "5=全部覆盖且深入；3=主体覆盖但有小遗漏；1=只回答了部分子问题。"
            ),
        ),
        RubricDim(
            key="faithfulness",
            label="引用对齐",
            weight=0.20,
            threshold=2.0,
            desc=(
                "0~5，各角色产出中的论据是否有逻辑支撑，角色间信息是否一致。"
                "5=每个论点都有支撑；3=多数有支撑但偶有矛盾；1=明显矛盾或缺支撑。"
            ),
        ),
        RubricDim(
            key="depth",
            label="论证深度",
            weight=0.20,
            threshold=2.0,
            desc=(
                "0~5，是否仅罗列事实，有无对比/取舍/因果分析。"
                "5=多层论证 + 真知灼见；3=有分析但偏浅；1=纯罗列、无分析。"
            ),
        ),
        RubricDim(
            key="consistency",
            label="内部一致性",
            weight=0.15,
            threshold=3.0,
            desc=(
                "0~5，多角色产出拼装后是否逻辑一致、无自相矛盾。"
                "5=行文流畅逻辑一致；3=有小矛盾但可调和；1=明显前后打架。"
            ),
        ),
        RubricDim(
            key="relevance",
            label="相关性",
            weight=0.20,
            threshold=3.0,
            desc=(
                "0~5，各角色子任务产出是否紧扣自身任务分配、不离题。"
                "5=每段都紧扣；3=主体紧扣但个别偏离；1=离题严重。"
            ),
        ),
        RubricDim(
            key="readability",
            label="结构与可读",
            weight=0.10,
            threshold=2.0,
            desc=(
                "0~5，汇总报告结构是否清晰、行文是否流畅。"
                "5=清晰友好；3=可读但有冗余；1=结构混乱难读。"
            ),
        ),
    ],
)

__all__ = ["COLLABORATION_RUBRIC"]
