#!/usr/bin/env bash

set -euo pipefail

HOST="127.0.0.1"
PORT="8123"
SKIP_INSTALL="false"
ALLOW_BLOCKING="false"

usage() {
  cat <<'EOF'
Usage: ./scripts/run-langgraph-studio.sh [options]

Options:
  --host <host>         Bind host (default: 127.0.0.1)
  --port <port>         Bind port (default: 8123)
  --skip-install        Skip dependency installation steps
  --allow-blocking      Pass --allow-blocking to langgraph dev
  -h, --help            Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL="true"
      shift
      ;;
    --allow-blocking)
      ALLOW_BLOCKING="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

VENV_DIR="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
LANGGRAPH_EXE="${VENV_DIR}/bin/langgraph"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  else
    echo "Could not find python3.12 or python3 on PATH." >&2
    exit 1
  fi
  echo "Creating .venv with ${PYTHON_BIN}..."
  "${PYTHON_BIN}" -m venv .venv
fi

echo "Using Python: ${VENV_PYTHON}"
"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel

if [[ "${SKIP_INSTALL}" != "true" ]]; then
  echo "Installing backend dependencies (editable)..."
  "${VENV_PYTHON}" -m pip install -e "./surfsense_backend"
  echo "Installing LangGraph CLI..."
  "${VENV_PYTHON}" -m pip install "langgraph-cli[inmem]"
fi

if [[ ! -x "${LANGGRAPH_EXE}" ]]; then
  echo "Could not find langgraph in .venv. Run again without --skip-install." >&2
  exit 1
fi

CMD=(
  "${LANGGRAPH_EXE}"
  dev
  --config "langgraph.json"
  --host "${HOST}"
  --port "${PORT}"
)
if [[ "${ALLOW_BLOCKING}" == "true" ]]; then
  CMD+=(--allow-blocking)
fi

echo "Starting LangGraph Studio on http://${HOST}:${PORT} ..."
exec "${CMD[@]}"
