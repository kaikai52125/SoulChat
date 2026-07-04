# SoulChat（SoulChat）项目学习计划

> 目标：从零开始，深入掌握 SoulChat 项目的技术栈、架构设计和核心功能实现。

---

## 学习前准备

### 你需要提前了解的背景知识
- Python 基础（能看懂函数、类、装饰器即可）
- 数据库基础概念（知道"表"、"查询"、"索引"是什么）
- 命令行基础（会用 `cd`、`ls`、`docker` 命令）

### 你的环境
- 项目路径：`d:\大模型学习\项目\SoulChat`
- 本文档会假设你在这个目录下执行所有命令

---

## 阶段一：Docker 容器化基础 + 项目跑起来

> **目标**：理解 Docker 是什么、为什么用、以及把 SoulChat 的所有服务成功跑起来。

### 1.1 Docker 核心概念入门

**学习内容：**

| 概念 | 一句话解释 | 类比 |
|------|-----------|------|
| **镜像 (Image)** | 一个打包好的"模板"，包含运行程序所需的一切（代码、依赖、系统库） | 类似虚拟机的 ISO 安装盘 |
| **容器 (Container)** | 镜像的"运行实例"，一个隔离的轻量级沙箱 | 类似用 ISO 装好的一台虚拟机（但轻得多） |
| **Docker Compose** | 用 YAML 文件定义和启动多个容器的工具 | 类似一键启动整套微服务的脚本 |
| **Volume** | 持久化存储，容器删了数据还在 | 类似虚拟机的虚拟硬盘 |
| **端口映射** | 把容器内的端口暴露到宿主机 | `"5432:5432"` = 本机5432 → 容器5432 |

### 1.2 阅读关键文件

打开 [docker-compose.yml](docker-compose.yml)，对照下面的架构图理解：

```
┌─────────────────────────────────────────────────────┐
│                    Docker 环境                        │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │ postgres │  │   es     │  │  neo4j   │  │redis │ │
│  │  :5432   │  │  :9200   │  │:7474/7687│  │ :6379│ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──┬───┘ │
│       │              │              │           │     │
│       └──────────────┼──────────────┼───────────┘     │
│                      ▼              ▼                  │
│               ┌─────────────┐  ┌──────────┐          │
│               │  api :8000  │  │ worker   │          │
│               │  (FastAPI)  │  │ (Celery) │          │
│               └──────┬──────┘  └──────────┘          │
│                      │                                │
│               ┌──────▼──────┐                         │
│               │ web :5173   │                         │
│               │ (React+NGX) │                         │
│               └─────────────┘                         │
└─────────────────────────────────────────────────────┘
```

### 1.3 动手：启动项目

```bash
# 步骤1：确认 Docker 已安装
docker --version
docker compose version

# 步骤2：复制环境变量文件
copy .env.example .env

# 步骤3：构建并启动所有服务（首次需下载镜像，可能较慢）
docker compose up -d

# 步骤4：查看服务状态
docker compose ps

# 步骤5：查看各组件的日志（开多个终端分别观察）
docker compose logs -f api        # API 服务日志
docker compose logs -f worker     # 后台任务日志
docker compose logs -f postgres   # 数据库日志
```

**预期结果**：浏览器访问 `http://localhost:5173` 看到 SoulChat 前端页面。

### 1.4 Q&A 检验

1. **docker-compose.yml 中 `depends_on` 和 `healthcheck` 分别做什么？为什么 api 的 depends_on 里 postgres/es/neo4j 都有 `condition: service_healthy`？**

2. **Volume `pg_data:/var/lib/postgresql/data` 的含义是什么？如果你执行 `docker compose down -v` 会发生什么？**

3. **api 服务的 environment 里 `POSTGRES_HOST: postgres`，这个 `postgres` 是什么？为什么不是 `localhost`？**

4. **Celery worker 和 beat 的区别是什么？看 docker-compose.yml 的 command，它们分别启动了什么东西？**

---

## 阶段二：数据存储层 —— 四种存储各司其职

> **目标**：理解 PostgreSQL、Elasticsearch、Neo4j、Redis 各自在这个项目中扮演什么角色，以及它们是如何配合的。

