#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_python="${BAILONG_BUILD_PYTHON:-$repo_root/.venv/bin/python}"
build_dist="${BAILONG_DIST_DIR:-$repo_root/dist}"
export PYINSTALLER_CONFIG_DIR="$repo_root/build/pyinstaller-cache"
qt_plugins="$("$build_python" -c 'import pathlib,PySide6; print(pathlib.Path(PySide6.__file__).parent/"Qt/plugins")')"
chflags -R nohidden "$qt_plugins"
"$build_python" -m PyInstaller --noconfirm --clean \
  --distpath "$build_dist" --workpath "$repo_root/build/macos" \
  "$repo_root/macos/BailongPet.spec"
chflags -R nohidden "$build_dist/BailongPet.app"
codesign --verify --deep --strict "$build_dist/BailongPet.app"
printf 'Built: %s\n' "$build_dist/BailongPet.app"
