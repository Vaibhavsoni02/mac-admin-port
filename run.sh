#!/usr/bin/env bash
# Fresh-system launcher: install deps + start Streamlit on this machine.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "==> Using: $($PY --version) @ $(command -v "$PY")"

if [[ ! -d .venv ]]; then
  echo "==> Creating .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo "==> Starting Mac Admin Analytics on http://0.0.0.0:8501"
echo "    This computer: http://127.0.0.1:8501"
exec python -m streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
