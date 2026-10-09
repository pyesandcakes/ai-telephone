#!/bin/bash
cd "$(dirname "$0")" || exit 1
# Reuse the running installation rather than start a competing server.
if /usr/bin/curl --silent --fail --max-time 3 http://127.0.0.1:8765/api/state | /usr/bin/grep -q '"progress":'; then
  echo "AI Telephone is already running. Opening the existing controller."
  /usr/bin/open http://127.0.0.1:8765/
  exit 0
fi
if /usr/sbin/lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8765 is occupied by another service. Close that service before starting AI Telephone."
  exit 1
fi
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
mkdir -p tmp
if ! .venv-mac/bin/python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=2)' >/dev/null 2>&1; then
  /opt/homebrew/bin/ollama serve >tmp/ollama-live.log 2>&1 &
fi
exec /usr/bin/caffeinate -i .venv-mac/bin/python app.py --demo
