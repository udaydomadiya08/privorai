#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall app tests
pytest -q
docker compose -f docker-compose.yml config >/dev/null
docker compose -f docker-compose.yml -f docker-compose.production.yml config >/dev/null

echo "Validation passed."
