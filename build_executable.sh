#!/usr/bin/env bash
# =============================================================================
# build_executable.sh — build the single-file Keryx Wallet executable.
#
# Builds on Ubuntu 22.04, 24.04, and 26.04. IMPORTANT: a PyInstaller binary is
# only guaranteed to run on the same or NEWER glibc than the machine it was
# built on. For the widest compatibility, build on the OLDEST Ubuntu you intend
# to support (e.g. build on 22.04 to also run on 24.04 and 26.04).
#
# Produces dist/keryx-wallet, a self-contained executable that bundles the
# Python wallet and its libraries. keryx-cli is NOT bundled — it stays
# user-supplied and is found at runtime via PATH / $KERYX_CLI / --cli-path.
#
# Usage:
#   chmod +x build_executable.sh
#   ./build_executable.sh
# =============================================================================
set -euo pipefail

echo "== Keryx Wallet — executable build =="

# 1. System libs PyQt6 needs at runtime (safe to re-run).
# Package names differ slightly across Ubuntu releases:
#   - 22.04 (jammy): libgl1-mesa-glx
#   - 24.04 / 26.04: libgl1
# We try the modern name first, fall back to the legacy one.
echo "-- installing system Qt dependencies (sudo) --"
sudo apt update
sudo apt install -y python3-venv python3-pip libegl1 libxkbcommon0 \
    libdbus-1-3 upx-ucl || true
# libGL: try the current name, then the 22.04 name.
sudo apt install -y libgl1 || sudo apt install -y libgl1-mesa-glx || true
# Some minimal images also need these for the xcb platform plugin:
sudo apt install -y libxcb-cursor0 libxcb-xinerama0 || true

# 2. Isolated build environment.
echo "-- creating build virtualenv --"
python3 -m venv .build-venv
source .build-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 3. Build.
echo "-- running PyInstaller --"
rm -rf build dist
pyinstaller keryx-wallet.spec

deactivate

echo ""
if [ -f dist/keryx-wallet ]; then
    echo "SUCCESS: dist/keryx-wallet"
    echo "Size: $(du -h dist/keryx-wallet | cut -f1)"
    echo ""
    echo "Run it:"
    echo "  ./dist/keryx-wallet"
    echo "  ./dist/keryx-wallet --cli-path /path/to/keryx-cli"
    echo "Or set: export KERYX_CLI=/path/to/keryx-cli"
else
    echo "Build did not produce dist/keryx-wallet — check the PyInstaller output above."
    exit 1
fi
