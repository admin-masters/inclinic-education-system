#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON="./.venv/bin/python"
SERVER_LOG="tmp/docs/demo_runtime/runserver.log"
SELECTORS=("$@")

$PYTHON tmp/docs/bootstrap_user_flow_demo.py >/dev/null

mkdir -p "$(dirname "$SERVER_LOG")"
$PYTHON backend/manage.py runserver 127.0.0.1:8000 --settings=myproject.settings_docs >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" >/dev/null 2>&1 || true' EXIT

$PYTHON - <<'PY'
import time
import urllib.request

url = "http://127.0.0.1:8000/"
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=1):
            break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Server did not start in time.")
PY

$PYTHON tmp/docs/capture_user_flow_screenshots.py "${SELECTORS[@]}"
$PYTHON tmp/docs/generate_user_flow_pack.py "${SELECTORS[@]}"
$PYTHON tmp/docs/qa_user_flow_pack.py "${SELECTORS[@]}"
