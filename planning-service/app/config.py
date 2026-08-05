"""Central environment-driven configuration for planning-service.

Single import surface for every tunable knob so the rest of the service never
reads os.environ directly. Mirrors the pattern already established in
code-service/app/config.py (same LLM_BASE_URL / LLM_MODEL_NAME swap mechanism
used across the stack).

NOTE: this file currently centralizes the values consumed by worker.py and
db.py. embeddings.py, github_auth.py, qdrant_store.py, and repo_sync.py still
read os.environ directly for their own vars (EMBEDDING_MODEL_NAME,
MAX_EMBED_TOKENS, GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_BASE64, QDRANT_URL,
QDRANT_COLLECTION, REPO_CLONE_ROOT) — same names, not yet wired to import from
here. See chat for the small patch to each once those files are on hand.
"""

import os

# --- Database (planning-service reads/writes the shared Postgres; backend
# owns all Alembic migrations — this is a thin Core table mirror only). ---
DATABASE_URL = os.getenv(
    "PLANNING_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/synapse",
)

# --- Redis (arq queue broker + pub/sub for WebSocket events). Kept as a
# required var (raises if unset) — this is unchanged from worker.py's
# previous os.environ["REDIS_URL"]; code-service treats the same var as
# optional with a default. Flag if you'd rather match code-service here. ---
REDIS_URL = os.environ["REDIS_URL"]

# --- LLM (vLLM OpenAI-compatible endpoint; same swap mechanism as the rest
# of the stack). Kept required, matching worker.py's previous
# os.environ["LLM_BASE_URL"] / os.environ["LLM_MODEL_NAME"] — code-service
# defaults these instead. Flag if you'd rather soften to a default here too. ---
LLM_BASE_URL = os.environ["LLM_BASE_URL"]
LLM_MODEL_NAME = os.environ["LLM_MODEL_NAME"]

# --- Embeddings (nomic-embed-text family, in-process via sentence-transformers).
# embeddings.py owns the actual default ("nomic-ai/CodeRankEmbed") and still
# reads os.environ directly for now (not yet wired to this file — see the
# note at the top). Mirrored here only so worker.py's startup log doesn't
# carry its own independent, and previously mismatched, fallback literal. ---
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "nomic-ai/CodeRankEmbed")

# ------------------------------------------------------------------ #
# Retrieval + job budgets (overridable via env for the same empirical-      #
# retuning reason as code-service/app/config.py).                          #
# ------------------------------------------------------------------ #

# Locked decision: top-k=8 (single shared Qdrant collection, project_id
# mandatory filter). Was a bare literal on the retrieve_chunks() call site.
RETRIEVAL_TOP_K = int(os.getenv("PLANNING_RETRIEVAL_TOP_K", "8"))

# arq hard-technical-failure retries: 3 attempts, 1/5/15 min backoff — same
# schedule/shape as code-service's CODE_MAX_JOB_ATTEMPTS / JOB_BACKOFF_SCHEDULE.
MAX_JOB_ATTEMPTS = int(os.getenv("PLANNING_MAX_JOB_ATTEMPTS", "3"))
JOB_BACKOFF_SCHEDULE = [60, 300, 900]  # seconds, indexed by (job_try - 1)

# arq WorkerSettings knobs — previously bare literals on the class body.
JOB_TIMEOUT_SECONDS = int(os.getenv("PLANNING_JOB_TIMEOUT_SECONDS", "600"))
WORKER_MAX_CONCURRENT_JOBS = int(os.getenv("PLANNING_WORKER_MAX_CONCURRENT_JOBS", "4"))


def job_backoff_seconds(job_try: int) -> int:
    """Return the defer time (seconds) for a given 1-based job attempt number."""
    idx = max(0, min(job_try - 1, len(JOB_BACKOFF_SCHEDULE) - 1))
    return JOB_BACKOFF_SCHEDULE[idx]