#!/usr/bin/env bash
# Pin the interpreter: bare `python` on this machine can resolve to a venv that
# lacks the project's dependencies. Override with PYTHON=/path/to/python.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-/home/louis/.venvs/main/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "Interpreter not found: $PYTHON" >&2
  echo "Set PYTHON=/path/to/python and retry." >&2
  exit 1
fi
case "${1:-}" in
  test)  shift; exec "$PYTHON" -m unittest discover -s tests -v "$@" ;;
  serve) shift; exec "$PYTHON" run_server.py "$@" ;;
  "")    exec "$PYTHON" run_simulation.py --help ;;
  *)     exec "$PYTHON" run_simulation.py "$@" ;;
esac
