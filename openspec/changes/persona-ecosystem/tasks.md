# Tasks: Persona Ecosystem (成长系统 + 日记 + 市场)

## 1. Database Foundation (数据底座)

- [x] 1.1 Create Alembic migration: 5 new tables (persona_growth, persona_milestones, persona_diaries, persona_market_listings, persona_market_reviews) + 3 new columns on agent_personas (cloned_from_id, clone_count, is_listed)
- [x] 1.2 Run migration and verify: `uv run alembic upgrade head` — all tables and indexes exist
- [x] 1.3 Create ORM model: `api/app/models/persona_growth_model.py`
- [x] 1.4 Create ORM model: `api/app/models/persona_milestone_model.py`
- [x] 1.5 Create ORM model: `api/app/models/persona_diary_model.py`
- [x] 1.6 Create ORM model: `api/app/models/persona_market_models.py` (MarketListing + MarketReview)
- [x] 1.7 Add 3 columns to `api/app/models/agent_persona_model.py`

## 2. Core Persona Subsystem (核心引擎)

- [x] 2.1 Create `api/app/core/persona/__init__.py`
- [x] 2.2 Create `api/app/core/persona/level_config.py` — level thresholds table (1-50), XP earning rules, daily cap
- [x] 2.3 Create `api/app/core/persona/xp_engine.py` — `calculate_xp_gain()`, `check_level_up()`, `compute_intimacy()`, `update_consecutive_days()`
- [x] 2.4 Create `api/app/core/persona/trait_config.py` — 7 traits with key, name, required_level, prompt_instruction
- [x] 2.5 Create `api/app/core/persona/milestone_detector.py` — 7 milestone type detectors, LLM description generator
- [x] 2.6 Create `api/app/core/persona/diary_writer.py` — `collect_daily_context()`, `generate_diary()`

## 3. Repositories (数据访问层)

- [x] 3.1 Create `api/app/repositories/persona_growth_repository.py` — `get_or_create()`, `upsert()`, `get_by_pair()`
- [x] 3.2 Create `api/app/repositories/persona_diary_repository.py` — `list_by_user()`, `get_by_id()`, `mark_read()`, `get_unread_count()`, `exists_for_date()`
- [x] 3.3 Create `api/app/repositories/persona_market_repository.py` — `list_active()`, `get_by_id()`, `create_listing()`, `update_listing()`, `add_review()`, `get_reviews()`, `increment_downloads()`

## 4. Growth System Backend (成长系统后端)

- [x] 4.1 Create `api/app/services/persona_growth_service.py` — `record_interaction()`, `get_growth()`, `list_milestones()`
- [x] 4.2 Integrate growth recording into `api/app/services/chat_service.py` `_run_chat_turn_bg()` — call `record_interaction()` after message persist, via `asyncio.create_task()`
- [x] 4.3 Integrate trait injection into `chat_service._compose_system_prompt()` — append unlocked trait instructions
- [x] 4.4 Add `growth_summary` field to `AgentPersonaService.to_out_dict()` — include xp, level, intimacy, unlocked_traits when persona_id and user_id are both known
- [x] 4.5 Create `api/app/controllers/persona_growth_controller.py` — `GET /personas/{persona_id}/growth`, `GET /personas/{persona_id}/milestones`
- [x] 4.6 Register growth routes in `api/app/controllers/router.py`

## 5. Growth System Frontend (成长系统前端)

- [x] 5.1 Create `web/src/api/personaGrowth.ts` — `getGrowth(personaId)`, `getMilestones(personaId)`
- [x] 5.2 Create `web/src/stores/personaGrowthStore.ts` — Zustand store for caching growth data
- [x] 5.3 Create `web/src/components/persona/GrowthPanel.tsx` — XP progress bar, level badge, intimacy ring chart, milestones timeline, unlocked traits display
- [x] 5.4 Modify `web/src/pages/agent/PersonaEditModal.tsx` — add "成长" Tab containing GrowthPanel
- [x] 5.5 Modify `web/src/api/personas.ts` — add growth_summary to Persona type

## 6. Diary System Backend (日记系统后端)