### 2.1 四种存储的角色

| 存储 | 角色 | 关键代码 |
|------|------|----------|
| **PostgreSQL** | 业务数据主库（用户、文档、对话、配置...） | [api/app/db/postgres.py](api/app/db/postgres.py) |
| **Elasticsearch** | 文档全文检索 + 向量相似度搜索 | [api/app/db/elastic.py](api/app/db/elastic.py) |
| **Neo4j** | 知识图谱（实体-关系、记忆溯源） | [api/app/db/neo4j.py](api/app/db/neo4j.py) |
| **Redis** | 缓存 + Celery 消息队列 | [api/app/db/redis.py](api/app/db/redis.py) |

### 2.2 动手实践

**任务2.2.1：直接连接各存储，感受它们的不同**

```bash
# 1. PostgreSQL —— 用 psql 客户端连接
#    (如果没有 psql，可以用 docker exec 进入容器)
docker exec -it soulchat-postgres psql -U soulchat -d soulchat
# 进去后试试：
\d                    # 列出所有表
\d users              # 查看 users 表结构
SELECT username, email FROM users;  # 查询用户
\q                    # 退出

# 2. Elasticsearch —— 查看索引
curl http://localhost:9200/_cat/indices?v
curl http://localhost:9200/soulchat_chunks/_mapping | python -m json.tool

# 3. Neo4j —— 浏览器访问图谱
# 打开 http://localhost:7474
# 用户名 neo4j，密码 soulchatneo4j
# 执行：MATCH (n) RETURN n LIMIT 25

# 4. Redis —— 查看 key
docker exec -it soulchat-redis redis-cli
# 进去后试试：
KEYS *               # 列出所有 key
SELECT 1             # 切换到 DB 1（Celery broker）
KEYS *
```

**任务2.2.2：边操作数据库边追踪代码**

以"注册用户"为例，追踪数据如何写入 PostgreSQL：
1. 前端发送注册请求 → 看 [web/src/api/](web/src/api/) 中的 auth 相关请求
2. 后端路由 → 看 [api/app/controllers/auth_controller.py](api/app/controllers/auth_controller.py)
3. 业务逻辑 → 看 [api/app/services/auth_service.py](api/app/services/auth_service.py)
4. 数据写入 → 看 [api/app/repositories/](api/app/repositories/) 和 [api/app/models/user_model.py](api/app/models/user_model.py)

### 2.3 Q&A 检验

1. **为什么一个项目需要 4 种不同的存储？能不能只用 PostgreSQL？每种存储分别适合什么场景？**

2. **Elasticsearch 里的 "向量检索" 和普通的关键词搜索有什么区别？为什么 RAG 系统要用向量检索？**

3. **Neo4j 的"图"和 PostgreSQL 的表有什么本质区别？什么情况下用图数据库比关系型数据库更好？**

4. **Redis 在 docker-compose.yml 中被挂了 3 个 DB（0/1/2），分别做什么？为什么 Celery 需要独立的 DB？**

---

## 阶段三：后端架构 —— FastAPI 分层设计

> **目标**：理解 API 项目的四层架构（Controller → Service → Repository → Model），掌握 FastAPI 的核心概念。

### 3.1 四层架构详解

```
用户请求
  │
  ▼
┌──────────────────────────────────────────────┐
│  Controller (路由层)                          │
│  - 定义 URL 路径和 HTTP 方法                  │
│  - 参数校验（Pydantic Schema）                │
│  - 只做"转发"，不做业务逻辑                    │
│  - 例：auth_controller.py                     │
└──────────────┬───────────────────────────────┘
               ▼
┌──────────────────────────────────────────────┐
│  Service (业务逻辑层)                          │
│  - 核心业务逻辑                                │
│  - 调用多个 Repository 协调数据操作            │
│  - 调用外部服务（LLM、RAG 等）                 │
│  - 例：auth_service.py                        │
└──────────────┬───────────────────────────────┘
               ▼
┌──────────────────────────────────────────────┐
│  Repository (数据访问层)                       │
│  - 封装数据库操作（CRUD）                      │
│  - 不包含业务逻辑，只做数据存取                │
│  - 例：user_repository.py                     │
└──────────────┬───────────────────────────────┘
               ▼
┌──────────────────────────────────────────────┐
│  Model (数据模型层)                            │
│  - ORM 模型定义（SQLAlchemy）                  │
│  - 数据库表结构映射                            │
│  - 例：user_model.py                          │
└──────────────┬───────────────────────────────┘
               ▼
           数据库
```

