#!/usr/bin/env bash
# FuelSense — one-command launcher.
# Installs backend deps, trains the model if artifacts are missing, and serves
# the API + static frontend on http://127.0.0.1:8000

set -e
cd "$(dirname "$0")/backend"

echo "▸ Installing dependencies…"
pip install -q -r requirements.txt

if [ ! -f artifacts/model.joblib ]; then
  echo "▸ No model found — training from data/vehicles_data_2022.csv…"
  python -m ml.train
else
  echo "▸ Model artifact present (run 'python -m ml.train' from backend/ to retrain)."
fi

echo "▸ Starting FuelSense at http://127.0.0.1:8000"
exec python -m uvicorn main:app --host 127.0.0.1 --port 8000
