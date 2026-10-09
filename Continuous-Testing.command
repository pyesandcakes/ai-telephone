#!/bin/bash
cd "$(dirname "$0")" || exit 1
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
mkdir -p tmp
if ! .venv-mac/bin/python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=2)' >/dev/null 2>&1; then
  /opt/homebrew/bin/ollama serve >tmp/ollama-live.log 2>&1 &
fi
exec /usr/bin/caffeinate -i .venv-mac/bin/python app.py --testing