### 3.2 核心概念速查

| 概念 | 是什么 | 在项目中的体现 |
|------|--------|---------------|
| **FastAPI** | 异步 Python Web 框架 | [api/app/main.py](api/app/main.py) |
| **Pydantic** | 数据校验库 | [api/app/schemas/](api/app/schemas/) |
| **SQLAlchemy** | Python ORM（对象-关系映射） | [api/app/models/](api/app/models/) |
| **Alembic** | 数据库迁移工具 | [api/migrations/](api/migrations/) |
| **JWT** | 无状态的用户认证令牌 | [api/app/core/security.py](api/app/core/security.py) |
| **Celery** | 异步任务队列 | [api/app/celery_app.py](api/app/celery_app.py) |
| **Depends** | FastAPI 依赖注入 | [api/app/core/dependencies.py](api/app/core/dependencies.py) |

### 3.3 动手：追踪一个完整的 API 请求

**选一个简单的功能来追踪**：获取当前用户信息 `GET /api/auth/me`

```bash
# 1. 先注册一个用户（或直接用已有账号登录获取 token）
# 2. 查看 API 文档（FastAPI 自动生成）
#    浏览器打开 http://localhost:8000/api/docs
# 3. 在 Swagger 页面直接测试 API
```

**代码追踪顺序**：

1. [api/app/main.py](api/app/main.py) → 找到 `app.include_router(auth_router)` 这行
2. [api/app/controllers/auth_controller.py](api/app/controllers/auth_controller.py) → 找到 `/me` 路由
3. [api/app/core/dependencies.py](api/app/core/dependencies.py) → 看 `get_current_user` 怎么从 token 拿到用户的
4. [api/app/core/security.py](api/app/core/security.py) → 看 JWT 解码逻辑

### 3.4 Q&A 检验

1. **为什么要分 Controller / Service / Repository 三层？如果所有逻辑都写在 Controller 里会有什么问题？**

2. **Pydantic Schema 和 SQLAlchemy Model 有什么区别？为什么需要两套？**

3. **`Depends(get_current_user)` 做了什么？如果没有 JWT 验证，系统会有什么安全风险？**

4. **看 response.py 中的统一响应格式 `{ code, message, data }`，这样设计有什么好处？**

---

## 阶段四：前端架构 —— React + TypeScript + Ant Design

> **目标**：理解前端项目结构、状态管理和与后端的通信方式。

### 4.1 前端技术栈

| 技术 | 作用 |
|------|------|
| **React 18** | UI 框架，组件化思想 |
| **TypeScript** | 给 JavaScript 加类型约束 |
| **Ant Design** | 企业级 UI 组件库（按钮、表单、表格等） |
| **Vite** | 构建工具（开发热更新、生产打包） |
| **Zustand** | 轻量级状态管理 |
| **Axios** | HTTP 请求库 |

### 4.2 动手

1. 打开浏览器 F12 → Network 标签
2. 在 SoulChat 前端登录，观察 Network 中 `/api/auth/login` 请求的 Request/Response
3. 创建知识库，观察调用了哪些 API
4. 看 [web/src/api/](web/src/api/) 目录，了解前端如何组织 API 调用

### 4.3 Q&A 检验

1. **Zustand 是做什么的？和 React 自带的 useState 有什么区别？**

2. **在 Network 中观察到登录成功后 Response 返回了什么？前端把这些信息存在哪里了？**

---

## 阶段五：核心功能一 —— RAG 知识库系统

> **目标**：深入理解"文档上传 → 解析分块 → 向量化存储 → 语义检索 → LLM 回答"这一完整链路。

### 5.1 RAG 核心流程

