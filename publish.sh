#!/bin/bash
set -e

VENV_DIR="venv"

# 1. Setup Virtual Environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at '$VENV_DIR'..."
    python3 -m venv "$VENV_DIR"
else
    echo "Found existing virtual environment."
fi

echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 2. Install/Upgrade Dependencies
echo "Upgrading pip and installing build tools..."
pip install --upgrade pip build twine

# 3. Clean up old build artifacts
echo "Cleaning up old build artifacts..."
rm -rf dist/ build/ *.egg-info/

# 4. Build the package
echo "Building the wheel and source distribution..."
python3 -m build

# 5. Upload to PyPI
echo "--------------------------------------------------"
echo "Ready to upload to PyPI."
echo "You will be prompted for your username and password."
echo "Username: __token__"
echo "Password: <Your PyPI Token starting with pypi-...>"
echo "--------------------------------------------------"
twine upload dist/*

echo "Successfully published to PyPI!"