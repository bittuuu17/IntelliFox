#!/usr/bin/env bash
# Intellifox — run API locally (macOS / Linux / WSL)
set -e
cd "$(dirname "$0")"

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit .env and set GEMINI_API_KEY."
fi

if [[ ! -d .venv ]]; then
  echo "Create a venv first:  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate
pip install -r requirements.txt -q

if [[ ! -f banking_knowledge.json ]]; then
  echo "Generating banking_knowledge.json ..."
  python build_banking_knowledge.py
fi

export UVICORN_RELOAD="${UVICORN_RELOAD:-1}"
export UVICORN_HOST="${UVICORN_HOST:-127.0.0.1}"

echo "Starting http://${UVICORN_HOST}:${PORT:-8080} (reload=$UVICORN_RELOAD)"
python main.py
