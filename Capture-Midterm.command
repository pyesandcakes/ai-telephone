#!/bin/bash
set -e
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Complete the real-model .venv setup in README.md first.'
  exit 1
fi
.venv/bin/python -m pip install -r requirements-capture.txt
caffeinate -i .venv/bin/python capture.py "$@"
