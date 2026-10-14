#!/bin/sh
# Container entry point. Migrations and the idempotent source/seed load run here rather
# than in railway.json's preDeployCommand: CLI-created Railway services have been seen to
# ignore railway.json (2026-10-08), which would silently skip the schema.
set -e
alembic upgrade head
python scripts/load_sources.py
exec uvicorn mhs.main:app --host 0.0.0.0 --port "${PORT:-8000}"
