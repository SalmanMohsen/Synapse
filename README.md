# Synapse

**Synapse** is an AI-native developer collaboration platform. It is organized like a team chat product — workspaces, projects, discipline channels, and tickets — with a human-supervised, two-stage AI agent pipeline attached to every ticket: a **Planning Agent** that turns a discussed ticket into a concrete implementation plan, and a **Code Agent** that executes an approved plan inside an isolated container and opens a pull request.

The platform is governed by one principle, enforced at every stage of the pipeline:

> **Humans deliberate, the agent executes, humans review.**

Nothing runs automatically on a hunch. A Team Lead decides when a ticket is ready, a Team Lead reviews and approves the generated plan before any code is touched, and every resulting change surfaces as a normal GitHub pull request for human review.

---

## Table of Contents

- [How It Works](#how-it-works)
- [System Architecture](#system-architecture)
- [Repository Structure](#repository-structure)
- [Component Reference](#component-reference)
  - [`backend/`](#backend--fastapi-modular-monolith)
  - [`planning-service/`](#planning-service--planning-agent)
  - [`code-service/`](#code-service--code-agent)
  - [`frontend/`](#frontend--react--typescript)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Configuring GitHub Identity](#configuring-github-identity)
  - [1. GitHub OAuth App — platform sign-in](#1-github-oauth-app--platform-sign-in)
  - [2. GitHub App — repository automation identity](#2-github-app--repository-automation-identity)
- [Configuring Google Sign-In (Optional)](#configuring-google-sign-in-optional)
- [Running the Local LLM](#running-the-local-llm)
- [Development Notes](#development-notes)

---

## How It Works

1. A ticket is initiated via an issue created in github then routed to a discipline channel (Frontend, Backend, Database, DevOps, AI…).
2. The Team Lead activates the ticket and the team discusses the approach in the thread.
3. Once the team has reached consensus, the Team Lead manually triggers the **Planning Agent**.
4. The Planning Agent retrieves relevant codebase context from Qdrant, drafts an implementation plan against the local LLM, validates that every file it references actually exists (or doesn't yet, for new files), and posts the plan back to the thread for review.
5. The Team Lead reviews, edits, approves, or rejects the plan.
6. On approval, the **Code Agent** spins up an ephemeral, isolated Docker sandbox, checks out the repository, and executes the plan step by step using the OpenHands runtime.
7. Each step is validated (repo test suite → generic linters → sanity check, in that order of preference) before the next one starts.
8. When execution finishes, the Code Agent pushes a branch and opens a pull request through the project's connected GitHub App installation. The PR lifecycle is mirrored back into the ticket's thread.

## System Architecture

Synapse is a **client-server system with background job workers**, not a full microservices mesh:

| Level | Pattern |
|---|---|
| Full system | Client-server, containerized, background workers over Redis/arq |
| Backend (macro) | Modular Monolith |
| Backend (micro) | N-Tier (Router → Service → Repository → Model) |
| Planning Agent | Pipes-and-Filters pipeline |
| Code Agent | Orchestrator + Observer (EventBus with guardrail subscribers) |
| Inter-service communication | Redis-backed job queue (`arq`) + Pub/Sub |

```
Member creates ticket ─▶ Team Lead activates ─▶ Team discusses in thread
                                                          │
                                        Team Lead manually triggers plan
                                                          ▼
                                 ┌────────────────────────────────────┐
                                 │   planning-service (Planning Agent) │
                                 │   scope gate → RAG retrieval        │
                                 │   → draft/critique → grounding      │
                                 │   validation                        │
                                 └────────────────────────────────────┘
                                                          │
                                          Plan posted, Team Lead reviews
                                                          ▼
                                               Team Lead approves plan
                                                          ▼
                                 ┌────────────────────────────────────┐
                                 │   code-service (Code Agent)         │
                                 │   ephemeral Docker sandbox          │
                                 │   OpenHands step execution          │
                                 │   guardrails + tiered validation    │
                                 └────────────────────────────────────┘
                                                          │
                                     Branch pushed, Pull Request opened
                                                          ▼
                                       Team reviews on GitHub → merges
```

Only two AI agents exist in the pipeline: **Planning Agent** and **Code Agent**. Both are stateless `arq` workers backed by shared Postgres state and a shared, locally hosted LLM — nothing is triggered automatically by an observer process; every hand-off is a human decision recorded through the backend API.

---

## Repository Structure

```
synapse/
├── backend/                     # FastAPI modular monolith — single source of truth
│   ├── alembic/                 # Database migrations (owned exclusively by backend)
│   └── app/
│       ├── agent_run/           # Plan review: approve / reject / edit endpoints
│       ├── auth/                # Registration, login, OAuth, JWT sessions
│       ├── channel/              # Discipline-scoped channels, approval policy
│       ├── git_providers/       # GitProvider abstraction (GitHub today, GitLab-ready)
│       ├── github/              # GitHub App install flow + webhook ingestion
│       ├── inbox/               # Invites and notifications
│       ├── message/             # Thread messages (human + agent cards)
│       ├── project/             # Projects, each linked to one GitHub repo
│       ├── skill/               # Skill files (specialty / technology) + assignment
│       ├── thread_state/        # Per-thread read-state
│       ├── ticket/              # Ticket lifecycle, status machine, agent job dispatch
│       ├── websocket/           # Single persistent WS connection, event fan-out
│       ├── workspace/           # Top-level container, membership, ownership
│       ├── config.py, database.py, jobs.py, main.py, UoW.py
│
├── planning-service/             # Planning Agent — arq worker
│   └── app/
│       ├── agent/                # Scope gate, plan draft/critique
│       ├── git_providers/        # Mirrors backend's GitProvider interface
│       ├── ingestion/            # Repo sync, chunking, embeddings, Qdrant storage
│       ├── llm/                  # vLLM (OpenAI-compatible) client
│       ├── prompt/               # Versioned prompt templates + assembly
│       ├── schemas/              # DevelopmentPlan schema
│       ├── config.py, db.py, pipeline.py, worker.py
│
│
├── code-service/                 # Code Agent — arq worker
│   ├── app/
│   │   ├── git/, git_providers/  # Branch, commit, PR operations
│   │   ├── guardrails/           # Dynamic locking, protected paths, stuck-loop
│   │   ├── openhands/            # OpenHands SDK wrapper, untrusted-content boundary
│   │   ├── sandbox/               # Docker-outside-of-Docker container lifecycle
│   │   ├── config.py, db.py, locks.py, loops_detector.py,
│   │   │   manifest.py, runner.py, steps.py, validation.py, worker.py
│   └── sandbox/                  # Dockerfile for the ephemeral execution image
│
├── frontend/                     # React + TypeScript SPA
│   └── src/
│       ├── features/             # Feature-sliced modules (auth, ticket, agentRun, …)
│       ├── router/                # Route guards
│       └── shared/                # Shared components, hooks (WebSocket, toast)
│
└── docker-compose.yaml           # Full local orchestration (dev profile)
```

---

## Component Reference

### `backend/` — FastAPI Modular Monolith

The backend is the single source of truth: it owns the database schema, authentication, and every write path in the system. It never calls the LLM directly — its only responsibility toward the AI pipeline is enqueuing jobs and exposing review/approval endpoints.

| Module | Function |
|---|---|
| `auth` | Email/password, GitHub OAuth, and Google OAuth sign-in; JWT access/refresh cookies; account linking. Platform identity is intentionally kept separate from Git access. |
| `workspace` | Top-level container for projects; ownership and membership. |
| `project` | A workspace's projects, each linked to exactly one GitHub repository. |
| `channel` | Discipline-scoped channels (Frontend, Backend, Database, DevOps, AI…); each channel sets its own approval policy (Lead Only vs. Any Member). |
| `ticket` | The atomic unit of work. Owns the ticket status machine (`backlog → active → in_discussion → consensus_reached → plan_review → agent_working → in_review → closed`, plus `blocked`/`split`) and is the module that enqueues the Planning Agent job once a Team Lead triggers it. |
| `message` | Thread messages — both human messages and typed agent cards. |
| `thread_state` | Lightweight per-thread read-state used to render a ticket's discussion. |
| `skill` | Skill files (Markdown/YAML) along two dimensions — specialty (auto-mapped from channel discipline) and technology (set by the Team Lead) — plus their assignment to channels. |
| `agent_run` | Tracks each `AgentRun` and its `AgentRunStep`s; exposes the plan-review endpoints (`approve`, `reject`, `edit`) that gate the hand-off from Planning Agent to Code Agent. |
| `github` / `git_providers` | GitHub App installation flow (`/github/install`, `/github/app/callback`), webhook ingestion (`/webhooks/github`), and a provider-agnostic `GitProvider` interface so a second provider (e.g. GitLab) can be added without touching calling code. |
| `inbox` | Invitations and personal notifications. |
| `websocket` | One persistent connection per client, JWT-authenticated on connect; fans out message, agent-progress, and ticket-status events. |
| `jobs.py` | Shared `arq` producer helper used to enqueue jobs onto Redis for `planning-service` and `code-service` to pick up. |
| `alembic/` | The **only** place database migrations are authored. Both agent services maintain read/write SQLAlchemy Core table mirrors (`create_type=False`) but never generate their own migrations. |

### `planning-service/` — Planning Agent

A stateless `arq` worker. `pipeline.py` composes a fixed, four-stage Pipes-and-Filters flow; `worker.py` is a thin adapter that registers the job and hands off to it.

| Component | Function |
|---|---|
| **Stage 1 — Scope gate** (`agent/planner.py`) | A cheap, guided-JSON LLM call that rejects out-of-scope or non-actionable tickets before any expensive work happens (`rejected_out_of_scope` status). |
| **Stage 2 — Retrieval** (`ingestion/qdrant_store.py`, `ingestion/embeddings.py`) | Embeds the ticket + discussion and retrieves the top-k most relevant codebase chunks from a single, `project_id`-filtered Qdrant collection. |
| **Stage 3 — Draft / critique** (`agent/planner.py`) | Generates the implementation plan against the local LLM, with a self-critique pass. |
| **Stage 4 — Grounding validation** (`agent/validation.py`) | Hard-fails the run if a "modify"/"delete" target doesn't exist in the manifest, or a "create" target already does. No silent correction — failures escalate. |
| `ingestion/repo_sync.py`, `chunking.py`, `service.py` | Clone/sync the project's repository and (re-)index it into Qdrant at function/class granularity. |
| `llm/client.py` | Thin OpenAI-compatible client pointed at the shared vLLM server. |
| `prompt/` | Prompt templates and assembly logic, versioned in the same commit as the code that depends on their JSON schema — never stored as loose config. |
| `schemas/plan.py` | The `DevelopmentPlan` Pydantic schema returned by the pipeline. |

### `code-service/` — Code Agent

Also a stateless `arq` worker. `runner.py` is the orchestrator; it owns the sandbox's entire lifecycle and is the *only* code path allowed to tear it down.

| Component | Function |
|---|---|
| `runner.py` | Orchestrates a run: acquires locks, starts the OpenHands conversation, races it against an `abort_event` via `asyncio.wait(..., FIRST_COMPLETED)`, and guarantees exactly one sandbox teardown in its `finally` block. |
| `guardrails/` | Subscribers on the agent's event bus, coordinated through a shared `RunContext`. They may request an abort but never touch the sandbox directly — only `runner.py`'s orchestrator does, which is what fixes a former teardown race condition. |
| &nbsp;&nbsp;↳ `dynamic_locking.py` | Requests/releases the Redis-backed distributed file locks a step needs before it can write. |
| &nbsp;&nbsp;↳ `protected_paths.py` | Flags any step touching database migrations files for mandatory human review; never aborts on its own. |
| &nbsp;&nbsp;↳ `stuck_loop.py` | Wraps `loops_detector.py`'s fingerprinting to abort a run that keeps repeating the same failing approach. |
| `openhands/conversation.py` | Wraps the OpenHands Agent SDK; wraps all ticket/plan text and file contents read back from the repository in an `<untrusted_context>` boundary so injected instructions inside them can't be treated as commands. |
| `sandbox/container.py` | Creates and tears down the ephemeral, per-run Docker sandbox using Docker-outside-of-Docker (the controller talks to the **host** Docker daemon over the mounted socket). |
| `locks.py` | Redis-based distributed locking (`SET NX EX`, alphabetical acquisition order to avoid deadlocks), monotonically increasing fencing tokens, the active-job registry, and LLM-assisted semantic conflict detection against the Codebase Manifest. |
| `manifest.py` | Incrementally updates the Codebase Manifest — AST (Python) / tree-sitter (other languages) structural parsing plus a lightweight LLM purpose summary per file. |
| `validation.py` | Three-tier post-step validation: the repo's own declared checks (Makefile/`package.json` scripts) → generic per-language linters baked into the sandbox image → a bare sanity check (encoding, merge-conflict markers) as the last resort. |
| `git/`, `git_providers/` | Branch creation, commits, and pull-request operations against the project's connected GitHub App installation. |
| `sandbox/Dockerfile` | The image every ephemeral run container is built from — git, Node.js, Python, generic Tier-2 validators (Stylelint, html-validate, Ruff), and the OpenHands agent server. |

### `frontend/` — React + TypeScript

A feature-sliced SPA (Bulletproof React convention). Each `features/<name>` folder owns its own `api/`, `hooks/`, `components/` or `pages/`, and `types/`. Notable modules:

| Feature | Function |
|---|---|
| `auth` | Login/register forms, OAuth popup flow, connected-account management. |
| `workspace`, `project`, `channel`, `ticket` | The core information-architecture CRUD and detail views. |
| `message` | Thread rendering, including typed agent cards. |
| `agentRun` | The plan-review card and edit modal — where a Team Lead approves, rejects, or edits a generated plan. |
| `github` | Connect/disconnect a project's GitHub App installation. |
| `shared/hooks/useWebSocket.ts` | The single persistent WebSocket connection consumed across every feature. |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite, React Query, Zustand, React Router |
| Backend API | FastAPI, SQLAlchemy (async) + Alembic, Pydantic v2 |
| Job Queue / Messaging | Redis + `arq` (async-native job queue) |
| Primary Database | PostgreSQL |
| Vector Database | Qdrant (Planning Agent RAG index only) |
| LLM Inference | vLLM, serving LLMs locally — no external/commercial AI APIs |
| Code Execution Runtime | OpenHands Agent SDK, inside Docker-outside-of-Docker ephemeral sandboxes |
| Embeddings | `nomic-ai/CodeRankEmbed` (sentence-transformers) |
| Static Parsing | Python `ast`, `tree-sitter-language-pack` |
| Sandbox Validators | Stylelint, html-validate, Ruff |
| Auth | GitHub OAuth, Google OAuth, JWT (HS256) cookies |
| Git Integration | GitHub App (Octokit-style REST calls via `httpx` + `python-jose`) |
| Containerization | Docker, Docker Compose |

---

## Prerequisites

- Docker and Docker Compose
- Git
- A machine that can serve **Qwen2.5-Coder** or any open-weight model through vLLM (or any OpenAI-compatible endpoint you point `LLM_BASE_URL` at). so the model choice is a single environment variable, not a code change.
- A GitHub account with permission to register an OAuth App and a GitHub App on the target account or organization
- Node.js 20+ and Python 3.11+ only if you intend to run a service outside Docker

## Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/SalmanMohsen/Synapse.git synapse
cd synapse

# 2. Create the root .env file (see Environment Variables below)
cp .env.example .env   # or create it from scratch using the reference table

# 3. Create a frontend-local env file
echo "VITE_API_URL=http://localhost:8000" > frontend/.env

# 4. Build the sandbox image the Code Agent spins up per run (one-time / on updates)
docker compose --profile setup build code-sandbox

# 5. Start everything else
docker compose up -d --build
```

The backend container waits for Postgres, then runs `alembic upgrade head` automatically on every startup — there is no separate manual migration step in development.

Once the stack is up:

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API (interactive docs) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |
| Qdrant dashboard | http://localhost:6333/dashboard |

Stop the stack with `docker compose down` (add `-v` to also drop the named volumes).

---

## Environment Variables

All variables below are read from the root `.env` file referenced by `docker-compose.yaml`.

**Database & cache**

| Variable | Used by | Notes |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | postgres, backend, planning-service, code-service | Shared Postgres instance |
| `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD` | pgadmin | Dev-only convenience container |

**Backend**

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Signs JWTs (`JWT_SECRET_KEY` internally) |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub **OAuth App** — sign-in only |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `GITHUB_APP_ID` | Numeric ID of the **GitHub App** (repo automation identity) |
| `GITHUB_APP_SLUG` | The App's URL slug — must match exactly; used to build the install link |
| `GITHUB_APP_PRIVATE_KEY_BASE64` | Base64-encoded PEM private key of the GitHub App |
| `GITHUB_WEBHOOK_SECRET` | Shared secret used to verify inbound webhook signatures |

**Planning Agent / Code Agent (both services)**

| Variable | Notes |
|---|---|
| `LLM_BASE_URL` | OpenAI-compatible vLLM endpoint, e.g. `http://host.docker.internal:8001/v1` |
| `LLM_MODEL_NAME` | e.g. `Qwen/Qwen2.5-Coder-7B-Instruct` — swap for the 1.5B variant on constrained VRAM |
| `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_BASE64` | Same GitHub App credentials as the backend — used to mint short-lived installation tokens for pushing branches and opening PRs |
| `CODE_REPO_WORK_ROOT_HOST` | *(code-service only, optional)* Host-side path backing the sandbox's bind-mounted working directory; defaults to `./data/code-repos` |

None of these secrets are ever committed — the GitHub App private key in particular should be treated the same as any production credential, even in local development, since it grants write access to whatever repositories the App is installed on.

---

## Configuring GitHub Identity

Synapse deliberately separates **who you are on the platform** (GitHub OAuth) from **what the agents are allowed to touch in your repositories** (a GitHub App). You need to register both.

### 1. GitHub OAuth App — platform sign-in

1. On GitHub: **Settings → Developer settings → OAuth Apps → New OAuth App**.
2. **Homepage URL**: your frontend URL (e.g. `http://localhost:5173`).
3. **Authorization callback URL**: `{BACKEND_URL}/api/v1/auth/github/callback` (e.g. `http://localhost:8000/api/v1/auth/github/callback`).
4. Generate a client secret.
5. Set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in the root `.env`.

This app is only used for `/api/v1/auth/github` (sign-in) and `/api/v1/auth/link/github` (linking an existing account) — it never touches repository contents.

### 2. GitHub App — repository automation identity

This is the identity the Planning Agent and Code Agent use to clone, push branches, and open pull requests.

> **Note — local development:** GitHub's servers need to reach your **Callback URL** and **Webhook URL** directly, so `http://localhost:8000` won't work for either one. Tunnel your local backend with [ngrok](https://ngrok.com/) (or a similar tool):
> ```bash
> ngrok http 8000
> ```
> Use the resulting `https://<random-id>.ngrok-free.app` URL as `BACKEND_URL` everywhere below — i.e. as the base for both the Callback URL and Webhook URL when you register the App on GitHub, and as `BACKEND_URL` in your root `.env`. `FRONTEND_URL` and `COOKIE_SECURE` can stay as they are for local testing. Since the free ngrok URL changes every time you restart the tunnel, you'll need to update the App's Callback/Webhook URLs (and `BACKEND_URL`) each time it does, or use a paid ngrok static domain to avoid that.

1. On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. **Homepage URL**: your frontend URL.
3. **Callback URL**: `{BACKEND_URL}/api/v1/github/app/callback` — this is where GitHub redirects a Team Lead after they install the App on a repository.
4. **Webhook → Active**: check it.
   - **Webhook URL**: `{BACKEND_URL}/api/v1/webhooks/github`
   - **Webhook secret**: generate a random value and set it as `GITHUB_WEBHOOK_SECRET`.
5. **Repository permissions** — grant at least:
   - Contents: **Read & write** (clone, branch, commit)
   - Pull requests: **Read & write** (open PRs)
   - Metadata: **Read-only** (required baseline)
6. **Subscribe to events**: `Issues`, `Pull request`, `Push` — these are the events the webhook handler currently normalizes and acts on.
7. Choose **Where can this GitHub App be installed?** based on your setup (your own account is fine for local development).
8. Create the App, then **generate a private key** from its settings page — this downloads a `.pem` file.
9. Base64-encode the key and set it as `GITHUB_APP_PRIVATE_KEY_BASE64`:
   ```bash
   # Linux
   base64 -w 0 your-app-private-key.pem
   # macOS
   base64 -i your-app-private-key.pem | tr -d '\n'
   ```
10. Set `GITHUB_APP_ID` (the numeric App ID shown at the top of the App's settings page — **not** the client ID) and `GITHUB_APP_SLUG` (the App's URL slug, exactly as it appears in `https://github.com/apps/<slug>`).
11. Restart the backend, planning-service, and code-service containers so they pick up the new credentials.

From here, connecting a specific project to a repository is done from inside Synapse itself: a Team Lead opens the project's settings, triggers **Connect GitHub** (`GET /api/v1/projects/{project_id}/github/install`), and completes the App's installation flow in the popup GitHub opens. The backend resolves the resulting installation ID back to the correct project automatically.

## Configuring Google Sign-In (Optional)

1. In the [Google Cloud Console](https://console.cloud.google.com/), create an OAuth 2.0 Client ID (Web application).
2. **Authorized redirect URI**: `{BACKEND_URL}/api/v1/auth/google/callback`.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the root `.env`.

## Running the Local LLM

Both agent services call the same OpenAI-compatible `LLM_BASE_URL`. In development this is typically a vLLM server run **outside** the Docker Compose stack (on the host, or on a machine reachable from it), which is why `planning-service` and `code-service` are given `host.docker.internal` mappings. Point `LLM_BASE_URL` at wherever that server is listening, and set `LLM_MODEL_NAME` to match the model it's serving. Switching between the 1.5B and 7B Qwen2.5-Coder variants to fit available VRAM requires changing this variable only — no code changes.

## Development Notes

- The backend is the **only** service that runs Alembic migrations. `planning-service` and `code-service` maintain read/write SQLAlchemy Core table mirrors against the same schema and must never generate their own migrations.
- `planning-service` and `code-service` are both plain `arq` workers — start them the same way you'd start any other `arq` worker (`arq app.worker.WorkerSettings`), which is exactly what their Dockerfiles do.
- The sandbox image (`code-service/sandbox/Dockerfile`) is intentionally a single, generously-equipped image rather than one tiered per repository type — rebuild it (`docker compose --profile setup build code-sandbox`) whenever you change the validators or tools it ships with.
