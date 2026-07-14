# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer output streams
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Configure pip global environment variables inside the container
ENV PIP_DEFAULT_TIMEOUT=1000
ENV PIP_RETRIES=20

# Establish working directory inside the container
WORKDIR /app

# Install system-level dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies file first to leverage Docker layer caching
COPY requirements.txt .

# Mount the host system's pip cache folder into the build container.
# This prevents downloading from scratch if a timeout occurs.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy application source files
COPY . .

# Run the arq worker command targeting our WorkerSettings
CMD ["arq", "app.worker.WorkerSettings"]