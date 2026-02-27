#!/usr/bin/env bash

# simple wrapper that runs run_daily.py from the project root
# usage: ./run_daily.sh

set -e
cd "$(dirname "$0")"

# activate virtualenv if you have one
if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
fi

python3 run_daily.py

# if the db changed, commit & push so that Streamlit Cloud / GitHub Actions
# see the newest file
if git diff --quiet screener.db; then
    echo "no database changes"
else
    git add screener.db
    git commit -m "daily update $(date +%F)" || true
    git push origin main
fi
