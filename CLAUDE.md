# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 行为准则（八荣八耻）

1. **以认真查询为荣，以乱猜接口为耻** — 调用函数/组件前先查源文件，不凭记忆编造入参
2. **以寻求确认为荣，以模糊执行为耻** — 需求有歧义时停下来问，不脑补条件
3. **以人类确认为荣，以臆想业务为耻** — 业务逻辑不在上下文时直接求证，不擅自推导
4. **以复用现有为荣，以创造接口为耻** — 写新逻辑前全局搜索现存的 utils/helpers/components
5. **以主动测试为荣，以跳过验证为耻** — 代码产出后必须执行终端测试，跑不通不算完
6. **以遵循规范为荣，以破坏架构为耻** — 严格模仿项目的目录结构和命名习惯
7. **以诚实无知为荣，以乱猜理解为耻** — 看不懂的复杂逻辑直接说"不确定"
8. **以谨慎重构为荣，以盲目修改为耻** — 改 Bug 加功能时最小化改动范围，不夹带私货

## Project Overview

SoulChat is a personal AI knowledge base and memory assistant — multi-user, full-stack. Users build a semantic knowledge base from documents/images/web pages, the system automatically extracts structured memories into a knowledge graph, and an LLM Agent autonomously orchestrates knowledge base / memory / web search tools to answer questions.

## Development Commands

### Backend (Python/FastAPI, `api/`)

```bash
cd api

# Install dependencies (uses uv, not pip)
uv sync

# Lint
uv run ruff check .

# Run the API server (http://localhost:8000)
uv run python run.py

# Database migrations
uv run alembic revision --autogenerate -m "description"   # generate migration
uv run alembic upgrade head                                 # apply migrations

# Celery worker (Windows uses --pool=solo; Linux/macOS can omit and add --concurrency=N)
uv run celery -A app.celery_app.celery_app worker -l info -Q default,parse,memory,beat,research --pool=solo

# Celery beat (scheduled tasks)
uv run celery -A app.celery_app.celery_app beat -l info

# Run evaluations
uv run python -m eval.run_eval                        # full custom gold-set eval
uv run python -m eval.run_eval --benchmark cmteb-t2   # C-MTEB Chinese retrieval benchmark
uv run python -m eval.run_eval --benchmark hotpotqa   # HotpotQA multi-hop benchmark
uv run python -m eval.run_eval --reset                # clean re-run
uv run python -m eval.run_eval --only retrieval       # run a single eval task
```

### Frontend (React/TypeScript, `web/`)

```bash
cd web

npm install
npm run dev       # dev server at http://localhost:5173 (proxies /api → :8000)
npm run build     # type-check + production build
npm run lint      # ESLint
```

### Infrastructure (Docker)

```bash
# Start the four storage backends only (dev mode)
docker compose up -d postgres elasticsearch neo4j redis

# Check health
docker compose ps

# Health endpoint: http://localhost:8000/api/health (all four should be "ok")
```

## Architecture

### Storage Layer (4 backends)

| Backend | Purpose | Port |
|----------|---------|------|
| PostgreSQL 16 | Business data (users, documents, conversations, etc.) via SQLAlchemy 2.0 async | 5432 |
| Elasticsearch 8.17 | Vector + BM25 hybrid retrieval with IK Chinese tokenizer (custom-built image) | 9200 |
| Neo4j 5.26 | Memory knowledge graph — 4-layer provenance: Dialogue → Chunk → Statement → Entity | 7687 |
| Redis | Celery broker/result backend + general caching | 6379 |

### Backend Layered Architecture (`api/app/`)

All code follows a **strict one-way dependency**: `controller → service → repository → model/db`. No layer may skip or reverse this chain.

- **`controllers/`** — Route handlers. Thin: parse request, call service, return wrapped response.
- **`services/`** — Business logic. Orchestrates repositories + external calls. The largest files live here (e.g., `chat_service.py` at ~44KB, `group_chat_service.py` at ~49KB, `research_service.py` at ~25KB).
- **`repositories/`** — Data access for PostgreSQL (`*_repository.py`) and Neo4j (`neo4j/` subdirectory).
- **`models/`** — SQLAlchemy ORM models. Every business table has `user_id` for multi-tenant isolation.
- **`schemas/`** — Pydantic request/response models.
- **`core/`** — Cross-cutting subsystems:
  - **`core/agent/`** — Agent orchestration (see below)
  - **`core/rag/`** — RAG pipeline (chunking, ES indexing, hybrid search, document parsing)
  - **`core/memory/`** — Memory system (extraction, graph models, clustering, consolidation, reflection, retrieval)
  - **`core/llm/`** — LLM client factory + provider abstraction (supports OpenAI-compatible APIs)
  - **`core/storage/`** — File storage backends (local / Alibaba Cloud OSS)
  - **`core/emotion/`** — Valence-arousal emotion analysis
  - **`core/music/`** — Emotion-driven music recommendation
  - **`core/asr/`** — Speech recognition
