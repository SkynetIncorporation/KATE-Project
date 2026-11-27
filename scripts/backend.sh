#!/usr/bin/env bash
# Arranca el backend (Gemini + servidor MCP) en 127.0.0.1:8000. Luego, en otra terminal: scripts/tunel.sh
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port "${1:-8000}"
