# CLAUDE.md

This file provides guidance for AI assistants working with the OneSeek codebase.

## Project Overview

OneSeek (formerly SurfSense) is an AI agent platform for real-time analysis, tool orchestration, and transparent AI decision logic. It consists of three main components:

- **Backend** (`surfsense_backend/`) — Python/FastAPI with LangGraph agent orchestration
- **Frontend** (`surfsense_web/`) — Next.js 16 web application with React 19
- **Browser Extension** (`surfsense_browser_extension/`) — Plasmo-based Chrome extension

The project language (UI, README, agent names) is primarily Swedish, though code and comments are in English.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌────────────────────┐
│  Browser Extension   │────▶│   Next.js Frontend    │────▶│  FastAPI Backend    │
│  (Plasmo/React 18)   │     │  (React 19/Next 16)   │     │  (Python 3.12)     │
└─────────────────────┘     └──────────────────────┘     └────────┬───────────┘
                                       │                          │
                              ┌────────┴────────┐        ┌───────┴──────────┐
                              │  Electric-SQL    │        │  LangGraph Agent │
                              │  (real-time sync)│        │  Orchestration   │
                              └─────────────────┘        └───────┬──────────┘
                                                                  │
                                                    ┌─────────────┼──────────────┐
                                                    │             │              │
                                             ┌──────┴──┐  ┌──────┴──┐  ┌───────┴──┐
                                             │PostgreSQL│  │  Redis   │  │ External │
                                             │+PGVector │  │ (Celery) │  │   APIs   │
                                             └─────────┘  └─────────┘  └──────────┘