- **`tasks/`** — Celery async tasks (parse, memory extraction, emotion analysis, music, beat scheduling, agent tasks)
- **`db/`** — Connection management for all four backends (`postgres.py`, `elastic.py`, `neo4j.py`, `redis.py`)

**File naming convention**: `xxx_model.py` / `xxx_repository.py` / `xxx_service.py` / `xxx_controller.py` / `xxx_schema.py`. Match these exactly when adding new features.

**API response format**: All endpoints return `{ code: 0, message: "ok", data: ... }`. Non-zero `code` indicates error.

### Agent Orchestration (`core/agent/orchestrator.py`)

Dual-path tool-calling loop that outputs a unified SSE event stream:

- **Strong models** (function calling capable): `bind_tools` + streaming tool loop. LLM natively decides which tool to call.
- **Weak models**: ReAct-style prompt-based fallback — parses `Action`/`Action Input` patterns from LLM text output.

Both paths emit standardized events: `tool_start`, `tool_result`, `token`, `final`. Citations are collected into an external list referenced after the loop ends. Max 5 tool iterations per turn.

### Agent Subsystems (within `core/agent/`)

- **`tools/`** — Tool registry, base tool class, builtin tools (KB search, memory, web, datetime, persona memory), MCP tool adapter, skill script executor
- **`tools/builtin/persona_memory.py`** — Agent 自主维护角色 MEMORY.md 工具（save_to_persona_memory）
- **`tools/skill_executor.py`** — Skill 脚本执行器（subprocess 调用，stdin/stdout JSON）
- **`tools/mcp/`** — MCP 工具加载：SSE/Streamable HTTP，缓存，角色级过滤
- **`research/`** — Deep research pipeline: planner → retriever → distiller → reflector → curator → writer. Multi-stage with reflection-based gap-filling.
- **`loop/`** — Verifier Loop (v0.0.5): LLM-as-judge quality verification with 6-dim rubric scoring, patch/rewrite repair, state persisted to DB for resumability.
- **`tracing/`** — OpenTelemetry GenAI-compliant traces: spans for every tool call / LLM call / retrieval / writing. Cost tracking per model per call. Async batch recorder.

### Memory System (`core/memory/`)

Neo4j-based 4-layer provenance graph:
```
Dialogue (source) → Chunk (segmented turn) → Statement (atomic claim) → Entity (extracted node)
```
On top of this are: Entity-to-Entity `RELATION` edges (triples), `Event` nodes (with timestamps for timeline), `Community` clusters, and `Insight` nodes (from reflection engine).

Subsystems: `extraction/`, `preprocessing/`, `clustering/`, `consolidation/`, `reflection/`, `retrieval/`.

Memory has a **human feedback loop**: entities below confidence threshold can be confirmed/corrected/deleted via UI; corrections stored in `memory_corrections` table; `human_verified` entities get boosted recall weight.

### Persona = Agent（角色即 Agent）

角色从"提示词模板"升级为完整 Agent 配置，`agent_personas` 表承载所有配置：
- **人设层**: system_prompt / temperature / memory_text (MEMORY.md)
- **工具层**: enable_knowledge / enable_memory / enable_web_search / enable_mcp / tool_keys
- **知识库**: kb_ids（角色默认检索范围）
- **技能**: 角色下所有 enabled=true 的 Skill 自动挂载，提示词注入 system prompt
- **MCP**: mcp_server_ids 角色级选用，空=全部可用
- **上下文**: conversation_scope ('shared'/'isolated'), context_window
- **风格**: human_mode / show_avatar / enable_active_recall / enable_cross_session

Skills 归属于 Persona（`skills.persona_id`），支持 .soulskill.zip 导入（SKILL.md + scripts/）。

### MCP 配置（`core/agent/tools/mcp/`）

