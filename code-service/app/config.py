"""Central environment-driven configuration for code-service.

Single import surface for every tunable knob so the rest of the service never
reads os.environ directly. Mirrors the env-var swap mechanism used across the
stack (LLM_BASE_URL / LLM_MODEL_NAME), and centralizes the budgets that the
build plan explicitly flags as "may need empirical retuning" against the local
Qwen2.5-Coder model.
"""

import os


# --- Database (code-service reads/writes the shared Postgres, backend owns
# migrations). Own env-var name so it can point at a different DSN than the
# planning-service if ever needed. ---
DATABASE_URL = os.getenv(
    "CODE_DATABASE_URL",
    os.getenv(
        "PLANNING_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/synapse",
    ),
)

# --- Redis (arq queue + Redlock + active job registry + progress pub/sub) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# --- LLM (vLLM OpenAI-compatible endpoint; same swap mechanism as the rest
# of the stack). Used only for the lightweight manifest purpose-summary call. ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://host.docker.internal:8001/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")

# --- GitHub App (installation-token auth; same secrets as backend) ---
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY_BASE64 = os.getenv("GITHUB_APP_PRIVATE_KEY_BASE64", "")

# --- Sandbox image (Step 1). Pinned + tagged; single generic image. ---
SANDBOX_IMAGE = os.getenv("CODE_SANDBOX_IMAGE", "synapse-code-sandbox:latest")

# Where the sandbox mounts the working repo internally. Only this path is
# visible inside the sandbox (dangerous-action mount boundary, Step 12).
SANDBOX_REPO_MOUNT = os.getenv("SANDBOX_REPO_MOUNT", "/workspace/repo")

# Host-side root under which per-run repo clones live before being mounted into
# the sandbox. Must be a path the host Docker daemon can bind-mount.
REPO_WORK_ROOT = os.getenv("CODE_REPO_WORK_ROOT", "/data/code-repos")

# Host-side path corresponding to REPO_WORK_ROOT as seen by the host Docker daemon
REPO_WORK_ROOT_HOST = os.getenv("CODE_REPO_WORK_ROOT_HOST", REPO_WORK_ROOT)

# Agent git identity for commits produced inside the sandbox.
GIT_AUTHOR_NAME = os.getenv("CODE_GIT_AUTHOR_NAME", "Synapse Code Agent")
GIT_AUTHOR_EMAIL = os.getenv("CODE_GIT_AUTHOR_EMAIL", "code-agent@synapse.local")

# --- Branch naming: ai/ticket-{id}-{slug} ---
BRANCH_PREFIX = os.getenv("CODE_BRANCH_PREFIX", "ai/ticket")

# ------------------------------------------------------------------ #
# Budgets & limits (build plan "Locked Decisions" + "Deferred")       #
# All overridable via env for the empirical-retuning the plan calls   #
# for once real runs against the local model are observed.            #
# ------------------------------------------------------------------ #

# Soft AI failure: max correction attempts per step.
CORRECTION_ATTEMPT_BUDGET = int(os.getenv("CODE_CORRECTION_BUDGET", "2"))

# Stuck loop: attempts counted against budget after the initial warning.
STUCK_LOOP_BUDGET = int(os.getenv("CODE_STUCK_LOOP_BUDGET", "5"))
# Fingerprint sliding-window size (last N tool calls, scoped per step).
STUCK_LOOP_WINDOW = int(os.getenv("CODE_STUCK_LOOP_WINDOW", "20"))
# Number of identical fingerprints in-window that trips the detector.
STUCK_LOOP_THRESHOLD = int(os.getenv("CODE_STUCK_LOOP_THRESHOLD", "3"))

# Per-step wall-clock timeout (seconds). 5 min per the locked decision.
STEP_TIMEOUT_SECONDS = int(os.getenv("CODE_STEP_TIMEOUT_SECONDS", "300"))

# Redlock lock TTL (seconds). Must exceed STEP_TIMEOUT_SECONDS so a legitimately
# running step's lock can't expire mid-flight. 6 min per the locked decision.
LOCK_TTL_SECONDS = int(os.getenv("CODE_LOCK_TTL_SECONDS", "360"))

# arq hard-technical-failure retries: 3 attempts, 1/5/15 min backoff.
MAX_JOB_ATTEMPTS = int(os.getenv("CODE_MAX_JOB_ATTEMPTS", "3"))
JOB_BACKOFF_SCHEDULE = [60, 300, 900]  # seconds, indexed by (job_try - 1)

# Semantic-conflict similarity threshold for the active job registry check.
SEMANTIC_CONFLICT_THRESHOLD = float(os.getenv("CODE_SEMANTIC_CONFLICT_THRESHOLD", "0.85"))


# --- OpenHands Agent Server (Step 4). Runs inside the sandbox image; the
# controller reaches it via the published port over host.docker.internal
# (code-service and the sandbox are sibling containers, not networked
# together — same reason planning-service reaches vLLM this way). ---
AGENT_SERVER_INTERNAL_PORT = int(os.getenv("CODE_AGENT_SERVER_PORT", "8000"))
AGENT_SERVER_HOST = os.getenv("CODE_AGENT_SERVER_HOST", "host.docker.internal")

def job_backoff_seconds(job_try: int) -> int:
    """Return the defer time (seconds) for a given 1-based job attempt number."""
    idx = max(0, min(job_try - 1, len(JOB_BACKOFF_SCHEDULE) - 1))
    return JOB_BACKOFF_SCHEDULE[idx]