```
上传文档 (PDF/Word/MD/TXT)
  │
  ▼
文档解析 (提取文本)          ← 看 rag/parser/
  │
  ▼
文本分块 (chunking)          ← 看 rag/splitter/
  │  父块(parent) + 子块(child)
  ▼
向量化 (embedding)           ← LLM 将文本转为 1024 维向量
  │
  ▼
存入 Elasticsearch           ← 向量 + BM25 双路索引
  │
  ▼
用户提问 → 向量化 → ES 混合检索 → 召回相关块
  │
  ▼
LLM 结合召回的上下文生成回答  ← 带引用溯源
```

### 5.2 关键代码路径

| 步骤 | 关键文件 |
|------|----------|
| 文档上传 | [api/app/controllers/document_controller.py](api/app/controllers/document_controller.py) |
| 异步解析 | [api/app/tasks/parse_tasks.py](api/app/tasks/parse_tasks.py) |
| 分块策略 | [api/app/core/rag/splitter.py](api/app/core/rag/splitter.py) |
| 向量化索引 | [api/app/core/rag/indexer.py](api/app/core/rag/indexer.py) |
| 混合检索 | [api/app/core/rag/retriever.py](api/app/core/rag/retriever.py) |
| 问答编排 | [api/app/services/chat_service.py](api/app/services/chat_service.py) |

### 5.3 动手测试 + 看日志

```bash
# 1. 监控日志（开多个终端）
docker compose logs -f api      # 看 API 请求
docker compose logs -f worker   # 看文档解析任务
docker compose logs -f es       # 看 ES 索引操作

# 2. 在前端操作：
#    - 创建一个知识库
#    - 上传一个 PDF 文档
#    - 观察 worker 日志中文档解析过程
#    - 等解析完成后，在知识库中提问
#    - 观察 api 日志中的检索和 LLM 调用

# 3. 验证 ES 索引：
curl http://localhost:9200/soulchat_chunks/_count
curl -X POST "http://localhost:9200/soulchat_chunks/_search" \
  -H "Content-Type: application/json" \
  -d '{"query": {"match_all": {}}, "size": 3}' | python -m json.tool
```

### 5.4 Q&A 检验

1. **为什么要把文档切分成小块（chunk）？直接检索整个文档不行吗？**

2. **为什么有"父子块"的设计？父块和子块分别有什么作用？**

3. **混合检索（hybrid search）结合了哪两种检索方式？为什么比单一检索更好？**

4. **上传一个 PDF 后，数据分别写入了哪些存储？（提示：PostgreSQL 存元数据，ES 存分块）**

---

## 阶段六：核心功能二 —— 记忆系统与知识图谱

> **目标**：理解记忆的"萃取 → 去重 → 图谱构建 → 社区聚类 → 反思"这一完整生命周期。

### 6.1 记忆系统架构

```
对话消息
  │
  ▼
┌──────────────────────────┐
│ 1. 记忆萃取 (extraction) │  ← LLM 从对话中提取三元组 (主语-谓词-宾语)
│    LLM 提取：实体、关系、  │     以及重要度、情感等信息
│    事件、语句              │
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│ 2. 去重 + 合并            │  ← 两层去重：完全匹配 + 语义相似
│    避免重复记忆           │
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│ 3. 图谱存储 (Neo4j)       │  ← 四层结构：
│    Dialogue → Chunk →     │     Dialogue → Chunk → Statement → Entity
│    Statement → Entity     │     实体之间用 RELATION 连接
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│ 4. 社区聚类 (community)   │  ← 类似社交网络找"圈子"
│    发现相关实体群          │     基于图谱拓扑结构
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│ 5. 反思 (reflection)     │  ← LLM 对社区生成高层洞察
│    从具体事实抽象出认知    │     "用户喜欢...因为..."
└──────────────────────────┘
```

### 6.2 关键代码路径

