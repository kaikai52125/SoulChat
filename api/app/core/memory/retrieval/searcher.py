"""记忆图谱混合检索：实体向量召回 + 全文召回 → 融合 → 邻居关系遍历。

强制 user_id 过滤做数据隔离。命中实体后取其一跳关系，拼成「实体 + 关联事实」上下文。
"""
import uuid
from datetime import datetime

from app.config import settings
from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

logger = get_logger(__name__)

# 融合权重（向量为主，全文为辅，社区为间接信号，重要度为附加加权）
_VECTOR_WEIGHT = 0.45
_FULLTEXT_WEIGHT = 0.25
_COMMUNITY_WEIGHT = 0.10
_IMPORTANCE_WEIGHT = 0.20
# 长期记忆轻微加权（更稳定的记忆优先）
_LONG_TERM_BONUS = 0.05
_LONG_TERM_RELIABILITY_WEIGHT = 1.1
_DEFAULT_CONFIDENCE = 0.8
_EXPIRED_DECAY = 0.5  # 已过期关系的可靠性权重衰减因子


def _float(value: object, default: float) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: object) -> datetime | None:
    """把 Neo4j 返回的时间字符串解析为 datetime（容错）。"""
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value
        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _is_expired(invalid_at: object) -> bool:
    """判断关系是否已过期（invalid_at 非空且 < 当前时间）。"""
    dt = _parse_dt(invalid_at)
    return dt is not None and dt < datetime.now()


def _layer_weight(memory_layer: str | None) -> float:
    return _LONG_TERM_RELIABILITY_WEIGHT if memory_layer == "long_term" else 1.0


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _rank_memory_hits(
    hits: dict[str, dict],
    semantic_scores: dict[str, float],
    *,
    top_k: int,
    min_confidence: float | None,
    use_reliability_score: bool,
) -> list[tuple[str, float, float]]:
    """Rank memory hits while preserving the original semantic score for callers."""
    ranked: list[tuple[str, float, float]] = []
    for eid, score in semantic_scores.items():
        src = hits.get(eid) or {}
        confidence = _float(src.get("confidence"), _DEFAULT_CONFIDENCE)
        if min_confidence is not None and confidence < min_confidence:
            continue
        reliability_score = score
        if use_reliability_score:
            reliability_score = score * confidence * _layer_weight(src.get("memory_layer"))
        ranked.append((eid, score, reliability_score))
    ranked.sort(key=lambda x: x[2] if use_reliability_score else x[1], reverse=True)
    return ranked[:top_k]


def _is_uncertain(confidence: object, threshold: float | None = None) -> bool:
    threshold = settings.active_recall_uncertain_confidence if threshold is None else threshold
    return _float(confidence, _DEFAULT_CONFIDENCE) < threshold