```

### Backend Architecture (LangGraph Agent Flow)

The backend implements a **Hybrid Supervisor v2** pattern with 4 phases:
1. **Phase 1**: Intent routing with complexity classification (`trivial`/`simple`/`complex`)
2. **Phase 2**: Execution strategy routing (`inline`/`parallel`/`subagent`)
3. **Phase 3**: Memory and feedback loops (episodic memory)
4. **Phase 4**: Speculative branching + progressive synthesis with draft-streaming

Key subsystems:
- **Bigtool retrieval** — dynamic tool selection via vector similarity
- **LiteLLM** — model abstraction layer with usage-based routing
- **Domain fan-out** — parallel tool execution within bounded agents
- **Compare mode** — parallel external model calls with separate subgraph
- **DB-driven flow graph** — database-backed route/tool mappings (not hardcoded)

## Repository Structure

```
oneseekv1/
├── surfsense_backend/           # Python backend
│   ├── app/
│   │   ├── agents/              # LangGraph agent definitions
│   │   │   ├── new_chat/        # Main chat agent graph
│   │   │   │   ├── nodes/       # Graph nodes (intent, planner, executor, synthesizer, etc.)
│   │   │   │   ├── tools/       # Tool implementations (weather, search, maps, etc.)
│   │   │   │   ├── complete_graph.py  # Full graph assembly
│   │   │   │   ├── supervisor_*.py    # Supervisor agent logic
│   │   │   │   └── ...
│   │   │   └── podcaster/       # Podcast generation agent
│   │   ├── config/              # App configuration (Config class, LLM router)
│   │   ├── connectors/          # External service connectors (Slack, Notion, Jira, etc.)
│   │   ├── prompts/             # Prompt templates
│   │   ├── retriever/           # Hybrid search (chunks + documents)
│   │   ├── routes/              # FastAPI route handlers
│   │   ├── schemas/             # Pydantic/SQLAlchemy models
│   │   ├── services/            # Business logic services
│   │   ├── tasks/               # Celery async tasks
│   │   ├── utils/               # Shared utilities
│   │   ├── app.py               # FastAPI app factory with lifespan
│   │   ├── db.py                # SQLAlchemy models and DB setup
│   │   └── users.py             # FastAPI-Users auth config
│   ├── alembic/                 # Database migrations
│   ├── tests/                   # pytest test suite
│   ├── main.py                  # uvicorn entry point
│   ├── celery_worker.py         # Celery worker entry point
│   └── pyproject.toml           # Python dependencies (uv/pip)
│
├── surfsense_web/               # Next.js frontend
│   ├── app/                     # Next.js App Router pages
│   │   ├── (home)/              # Landing/marketing pages
│   │   ├── admin/               # Admin panel (cache, flow, lifecycle, prompts, tools)
│   │   ├── api/                 # Next.js API routes (search, convert, contact)
│   │   ├── auth/                # Auth pages
│   │   ├── dashboard/           # Main user dashboard
│   │   ├── db/                  # Drizzle ORM schema
│   │   ├── docs/                # Documentation pages (fumadocs)
│   │   └── public/              # Public-facing pages
│   ├── components/              # React components
│   │   ├── admin/               # Admin UI components
│   │   ├── assistant-ui/        # Chat/assistant components
│   │   ├── new-chat/            # Chat interface components
│   │   ├── ui/                  # shadcn/ui base components
│   │   └── ...
│   ├── hooks/                   # Custom React hooks
│   ├── lib/                     # Utility libraries (APIs, auth, Electric-SQL, etc.)
│   ├── contracts/               # TypeScript types and enums
│   ├── atoms/                   # Jotai state atoms
│   ├── contexts/                # React context providers
│   ├── messages/                # i18n translation files (en, sv, zh)
│   ├── i18n/                    # next-intl configuration
│   └── package.json             # Node dependencies (pnpm)
│
├── surfsense_browser_extension/ # Browser extension
│   ├── background/              # Service worker scripts
│   ├── routes/                  # Extension page routes
│   ├── lib/                     # Shared utilities
│   ├── popup.tsx                # Extension popup entry
│   ├── content.ts               # Content script
│   └── package.json             # Dependencies (pnpm + Plasmo)
│
├── docs/                        # Architecture documentation
├── eval/                        # Evaluation system
├── scripts/                     # Docker and utility scripts
├── .github/workflows/           # CI: code-quality.yml
├── .rules/                      # Cursor/AI coding rules (.mdc files)
├── docker-compose.yml           # Development stack
├── docker-compose.quickstart.yml # Quick-start stack
├── biome.json                   # Root Biome config (JS/TS linting + formatting)
├── .pre-commit-config.yaml      # Pre-commit hooks configuration
└── langgraph.json               # LangGraph Studio configuration
```

## Development Setup

### Prerequisites

- **Python 3.12+** with `uv` package manager
- **Node.js 18+** with `pnpm` package manager
- **PostgreSQL** with PGVector extension
- **Redis** (for Celery task queue)
- **Docker & Docker Compose** (recommended)

### Backend

```bash
cd surfsense_backend

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env  # Edit with your API keys and DB URL

# Run database migrations
alembic upgrade head

# Start the backend server
python main.py --reload

# Or run via uvicorn directly
uvicorn app.app:app --reload --port 8000
```

### Frontend

```bash
cd surfsense_web

# Install dependencies
pnpm install

# Start development server (Turbopack)
pnpm dev

# Build for production
pnpm build

# Database operations (Drizzle)
pnpm db:generate   # Generate migrations
pnpm db:migrate    # Run migrations
pnpm db:push       # Push schema to DB
```

### Browser Extension

```bash
cd surfsense_browser_extension

# Install dependencies
pnpm install

# Start development
pnpm dev

# Build for production
pnpm build
```

### Docker (Full Stack)

```bash
# Copy env files
cp .env.example .env
cp surfsense_backend/.env.example surfsense_backend/.env

# Start all services
docker compose up -d

