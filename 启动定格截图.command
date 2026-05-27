#!/bin/zsh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "$PROJECT_DIR" || exit 1
"$PYTHON_BIN" "$PROJECT_DIR/定格截图.py"
