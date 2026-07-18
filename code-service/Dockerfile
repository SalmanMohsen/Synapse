# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer output streams
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Configure pip global environment variables inside the container
ENV PIP_DEFAULT_TIMEOUT=1000
ENV PIP_RETRIES=20

# Establish working directory inside the container
WORKDIR /app

# Install system-level dependencies.
# git: repo operations executed from the controller side (checkpoint resume clones).
# The Docker CLI is NOT needed here — we talk to the host daemon via the
# docker-py SDK over the mounted /var/run/docker.sock (Docker-outside-of-Docker).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy python dependencies file first to leverage Docker layer caching
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.txt

# Copy application source files
COPY . .

# Run the arq worker command targeting our WorkerSettings
CMD ["arq", "app.worker.WorkerSettings"]