| 步骤 | 关键文件 |
|------|----------|
| 记忆萃取 | [api/app/core/memory/extractor.py](api/app/core/memory/extractor.py) |
| 去重 | [api/app/core/memory/dedup.py](api/app/core/memory/dedup.py) |
| 图谱操作 | [api/app/repositories/neo4j/](api/app/repositories/neo4j/) |
| 社区聚类 | [api/app/core/memory/clustering.py](api/app/core/memory/clustering.py) |
| 反思引擎 | [api/app/core/memory/reflection.py](api/app/core/memory/reflection.py) |
| 记忆召回 | [api/app/core/memory/recall.py](api/app/core/memory/recall.py) |

### 6.3 动手测试

```bash
# 1. 在前端与 AI 进行多轮对话（至少 10+ 轮），聊聊你的个人信息、偏好等
#    例如："我叫张三，我在北京工作，喜欢打篮球和游泳，我的猫叫小花"

# 2. 观察 worker 日志，看记忆萃取任务
docker compose logs -f worker | grep -i memory

# 3. 打开 Neo4j 浏览器 http://localhost:7474 查看图谱
#    执行以下 Cypher 查询：
MATCH (e:Entity) RETURN e LIMIT 25                    # 查看实体
MATCH (e1:Entity)-[r:RELATION]->(e2:Entity) RETURN e1, r, e2 LIMIT 50  # 查看关系
MATCH (e:Entity) WHERE e.name CONTAINS '张三' RETURN e # 查特定实体

# 4. 第二天（或手动触发）查看反思结果
#    在 Neo4j 中查：
MATCH (i:Insight) RETURN i.content LIMIT 10
```

### 6.4 Q&A 检验

1. **"三元组"（subject-predicate-object）是什么？举个例子，从"我在北京工作"这句话能提取出什么三元组？**

2. **为什么需要"去重"？如果不去重，图谱会变成什么样？**

3. **Neo4j 的四层结构（Dialogue → Chunk → Statement → Entity）是逐步抽象的，每一层分别代表什么粒度？为什么需要分层？**

4. **"社区聚类"和"反思"这两个步骤的目的是什么？如果不做这两步，记忆系统缺失了什么能力？**

---

## 阶段七：核心功能三 —— Agent 智能体系统

> **目标**：理解 LLM Agent 的"思考 → 选择工具 → 调用工具 → 综合回答"循环。

### 7.1 Agent 工作流

```
用户提问："我上次聊到的那个项目有什么进展？"
  │
  ▼
┌────────────────────────────────────────────┐
│ Agent 编排器 (Orchestrator)                 │
│                                            │
│ 思考：用户问的是"项目进展"，需要查记忆       │
│   ↓                                        │
│ 决策：调用 memory_tool 查询记忆             │
│   ↓                                        │
│ 观察：memory_tool 返回了...                 │
│   ↓                                        │
│ 思考：还需要查知识库看有没有相关文档         │
│   ↓                                        │
│ 决策：调用 kb_tool 检索知识库               │
│   ↓                                        │
│ 观察：kb_tool 返回了...                     │
│   ↓                                        │
│ 思考：信息足够了，可以综合回答              │
│   ↓                                        │
│ 输出：流式 SSE 回答给用户                   │
└────────────────────────────────────────────┘
```

### 7.2 可用工具

| 工具 | 功能 | 用什么存储 |
|------|------|-----------|
| 知识库搜索 | 语义搜索用户上传的文档 | Elasticsearch |
| 记忆搜索 | 搜索 AI 记住的关于用户的信息 | Neo4j |
| 联网搜索 | 搜索互联网实时信息 | 外部搜索引擎 API |

### 7.3 关键代码路径

| 步骤 | 关键文件 |
|------|----------|
| Agent 编排主逻辑 | [api/app/core/agent/orchestrator.py](api/app/core/agent/orchestrator.py) |
| 工具定义 | [api/app/core/agent/tools/](api/app/core/agent/tools/) |
| 聊天 SSE 流 | [api/app/controllers/chat_controller.py](api/app/controllers/chat_controller.py) |
| Agent 配置 | [api/app/models/agent_config_model.py](api/app/models/agent_config_model.py) |

### 7.4 动手测试

