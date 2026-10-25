#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_python="${BAILONG_BUILD_PYTHON:-$repo_root/.venv/bin/python}"
test_state="${BAILONG_TEST_STATE_DIR:-$repo_root/build/test-state}"

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  printf 'These macOS release checks require an Apple Silicon Mac.\n' >&2
  exit 1
fi
if [[ ! -f "$repo_root/outputs/白龙桌宠素材/素材清单.json" ]]; then
  printf 'Animation assets are missing. Run: %s scripts/fetch_assets.py\n' "$build_python" >&2
  exit 1
fi

# File providers can mark .dylib files hidden, preventing Qt discovery. Test a
# private copy of the platform plugins in a normal local temporary directory.
qt_plugins="$("$build_python" -c 'import pathlib,PySide6; print(pathlib.Path(PySide6.__file__).parent/"Qt/plugins/platforms")')"
test_plugins="$(mktemp -d /private/tmp/bailong-test-plugins.XXXXXX)"
trap 'rm -rf "$test_plugins"' EXIT
"$build_python" - "$qt_plugins" "$test_plugins/platforms" <<'PY'
from pathlib import Path
import shutil
import sys
source, target = map(Path, sys.argv[1:])
# Copy bytes only: file-provider flags and protected metadata are not part of
# a Qt plugin and can otherwise make an ordinary temporary copy fail.
target.mkdir()
for path in source.glob('*.dylib'):
    shutil.copyfile(path, target/path.name)
PY
chflags -R nohidden "$test_plugins"
export QT_QPA_PLATFORM=offscreen
export QT_QPA_PLATFORM_PLUGIN_PATH="$test_plugins/platforms"
export BAILONG_DATA_DIR="$test_state/unit"
"$build_python" -m unittest discover -s "$repo_root/app" -p 'test_*.py' -v

# This mode exercises local UI and artwork only. It never sends a Codex task.
BAILONG_DATA_DIR="$test_state/source-smoke" "$build_python" "$repo_root/app/pet.py" --self-test
printf 'Offline macOS checks passed.\n'