- [x] 6.1 Create `api/app/services/persona_diary_service.py` — `list_diaries()`, `get_diary()`, `mark_read()`, `get_unread_count()`
- [x] 6.2 Create `api/app/tasks/persona_diary.py` — `generate_persona_diaries` Celery task with user pagination, per-persona diary generation using `diary_writer`
- [x] 6.3 Register diary task in `api/app/celery_app.py` — add to beat_schedule at 23:00, add task route to "beat" queue
- [x] 6.4 Create `api/app/controllers/persona_diary_controller.py` — `GET /diaries`, `GET /diaries/unread-count`, `PUT /diaries/{id}/read`
- [x] 6.5 Register diary routes in `api/app/controllers/router.py`

## 7. Diary System Frontend (日记系统前端)

- [x] 7.1 Create `web/src/api/personaDiary.ts` — `listDiaries()`, `getUnreadCount()`, `markRead()`
- [x] 7.2 Create `web/src/components/diary/DiaryCard.tsx` — persona avatar, date, mood icon, title, content preview, read status
- [x] 7.3 Create `web/src/pages/DiaryPage.tsx` — persona Tab filter, date-grouped diary list, unread badge, loading skeleton
- [x] 7.4 Modify `web/src/pages/HomePage.tsx` — add "今日日记" card with unread count badge
- [x] 7.5 Modify `web/src/layouts/MainLayout.tsx` — add diary nav entry in sidebar
- [x] 7.6 Modify `web/src/App.tsx` — add `/diaries` route with lazy loading

## 8. Marketplace Backend (市场后端)

- [x] 8.1 Create `api/app/schemas/persona_market_schema.py` — PublishRequest, ListingsResponse, ReviewRequest, etc.
- [x] 8.2 Create `api/app/services/persona_market_service.py` — `publish()`, `unpublish()`, `update_listing()`, `list_marketplace()`, `get_detail()`, `import_persona()`, `add_review()`
- [x] 8.3 Create `api/app/controllers/persona_market_controller.py` — marketplace browsing routes (no auth required for browse), import/review routes (auth required)
- [x] 8.4 Add publish/unpublish endpoints to `api/app/controllers/agent_persona_controller.py` — `POST /personas/{persona_id}/publish`
- [x] 8.5 Register market routes in `api/app/controllers/router.py`

## 9. Marketplace Frontend (市场前端)

- [x] 9.1 Create `web/src/api/personaMarket.ts` — `listMarket()`, `getDetail()`, `importPersona()`, `addReview()`
- [x] 9.2 Create `web/src/components/market/PersonaMarketCard.tsx` — icon, name, description, tags, rating stars, download count, "一键导入" button
- [x] 9.3 Create `web/src/components/market/PersonaMarketDetailModal.tsx` — full persona preview (truncated system_prompt), rating stats, review list, import button
- [x] 9.4 Create `web/src/components/market/PublishPersonaModal.tsx` — market name/description form, tag picker, icon selector, preview card
- [x] 9.5 Create `web/src/pages/MarketPage.tsx` — search bar, tag filter chips, sort selector (popular/newest/rating), card grid, pagination
- [x] 9.6 Modify `web/src/pages/agent/PersonaEditModal.tsx` — add "发布到市场" button triggering PublishPersonaModal
- [x] 9.7 Modify `web/src/App.tsx` — add `/market` route with lazy loading

## 10. Cross-System Integration & Polish (联动与打磨)

- [x] 10.1 Diary generation reads growth level to control insight depth (Lv.1-5 surface only, Lv.10+ deep insights)
- [ ] 10.2 Marketplace listing cards show aggregated growth stats from seller ("角色平均成长到 Lv.X") — v2
- [x] 10.3 Verify imported persona starts with fresh growth (XP=0, Lv.1) and independent diary
- [x] 10.4 Add level-up animation in GrowthPanel (CSS transition on XP bar)
- [x] 10.5 Add responsive layout for DiaryPage and MarketPage on mobile
- [x] 10.6 Add loading skeletons for DiaryPage, MarketPage, and GrowthPanel

## 11. Testing

- [ ] 11.1 Write unit tests for `xp_engine.py` — verify XP calculation for all scenario types, level thresholds, daily cap
- [ ] 11.2 Write unit tests for `milestone_detector.py` — verify each milestone type triggers correctly
- [ ] 11.3 Write unit tests for `diary_writer.py` — verify context collection and prompt assembly
- [ ] 11.4 Write integration test for growth recording in chat flow — mock chat → verify growth record updated
- [ ] 11.5 Write integration test for marketplace flow — publish → browse → import → verify clone
- [ ] 11.6 Run `cd api && uv run ruff check .` and fix any issues
- [x] 11.7 Run `cd web && npm run build` and verify no TypeScript errors
