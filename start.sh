#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
export IMAGE2DNG_PROJECT="${IMAGE2DNG_PROJECT:-$ROOT/vendor/Image-to-Raw}"
exec uvicorn app:app --host 127.0.0.1 --port 8000
