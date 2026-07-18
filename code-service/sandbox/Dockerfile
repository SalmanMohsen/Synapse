# syntax=docker/dockerfile:1
#
# Synapse Code Agent — sandbox runtime image (build plan Step 1).
#
# Single generic, generously-equipped image (NOT tiered by repo type) — this is
# OpenHands' own documented default posture, and real operators recommend
# preinstalling everything you can so the agent never burns steps installing
# tools itself.
#
# Contents: git, Python, Node/npm, plus this project's Tier-2 validators
# (Stylelint + an HTML validator) baked in.
#
# Build & tag (pin the tag; referenced by CODE_SANDBOX_IMAGE):
#   docker build -t synapse-code-sandbox:latest code-service/sandbox
#
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# --- System toolchain: git + Node.js + build essentials ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Tier-2 generic validators (build plan Validation section) ---
# JS/CSS: stylelint (+ a standard config). HTML: html-validate CLI.
RUN npm install -g --no-audit --no-fund \
    stylelint@16 \
    stylelint-config-standard@36 \
    html-validate@8 \
    && npm cache clean --force

# --- Python-side generic validators (extensible per build plan; Ruff ready
# for when Python repos are actually tested). ---
RUN pip install --no-cache-dir ruff

RUN pip install --no-cache-dir \
    openhands-agent-server==1.36.1 \
    openhands-sdk==1.36.1 \
    openhands-tools==1.36.1 \
    openhands-workspace==1.36.1 \
    lmnr==0.7.47 \
    opentelemetry-instrumentation==0.60b1 \
    opentelemetry-instrumentation-threading==0.60b1 \
    opentelemetry-semantic-conventions==0.60b1 \
    libtmux
# The agent's working repository is bind-mounted here at run time. Only this
# directory is visible inside the sandbox (dangerous-action mount boundary).
WORKDIR /workspace/repo

# Unauthenticated, loopback-only from the sandbox's own perspective is fine —
# the only path in is the port we publish ourselves, and container.py's
# network_mode="bridge" + no host network already keeps this off the host's
# public interfaces. (Revisit if sandboxes are ever placed on a shared
# network with untrusted containers.)
EXPOSE 8000
CMD ["python", "-m", "openhands.agent_server", "--host", "0.0.0.0", "--port", "8000"]