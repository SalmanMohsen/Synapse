#!/usr/bin/env bash
set -e  # Exit immediately if any test suite fails

echo "=== Running Backend Tests ==="
docker compose exec -e PYTHONPATH=. backend pytest --asyncio-mode=auto

echo "=== Running Code Service Tests ==="
docker exec -t synapse-code-service sh -c "PYTHONPATH=. pytest"

echo "=== Running Planning Service Tests ==="
docker exec -t synapse-planning-service sh -c "PYTHONPATH=. pytest"

echo "All test suites passed!"