# Or use quickstart
docker compose -f docker-compose.quickstart.yml up -d
```

## Key Commands

### Backend (Python)

| Command | Description |
|---------|-------------|
| `uv sync` | Install/sync Python dependencies |
| `python main.py --reload` | Start backend with hot reload |
| `cd surfsense_backend && python -m pytest tests/` | Run test suite |
| `ruff check surfsense_backend/ --fix` | Lint Python code |
| `ruff format surfsense_backend/` | Format Python code |
| `alembic upgrade head` | Run database migrations |
| `alembic revision --autogenerate -m "description"` | Create migration |
| `celery -A app.celery_app worker --loglevel=info` | Start Celery worker |

### Frontend (TypeScript)

| Command | Description |
|---------|-------------|
| `pnpm install` | Install dependencies |
| `pnpm dev` | Start dev server (Turbopack) |
| `pnpm build` | Production build |
| `pnpm lint` | Run ESLint |
| `pnpm format` | Run Biome formatter |
| `pnpm format:fix` | Auto-fix Biome issues |
| `pnpm db:generate` | Generate Drizzle migrations |
| `pnpm db:migrate` | Apply Drizzle migrations |

### Browser Extension

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start Plasmo dev server |
| `pnpm build` | Build extension |
| `pnpm package` | Package for distribution |

## Code Quality & Linting

### Pre-commit Hooks

The project uses pre-commit hooks (`.pre-commit-config.yaml`):
- **File quality**: YAML/JSON/TOML validation, merge conflict detection, large file checks
- **Security**: `detect-secrets` (with baseline), `bandit` (high severity only)
- **Python**: `ruff` linter + formatter (PEP 8, isort, bugbear, etc.)
- **TypeScript/JS**: `biome` check (errors only for pre-commit)
- **Commit messages**: `commitizen` (conventional commits)

### Python Style (Ruff)

- Line length: 88
- Indent: 4 spaces
- Double quotes
- Target: Python 3.12
- Import sorting: isort with `app` as first-party
- Rules: pycodestyle, pyflakes, isort, pep8-naming, pyupgrade, bugbear, comprehensions, simplify
- Print statements allowed (`T201` ignored)

### TypeScript/JS Style (Biome)

- Indent: tabs (width 2)
- Line width: 100
- Double quotes for strings and JSX
- Semicolons: always
- Trailing commas: ES5
- Arrow parens: always
- Recommended lint rules enabled, with `noExplicitAny` and `noArrayIndexKey` as warnings

### Commit Message Convention

Uses conventional commits enforced by commitizen:
```
feat: add document search functionality
fix: resolve pagination issue in chat history
docs: update installation guide
refactor: improve error handling in connectors
```

## Coding Rules (.rules/)

These rules are defined in `.rules/` and should always be followed:

1. **avoid-source-deduplication** — Preserve all source entries in search results for citation tracking. Never deduplicate sources by URL or title.

2. **consistent-container-image-sources** — Use consistent image sources from authorized registries in Docker compose files. Only use `build` in dev compose files.

3. **no-env-files-in-repo** — Never commit `.env` files. Use `.env.example` templates instead.

4. **require-unique-id-props** — Always provide unique `key` props when mapping arrays to React elements. Keys must be stable, predictable, and unique among siblings.

## Important Conventions

### Backend

- **Async-first**: All DB operations use SQLAlchemy async sessions (`AsyncSession`)
- **Auth**: FastAPI-Users with JWT (supports LOCAL and GOOGLE auth types)
- **Database**: PostgreSQL with PGVector for embeddings, SQLAlchemy ORM
- **Models**: Defined in `app/db.py` (SQLAlchemy) and `app/schemas/` (Pydantic)
- **Connectors**: Each external integration has its own connector module in `app/connectors/`
- **Routes**: RESTful API under `/api/v1/`, auth under `/auth/`
- **Config**: Centralized in `app/config/__init__.py` via `Config` class, reads from env vars
- **LLM calls**: Via LiteLLM abstraction, user-specific LLM configs stored in DB
- **Agent graph**: LangGraph-based, defined in `app/agents/new_chat/complete_graph.py`
- **Streaming**: Vercel AI Data Stream protocol (SSE) for real-time UI updates

### Frontend

- **Framework**: Next.js 16 with App Router, React 19, TypeScript
- **State management**: Jotai (atoms), Zustand, React Query (TanStack)
- **UI components**: shadcn/ui (Radix primitives), Tailwind CSS
- **Rich text**: BlockNote editor
- **i18n**: next-intl with Swedish (sv), English (en), and Chinese (zh)
- **Real-time sync**: Electric-SQL for live data from PostgreSQL
- **Chat UI**: @assistant-ui/react with Vercel AI SDK
- **Path aliases**: `@/*` maps to project root
- **Docs**: Fumadocs MDX for documentation pages
- **Analytics**: PostHog (reverse-proxied through Next.js rewrites)

### Browser Extension

- **Framework**: Plasmo with React 18 and TypeScript
- **Styling**: Tailwind CSS 3
- **Storage**: @plasmohq/storage
- **Content conversion**: dom-to-semantic-markdown

## Environment Variables

Key environment variables (see `.env.example` and `surfsense_backend/app/config/__init__.py`):

| Variable | Component | Description |
|----------|-----------|-------------|
| `DATABASE_URL` | Backend | PostgreSQL connection string (asyncpg) |
| `AUTH_TYPE` | Backend | `LOCAL` or `GOOGLE` |
| `EMBEDDING_MODEL` | Backend | Sentence-transformer model name |
| `SECRET_KEY` | Backend | JWT signing secret |
| `ETL_SERVICE` | Backend | `UNSTRUCTURED`, `LLAMACLOUD`, or `DOCLING` |
| `NEXT_FRONTEND_URL` | Backend | Frontend URL for CORS |
| `CELERY_BROKER_URL` | Backend | Redis URL for Celery |
| `NEXT_PUBLIC_FASTAPI_BACKEND_URL` | Frontend | Backend API URL |
| `NEXT_PUBLIC_ELECTRIC_URL` | Frontend | Electric-SQL sync URL |
| `NEXT_PUBLIC_FASTAPI_BACKEND_AUTH_TYPE` | Frontend | `LOCAL` or `GOOGLE` |
| `NEXT_PUBLIC_ETL_SERVICE` | Frontend | ETL service selection |

## CI/CD

GitHub Actions workflow (`.github/workflows/code-quality.yml`) runs on PRs to `main`/`dev`:

1. **File Quality Checks** — pre-commit hooks for YAML/JSON/TOML, merge conflicts, large files
2. **Security Scan** — detect-secrets and bandit
3. **Python Backend Quality** — ruff lint + format (only if `surfsense_backend/` changed)
4. **TypeScript/JS Quality** — biome check (only if `surfsense_web/` or extension changed)
5. **Quality Gate** — all jobs must pass

## Testing

### Backend Tests

Tests are in `surfsense_backend/tests/` using pytest:

```bash
cd surfsense_backend
python -m pytest tests/ -v
```

Test files cover:
- Agent routing and dispatching
- Phase 1-4 of the hybrid supervisor
- Individual services (SMHI, SCB, Kolada, etc.)
- Tool evaluation and metadata
- Sandbox provisioning

### No Frontend Tests Currently

The frontend does not have a test suite configured at this time.

## Database

- **ORM**: SQLAlchemy (async) for backend, Drizzle for frontend
- **Migrations**: Alembic (backend), Drizzle Kit (frontend)
- **Vector storage**: PGVector extension for embeddings (max 2000 dimensions)
- **Connection**: `postgresql+asyncpg://` for backend async operations

## Key Integration Points

- **Electric-SQL**: Real-time sync between PostgreSQL and frontend (messages, connectors, documents, comments)
- **LangGraph Studio**: Development tool for visualizing agent graphs (configured via `langgraph.json`)
- **LangSmith**: Optional tracing/observability (configured via env vars `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`)
- **PostHog**: Product analytics in frontend (reverse-proxied)
- **Celery/Redis**: Background task processing (document indexing, connector syncs)
