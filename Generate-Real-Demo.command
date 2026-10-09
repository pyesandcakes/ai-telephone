#!/bin/bash
cd "$(dirname "$0")" || exit 1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_OFFLINE=1
exec /usr/bin/caffeinate -i .venv-mac/bin/python generate_real_demo.py