```bash
# 1. 先确认知识库和记忆都有内容（阶段五、六已准备好）
# 2. 在聊天中问一个需要"联合查询"的问题
#    例如："根据我的知识库和之前的聊天，我最近在关注什么话题？"
# 3. 观察日志，看 Agent 的决策过程
docker compose logs -f api | grep -E "tool|agent|orchestrat"
```

### 7.5 Q&A 检验

1. **Agent 和普通的"一问一答"有什么区别？Agent 多做了什么？**

2. **什么是 ReAct 模式？为什么弱模型要用 ReAct 而不是原生 function calling？**

3. **如果 Agent 选错了工具（比如该查记忆却去查了知识库），用户体验会怎样？有没有办法防止？**

4. **SSE（Server-Sent Events）是什么？为什么聊天要用 SSE 而不是普通的 HTTP Response？**

---

## 阶段八：深度研究 + 群聊 + 其他高级功能

> **目标**：了解项目的高级功能，拓展认知边界。

### 8.1 功能清单

| 功能 | 简介 | 技术亮点 |
|------|------|----------|
| **深度研究** | 多步自主研究：规划→检索→提炼→写作 | LangChain Agent + 多工具编排 |
| **多 Agent 群聊** | 2~5 个 AI 角色群聊 | 主持人 LLM 调度，@ 指定发言 |
| **MCP 集成** | Model Context Protocol 扩展外部工具 | SSE/Streamable HTTP |
| **情绪分析** | valence-arousal 情绪模型 | 情绪记录 + 音乐推荐 |
| **每日回顾** | AI 生成当天互动总结 | Celery 定时任务 (22:00) |
| **对话分享** | 公开快照页 | Token 鉴权，无需登录 |

### 8.2 动手体验

```bash
# 查看 Celery 的定时任务调度
docker compose logs -f beat   # 观察 beat 的调度日志

# 查看定时任务执行（例如每日回顾）
docker compose logs -f worker | grep -E "daily_review|consolidat|reflection"
```

---

## 阶段九：生产部署

> **目标**：理解开发环境和生产环境的区别，知道如何上线。

### 9.1 开发 vs 生产

| 区别 | 开发环境 | 生产环境 |
|------|---------|---------|
| 配置文件 | `docker-compose.yml` | `docker-compose.yml` + `docker-compose.prod.yml` |
| 数据库密码 | 简单默认值 | 强密码 + 环境变量注入 |
| ES/Neo4j 内存 | 较小 | 4G+ 优化 |
| 前端 | Vite dev server | nginx 静态文件 |
| HTTPS | 无 | 启用 |
| 端口暴露 | 全部暴露 | 仅必要端口，绑定 127.0.0.1 |
| 调试模式 | APP_DEBUG=true | false |

### 9.2 生产启动

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 每日学习建议

| 天 | 阶段 | 预计时间 | 重点 |
|----|------|---------|------|
| Day 1 | 阶段一 + 阶段二 | 2-3h | Docker 基础 + 项目跑起来 + 四种存储概念 |
| Day 2 | 阶段三 + 阶段四 | 2-3h | 后端分层架构 + 前端结构 |
| Day 3 | 阶段五 | 2-3h | RAG 全链路，上传文档并观察日志 |
| Day 4 | 阶段六 | 2-3h | 记忆系统，看 Neo4j 图谱 |
| Day 5 | 阶段七 + 阶段八 | 2-3h | Agent 系统 + 高级功能体验 |
| Day 6 | 复习 + 自由探索 | 2-3h | 选一个最感兴趣的方向深入 |

---

## 学习小技巧

1. **边看边记**：每个阶段学完，用你自己的话写 3-5 句总结
2. **遇错不慌**：报错是最好的学习机会，先看日志，再定位代码
3. **多问"为什么"**：看到一个设计决策时，想想如果不这么做会有什么问题
4. **善用工具**：
   - `docker compose logs -f <服务名>` 实时看日志
   - FastAPI 的 `/api/docs` 交互式 API 文档
   - Neo4j 的 `http://localhost:7474` 可视化浏览器
   - 浏览器 F12 Network 看前后端通信
5. **对照学习**：每个功能都从 前端页面 → Network请求 → API路由 → Service逻辑 → Repository数据操作 → 数据库 完整走一遍