async def search_memory(
    *,
    embed_client: LLMClient,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 10,
    recall_size: int = 20,
    min_vector_score: float | None = None,
    min_confidence: float | None = None,
    use_reliability_score: bool = False,
    query_vector: list[float] | None = None,
) -> list[dict]:
    """记忆检索：返回 top_k 个相关实体，每个带其一跳关系（关联事实）。

    结果结构：{id, name, type, description, aliases, score, relations:[{predicate, object_name, source_text}]}

    min_vector_score 不为 None 时启用「绝对相关度门控」（精确导向，用于全局搜索）：
    只保留全文命中 或 向量余弦相似度 ≥ 阈值的实体。

    query_vector 不为 None 时复用外部已算好的查询向量，避免重复 embedding 调用。
    """
    repo = MemoryGraphRepository()
    uid = str(user_id)

    # 0. 查询向量化（一次 embedding，三路召回复用）
    try:
        qvec = query_vector if query_vector is not None else await embed_client.embed_one(query)
    except Exception as e:
        logger.warning("查询向量化失败: %s", e)
        return []

    # 1. 向量召回
    vec_hits: dict[str, dict] = {}
    vec_scores: dict[str, float] = {}
    try:
        rows = await repo.search_entities_by_vector(uid, qvec, recall_size)
        for r in rows:
            vec_hits[r["id"]] = r
            vec_scores[r["id"]] = float(r.get("score", 0.0))
    except Exception as e:
        logger.warning("记忆向量召回失败（降级仅全文）: %s", e)

    # 2. 全文召回（cjk 分词）
    ft_hits: dict[str, dict] = {}
    ft_scores: dict[str, float] = {}
    try:
        rows = await repo.search_entities_by_fulltext(uid, query, recall_size)
        for r in rows:
            ft_hits[r["id"]] = r
            ft_scores[r["id"]] = float(r.get("score", 0.0))
    except Exception as e:
        logger.warning("记忆全文召回失败: %s", e)

    # 2.5. Community 向量召回（复用 qvec，失败降级）
    comm_scores: dict[str, float] = {}
    comm_entity_ids: set[str] = set()
    try:
        comm_rows = await repo.search_communities_by_vector(uid, qvec, recall_size)
        for cr in comm_rows:
            cid = cr["id"]
            comm_scores[cid] = float(cr.get("score", 0.0))
        # 取命中社区的成员实体 id → 用于后续加权
        if comm_scores:
            all_candidate_ids = [r["id"] for r in vec_hits.values()] + [r["id"] for r in ft_hits.values()]
            if all_candidate_ids:
                comm_members = await repo.get_entity_community_context(uid, all_candidate_ids)
                # 构建 community_id → set[entity_id] 反向索引（仅对已在候选集中的实体）
                cid_to_entities: dict[str, set[str]] = {}
                for cm in comm_members:
                    c_id = cm.get("community_id")
                    e_id = cm.get("entity_id")
                    if c_id and e_id:
                        cid_to_entities.setdefault(c_id, set()).add(e_id)
                # 标记社区命中对应的实体
                for cid in comm_scores:
                    comm_entity_ids.update(cid_to_entities.get(cid, set()))
    except Exception as e:
        logger.warning("记忆社区向量召回失败（降级仅实体召回）: %s", e)

    if not vec_hits and not ft_hits:
        return []

    # 3. 归一化 + 加权融合
    all_hits = {**ft_hits, **vec_hits}

    # 3.5 精确模式（全局搜索）：纯语义余弦门控
    # Neo4j 向量索引返回的 score 即 cosine 相似度；只保留 ≥ 阈值的，按余弦排序、分数用余弦
    if min_vector_score is not None:
        kept = {
            eid: vec_scores[eid]
            for eid in all_hits
            if vec_scores.get(eid, 0.0) >= min_vector_score
        }
        if not kept:
            return []
        # Community boost in exact mode: 命中社区的实体微弱加权
        comm_n = _normalize(comm_scores)
        for eid in list(kept.keys()):
            if eid in comm_entity_ids:
                cid = all_hits[eid].get("community_id") or ""
                kept[eid] = kept[eid] + _COMMUNITY_WEIGHT * comm_n.get(cid, 0.0)
        ranked = _rank_memory_hits(
            all_hits,
            kept,
            top_k=top_k,
            min_confidence=min_confidence,
            use_reliability_score=use_reliability_score,
        )
        if not ranked:
            return []
        top_ids = [eid for eid, _, _ in ranked]
        try:
            await repo.bump_entity_access(uid, top_ids)
        except Exception as e:
            logger.warning("记忆检索命中回写失败（忽略）: %s", e)
        neighbor_rows = await repo.get_entity_neighbors(uid, top_ids)
        relations_by_entity: dict[str, list[dict]] = {eid: [] for eid in top_ids}
        for row in neighbor_rows:
            eid = row.get("entity_id")
            if eid in relations_by_entity and row.get("predicate"):
                relations_by_entity[eid].append({
                    "predicate": row.get("predicate"),
                    "object_name": row.get("object_name"),
                    "object_type": row.get("object_type"),
                    "source_text": row.get("source_text"),
                    "confidence": _float(row.get("confidence"), _DEFAULT_CONFIDENCE),
                    "importance": _float(row.get("importance"), 0.5),
                    "valid_at": row.get("valid_at"),
                    "invalid_at": row.get("invalid_at"),
                })
        # 取实体社区上下文（供结果附带社区名+摘要）
        comm_ctx: dict[str, dict | None] = {eid: None for eid in top_ids}
        try:
            comm_rows = await repo.get_entity_community_context(uid, top_ids)
            for cr in comm_rows:
                comm_ctx[cr["entity_id"]] = {
                    "id": cr.get("community_id"),
                    "name": cr.get("community_name"),
                    "summary": cr.get("community_summary"),
                }
        except Exception as e:
            logger.warning("取实体社区上下文失败（忽略）: %s", e)
        results: list[dict] = []
        for eid, score, reliability_score in ranked:
            src = all_hits[eid]
            results.append({
                "id": eid,
                "name": src.get("name"),
                "type": src.get("type"),
                "description": src.get("description"),
                "aliases": src.get("aliases") or [],
                "importance": round(float(src.get("importance", 0.5) or 0.5), 3),
                "confidence": round(_float(src.get("confidence"), _DEFAULT_CONFIDENCE), 3),
                "memory_layer": src.get("memory_layer") or "short_term",
                "score": round(score, 4),
                "reliability_score": round(reliability_score, 4),
                "community": comm_ctx.get(eid),
                "relations": relations_by_entity.get(eid, []),
            })
        return results

    vec_n = _normalize(vec_scores)
    ft_n = _normalize(ft_scores)
    comm_n = _normalize(comm_scores)
    fused: dict[str, float] = {}
    for eid in all_hits:
        base = _VECTOR_WEIGHT * vec_n.get(eid, 0.0) + _FULLTEXT_WEIGHT * ft_n.get(eid, 0.0)
        # Community 加权：实体所属社区被社区向量召回命中时给予微弱加成
        community_boost = 0.0
        if eid in comm_entity_ids:
            cid = all_hits[eid].get("community_id") or ""
            community_boost = _COMMUNITY_WEIGHT * comm_n.get(cid, 0.0)
        importance = float(all_hits[eid].get("importance", 0.5) or 0.5)
        score = base + community_boost + _IMPORTANCE_WEIGHT * importance
        if not use_reliability_score and (all_hits[eid].get("memory_layer") or "") == "long_term":
            score += _LONG_TERM_BONUS
        fused[eid] = score

    ranked = _rank_memory_hits(
        all_hits,
        fused,
        top_k=top_k,
        min_confidence=min_confidence,
        use_reliability_score=use_reliability_score,
    )
    top_ids = [eid for eid, _, _ in ranked]

    # 命中回写：access_count +1、last_access_at（失败不影响检索）
    try:
        await repo.bump_entity_access(uid, top_ids)
    except Exception as e:
        logger.warning("记忆检索命中回写失败（忽略）: %s", e)

    # 4. 一跳邻居关系遍历，拼上下文
    neighbor_rows = await repo.get_entity_neighbors(uid, top_ids)
    relations_by_entity: dict[str, list[dict]] = {eid: [] for eid in top_ids}
    for row in neighbor_rows:
        eid = row.get("entity_id")
        if eid in relations_by_entity and row.get("predicate"):
            relations_by_entity[eid].append({
                "predicate": row.get("predicate"),
                "object_name": row.get("object_name"),
                "object_type": row.get("object_type"),
                "source_text": row.get("source_text"),
                "confidence": _float(row.get("confidence"), _DEFAULT_CONFIDENCE),
                "importance": _float(row.get("importance"), 0.5),
            })

    # 取实体社区上下文（供结果附带社区名+摘要）
    comm_ctx: dict[str, dict | None] = {eid: None for eid in top_ids}
    try:
        comm_rows = await repo.get_entity_community_context(uid, top_ids)
        for cr in comm_rows:
            comm_ctx[cr["entity_id"]] = {
                "id": cr.get("community_id"),
                "name": cr.get("community_name"),
                "summary": cr.get("community_summary"),
            }
    except Exception as e:
        logger.warning("取实体社区上下文失败（忽略）: %s", e)

    results: list[dict] = []
    for eid, score, reliability_score in ranked:
        src = all_hits[eid]
        results.append({
            "id": eid,
            "name": src.get("name"),
            "type": src.get("type"),
            "description": src.get("description"),
            "aliases": src.get("aliases") or [],
            "importance": round(float(src.get("importance", 0.5) or 0.5), 3),
            "confidence": round(_float(src.get("confidence"), _DEFAULT_CONFIDENCE), 3),
            "memory_layer": src.get("memory_layer") or "short_term",
            "score": round(score, 4),
            "reliability_score": round(reliability_score, 4),
            "community": comm_ctx.get(eid),
            "relations": relations_by_entity.get(eid, []),
        })
    return results


