#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
export PYTHONUTF8=1
# Prefer a supported, installed interpreter; copied virtualenvs are checked later.
for candidate in python3.12 python3.11 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.12 /usr/local/bin/python3.11 .venv-mac/bin/python python3; do
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) else 1)' >/dev/null 2>&1; then
    "$candidate" launch.py "$@"
    result=$?
    if [ "$result" -ne 0 ]; then read -r -p "Press Return to close..."; fi
    exit "$result"
  fi
done
echo 'Install Python 3.12 from python.org, then double-click Start-AI-Telephone.command again.'
/usr/bin/open 'https://www.python.org/downloads/release/python-31210/'
read -r -p 'Press Return to close...'
exit 1
