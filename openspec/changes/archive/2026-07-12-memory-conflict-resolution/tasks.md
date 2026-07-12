## 1. Phase 1: confidence max merge

- [x] 1.1 Fix ENTITY_SAVE Cypher: change `n.confidence = row.confidence` to CASE-based max pattern in `cypher_queries.py`
- [x] 1.2 Fix RELATION_SAVE Cypher: change `r.confidence = row.confidence` to CASE-based max pattern in `cypher_queries.py`
- [x] 1.3 Fix STATEMENT_SAVE Cypher: change confidence to CASE-based max pattern in `cypher_queries.py`
- [x] 1.4 Verify: test that writing confidence=0.3 does not overwrite existing confidence=1.0

## 2. Phase 2: temporal validity activation

- [x] 2.1 Update `extract_triplet.jinja2` prompt: instruct LLM to infer valid_at/invalid_at from statement semantics (use dialog_at as anchor, NULL when uncertain)
- [x] 2.2 Verify `orchestrator.py` passes `dialog_at_str` correctly to `extract_triplets_batch` for time anchor
- [x] 2.3 Update `ENTITY_NEIGHBORS` Cypher query to also return `valid_at` and `invalid_at` fields
- [x] 2.4 Update `searcher.py` `format_memory_context()` to mark expired relations with `[已过期]` prefix
- [x] 2.5 Update `searcher.py` `search_memory()` to apply 0.5x weight decay to expired relations in reliability score mode

## 3. Phase 2: RELATION conflict detection + SUPERSEDES edges

- [x] 3.1 Add `REL_SUPERSEDES` and `REL_CONTRADICTS` relationship type constants to `graph_models.py`
- [x] 3.2 Add `PREDICATE_MUTABILITY` dictionary to `ontology.py` with static/dynamic/semi-dynamic classification for each predicate
- [x] 3.3 Add `RELATION_FIND_SAME_PREDICATE` Cypher query to `cypher_queries.py`
- [x] 3.4 Add `RELATION_MARK_SUPERSEDED` Cypher query to `cypher_queries.py`
- [x] 3.5 Add `find_conflicting_relations()` and `mark_relation_superseded()` methods to `memory_graph_repository.py`
- [x] 3.6 Add conflict detection logic to `orchestrator.py` `run_extraction()`: before persist, check each new RelationEdge for same-predicate conflicts, auto-supersede dynamic predicates, lower confidence for static conflicts
- [x] 3.7 Update `ENTITY_NEIGHBORS` query to optionally filter out superseded relations (WHERE r.invalid_at IS NULL) or mark them in results
- [x] 3.8 Update `format_memory_context()` to mark superseded relations with `[已更新]`

## 4. Phase 3: Statement semantic dedup

- [x] 4.1 Add `STATEMENT_VECTOR_SIMILAR` Cypher query to `cypher_queries.py`
- [x] 4.2 Add `find_similar_statement()` method to `memory_graph_repository.py`
- [x] 4.3 Update `orchestrator.py` to persist statement embeddings during extraction (set `embedding` on StatementNode before save)
- [x] 4.4 Add `SEMANTICALLY_SIMILAR_TO` relationship constant to `graph_models.py`
- [x] 4.5 (Future: Celery beat task for async dedup — not in this change)

## 5. Phase 4: Reflection contradiction detection

- [x] 5.1 Update `reflect.jinja2` prompt: add contradiction detection section with `contradictions` array output schema
- [x] 5.2 Update `reflector.py` `run()`: parse `contradictions` from LLM output, auto-resolve `resolved=true` entries via `mark_relation_superseded()`, lower confidence for unresolved conflicts
- [x] 5.3 Add `STATEMENT_LOWER_CONFIDENCE` Cypher query to `cypher_queries.py` for pushing unresolved conflicts to review queue

## 6. Phase 4: Correction immune memory

- [x] 6.1 Add `CorrectionRecord` node label constant and model to `graph_models.py`
- [x] 6.2 Add `CORRECTION_RECORD_SAVE` and `CORRECTION_RECORD_CHECK` Cypher queries to `cypher_queries.py`
- [x] 6.3 Add `save_correction_record()` and `check_correction_record()` methods to `memory_graph_repository.py`
- [x] 6.4 Update `dedup.py` `merge_with_graph()`: check CorrectionRecord before creating new entities — skip deleted, auto-rename corrected, allow confirmed
- [x] 6.5 Update `memory_service.py` `confirm_entity()` to write CorrectionRecord(confirm)
- [x] 6.6 Update `memory_service.py` `correct_entity_with_reason()` to write CorrectionRecord(correct) with corrected_to
- [x] 6.7 Update `memory_service.py` `delete_entity_with_reason()` to write CorrectionRecord(delete)

## 7. Unit tests (pure in-memory, zero DB dependency)

- [x] 7.1 Create `api/tests/test_memory_conflict_resolution.py` with all unit tests below
- [x] 7.2 Test confidence max merge: verify `_merge_into` preserves higher confidence, `ENTITY_SAVE` CASE logic correctness
- [x] 7.3 Test temporal validity formatting: expired relations get `[已过期]` prefix, active relations don't
- [x] 7.4 Test relation conflict detection: same-predicate-different-target detected, dynamic auto-supersede, static pushed to review
- [x] 7.5 Test PREDICATE_MUTABILITY classification: each ontology predicate has correct mutability label
- [x] 7.6 Test statement semantic dedup: `find_similar_statement` filters by min_score, `STATEMENT_VECTOR_SIMILAR` query structure
- [x] 7.7 Test reflection contradiction parsing: `resolved=true` entries trigger auto-fix, `resolved=false` trigger confidence lowering
- [x] 7.8 Test correction immune memory: CorrectionRecord blocks re-extraction of deleted entities, auto-renames corrected entities, allows confirmed entities
- [x] 7.9 Run all unit tests: `cd api && uv run python -m unittest tests.test_memory_conflict_resolution -v`

## 8. Integration verification (manual, on dev Neo4j)

- [x] 8.1 Run lint: `cd api && uv run ruff check .`
- [x] 8.2 Verify Neo4j schema updates: run `ensure_graph_schema()` and check new constraints/indexes
- [x] 8.3 Integration test: simulate two extractions ("work in Beijing" then "moved to Shanghai") and verify SUPERSEDES edge created
- [x] 8.4 Integration test: delete an entity, re-extract same content, verify entity not re-created
- [x] 8.5 Integration test: verify confidence=1.0 human_verified entity keeps confidence after re-extraction with confidence=0.3