MCP Server 按用户配置，角色通过 `mcp_server_ids` 选用。支持 SSE / Streamable HTTP 传输。
- `loader.py`: build_mcp_tools / open_mcp_tools，带角色级过滤和进程级缓存
- `connection.py`: 连接构建 + SSRF 防护（localhost 白名单放行）
- `test_mcp_server.py`: 本地测试用 MCP Server（FastMCP + SSE, port 8765）

### Celery Multi-Queue Setup (`celery_app.py`)

Four queues with clear separation:
- **`parse`** — Document parsing, image description, music processing
- **`memory`** — Memory triplet extraction, emotion analysis
- **`beat`** — Lightweight scheduling heartbeat + daily review generation (must not be blocked)
- **`research`** — Heavy deep research execution (isolated to avoid blocking heartbeat)

Celery tasks use **independent DB engines with NullPool** (`create_task_engine()` in `db/postgres.py`) because each task runs in a fresh asyncio event loop.

### Frontend Architecture (`web/src/`)

- **Framework**: React 18 + TypeScript + Vite
- **UI**: Ant Design 5
- **State**: Zustand stores (`authStore`, `musicStore`, `knowledgeBaseStore`, `chatHeaderStore`, etc.)
- **Routing**: React Router v7, `App.tsx` defines all routes under `MainLayout` with `RequireAuth` guard
- **API client**: Axios with interceptors — attaches JWT Bearer token, unwraps `{ code, message, data }` envelope, redirects to `/login` on 401
- **Key pages**: `ChatPage.tsx` (single + group chat, ~45KB), `GroupChatPage.tsx` (~61KB), `MemoryPage.tsx` (~46KB), `HomePage.tsx` (dashboard), `ResearchPage.tsx` (deep research), `TracesPage.tsx` (agent tracing), `GraphPage.tsx` (AntV X6 knowledge graph visualization)
- **Path alias**: `@/` maps to `src/`

### Configuration

- **`api/.env`** — Pydantic-settings reads all config from here. Must set `JWT_SECRET` and `FERNET_KEY` (for API key encryption at rest).
- **`.env`** (root) — Docker Compose variables for storage passwords.
- Model configuration is **user-facing, stored in DB** — users add their own LLM providers (OpenAI-compatible) via the Settings UI. Each model has a type: `chat`, `embedding`, `rerank`, `websearch`, `multimodal`, `verifier`. The system resolves models by type + "is_default" flag.

### Evaluation System (`api/eval/`)

Custom gold sets for extraction/dedup/retrieval/memory tasks, plus public benchmarks:
- **C-MTEB T2Retrieval** (Chinese retrieval, nDCG@10 = 0.98)
- **HotpotQA** (multi-hop QA, EM = 62%)

Entry: `run_eval.py` with `--benchmark`, `--reset`, `--skip-setup`, `--teardown`, `--only` flags.

### Skill 格式（.soulskill.zip）

```
my-skill.soulskill.zip
├── SKILL.md          ← YAML frontmatter + Markdown 提示词
└── scripts/          ← 可选，工具脚本（stdin JSON → stdout JSON）
```

SKILL.md frontmatter: `name`(必填), `description`, `icon`, `tool_keys`/`allowed-tools`, `tools`, `triggers`。
兼容 Claude Code / Cursor / Continue 等主流 SKILL.md 格式。

### 本地 MCP 测试

```bash
cd api && uv run python test_mcp_server.py  # 启动在 http://localhost:8765/sse
```

提供 weather / text_stats / roll_dice / sha256 / unix_time 等测试工具。

## Key Development Notes

- **Windows caveats**: Celery worker must use `--pool=solo` (prefork has permission issues on Windows). Paths use forward slashes.
- **ES startup**: The custom ES image (with IK plugin) builds on first `docker compose up`. ES takes 30-60s to become healthy.
- **Multi-tenant isolation**: All business DB tables include `user_id`. API keys stored encrypted with Fernet.
- **Sensitive values**: `api/.env` contains `JWT_SECRET` and `FERNET_KEY` — generate with `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **LLM provider pattern**: `core/llm/client.py` contains a factory that builds LangChain `ChatOpenAI` instances from DB-stored model configs. Provider detection is in `provider.py`.
- **Prompt files**: Agent and memory subsystems store prompts as `.txt` files in `prompts/` subdirectories, rendered with Jinja2 via local `prompt_renderer.py` modules.
