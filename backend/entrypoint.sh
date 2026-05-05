#!/bin/sh
set -e

echo "Waiting for Postgres..."

until python -c "import socket; s=socket.socket(); s.connect(('postgres', 5432)); s.close()" 2>/dev/null; do
  sleep 1
done
echo "Running Alembic migrations..."
alembic upgrade head
echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload