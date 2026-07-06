#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="$(command -v python3)"
PIP="$PYTHON_BIN -m pip"

echo "Using Python: $PYTHON_BIN ($("$PYTHON_BIN" --version))"

# TensorFlow only publishes wheels for Python 3.9–3.12
PY_MAJOR=$("$PYTHON_BIN" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON_BIN" -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -ne 3 ] || [ "$PY_MINOR" -lt 9 ] || [ "$PY_MINOR" -gt 12 ]; then
    echo ""
    echo "ERROR: TensorFlow requires Python 3.9–3.12. You are running ${PY_MAJOR}.${PY_MINOR}."
    echo ""
    echo "Set a compatible version and re-run:"
    echo "  asdf install python 3.12.13"
    echo "  asdf set python 3.12.13"
    echo ""
    exit 1
fi

# cairo is a system library required by cairosvg (SVG support)
OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
    if ! command -v brew &>/dev/null; then
        echo "WARNING: Homebrew not found — SVG support requires cairo: https://brew.sh"
    elif ! brew list cairo &>/dev/null 2>&1; then
        echo "Installing cairo (required for SVG support)..."
        brew install cairo
    fi
fi

echo "Installing dependencies..."
$PIP install --upgrade pip --quiet
mkdir -p build
$PIP install -e . --quiet

echo ""
echo "Setup complete."
echo ""
echo "To pre-download the DECIMER model now (~500 MB, saves time on first run):"
echo "  python3 main.py --download-model"
echo ""