def format_memory_context(results: list[dict]) -> str:
    """把检索结果拼成给 LLM 的记忆上下文文本（供问答 Agent 记忆工具复用）。
    已过期的关系标记 [已过期]，被取代的关系标记 [已更新]。
    同社区实体合并标注 【社区名】 前置行。
    """
    if not results:
        return ""
    # 按 community_id 分组（用于合并同社区标注）
    community_groups: dict[str, list[int]] = {}  # cid → [result_indices]
    for i, r in enumerate(results):
        comm = r.get("community")
        if comm and comm.get("id"):
            community_groups.setdefault(comm["id"], []).append(i)
    # 记录每个社区是否已输出标注行
    emitted: set[str] = set()
    lines: list[str] = []
    for i, r in enumerate(results):
        comm = r.get("community")
        cid = comm.get("id") if comm else None
        if cid and cid not in emitted and comm.get("name"):
            # 同社区多实体时合并为一个标注行（首个实体前输出）
            emitted.add(cid)
            peer_count = len(community_groups.get(cid, [1]))
            if peer_count > 1:
                lines.append(f"【{comm['name']}】（{peer_count} 条相关记忆）")
            else:
                lines.append(f"【{comm['name']}】")
        prefix = "- 待确认：" if _is_uncertain(r.get("confidence")) else "- "
        head = f"{prefix}{r['name']}（{r['type']}）：{r.get('description') or ''}".rstrip("：")
        lines.append(head)
        for rel in r.get("relations", []):
            obj = rel.get("object_name") or ""
            # 过期标记优先
            if _is_expired(rel.get("invalid_at")):
                status = " [已过期]"
            elif _is_uncertain(rel.get("confidence")):
                status = " [待确认]"
            else:
                status = ""
            rel_prefix = "    · "
            lines.append(f"{rel_prefix}{r['name']} {rel['predicate']} {obj}{status}")
    return "\n".join(lines)


__all__ = ["search_memory", "format_memory_context"]
