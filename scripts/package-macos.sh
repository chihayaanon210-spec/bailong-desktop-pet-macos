#!/bin/bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_python="${BAILONG_BUILD_PYTHON:-$repo_root/.venv/bin/python}"
build_dist="${BAILONG_DIST_DIR:-$repo_root/dist}"
release_dir="${BAILONG_RELEASE_DIR:-$repo_root/release}"
include_source=false
for argument in "$@"; do
  case "$argument" in
    --include-source) include_source=true ;;
    --help)
      printf 'Usage: bash scripts/package-macos.sh [--include-source]\n'
      printf 'BAILONG_DIST_DIR selects the directory containing BailongPet.app.\n'
      printf 'BAILONG_RELEASE_DIR selects the output directory.\n'
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  printf 'Packaging requires an Apple Silicon Mac.\n' >&2
  exit 1
fi
app_bundle="$build_dist/BailongPet.app"
app_executable="$app_bundle/Contents/MacOS/BailongPet"
if [[ ! -x "$app_executable" ]]; then
  printf 'Built application not found: %s\nRun scripts/build-macos.sh first.\n' "$app_bundle" >&2
  exit 1
fi
bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app_bundle/Contents/Info.plist")"
if [[ "$bundle_id" != local.bailongpet.macos ]]; then
  printf 'Refusing to package an unrelated application.\n' >&2
  exit 1
fi
if [[ "$(lipo -archs "$app_executable")" != arm64 ]]; then
  printf 'This release filename is reserved for an arm64 application.\n' >&2
  exit 1
fi
version="$("$build_python" -c 'import runpy,sys; print(runpy.run_path(sys.argv[1])["VERSION"])' "$repo_root/app/version.py")"
if [[ ! "$version" =~ ^[0-9][A-Za-z0-9.+_-]*$ ]]; then
  printf 'Invalid release version.\n' >&2
  exit 1
fi
mkdir -p "$release_dir" "$repo_root/build"
codesign --verify --deep --strict "$app_bundle"
BAILONG_DATA_DIR="$repo_root/build/release-smoke-state" "$app_executable" --self-test
"$build_python" - "$repo_root/build/release-smoke-state/检查报告.json" "$version" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if not report.get('passed') or not report.get('frozen') or report.get('version') != sys.argv[2]:
    raise SystemExit('Packaged app self-test/version does not match the source release version.')
PY

app_archive="$release_dir/BailongPet-Mac-$version-arm64.zip"
ditto -c -k --keepParent "$app_bundle" "$app_archive.partial"
unzip -t "$app_archive.partial" > "$repo_root/build/app-archive-check.log"
mv "$app_archive.partial" "$app_archive"
archives=("$app_archive")

if [[ "$include_source" == true ]]; then
  source_archive="$release_dir/BailongPet-Mac-source-$version.zip"
  "$build_python" - "$repo_root" "$source_archive" "$version" <<'PY'
from pathlib import Path
import sys
import zipfile

root, target, version = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
prefix = Path('bailong-desktop-pet-macos-' + version)
selected = []
for folder in ('.github', 'app', 'docs', 'licenses', 'macos', 'scripts', 'upstream-notices'):
    directory = root / folder
    if not directory.is_dir():
        continue
    for path in directory.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if ('__pycache__' in relative.parts or path.name == '.DS_Store'
                or path.suffix == '.pyc' or any(part.endswith('.iconset') for part in relative.parts)):
            continue
        if folder == 'app' and not (path.suffix == '.py' or 'sounds' in relative.parts):
            continue
        if folder == 'macos' and path.suffix not in ('.spec', '.icns'):
            continue
        selected.append(path)
for name in ('.gitignore', '.gitattributes', 'README.md', 'CHANGELOG.md', 'RELEASE_NOTES.md',
             'NOTICE.md', 'ASSETS.md', 'MACOS.txt', 'BUILD_INFO.json', 'THIRD_PARTY_NOTICES.md',
             'requirements.txt', 'requirements-build.txt', 'VERSION.txt'):
    if (root / name).is_file():
        selected.append(root / name)
temporary = target.with_suffix(target.suffix + '.partial')
with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(set(selected)):
        archive.write(path, prefix / path.relative_to(root))
    corrupt = archive.testzip()
    if corrupt:
        raise RuntimeError('Source archive verification failed: ' + corrupt)
temporary.replace(target)
print('Created clean source archive:', target.name)
PY
  archives+=("$source_archive")
fi

# Checksums name only the portable release files, never the builder's paths.
checksum_file="$release_dir/SHA256SUMS.txt"
: > "$checksum_file"
for archive in "${archives[@]}"; do
  digest="$(shasum -a 256 "$archive")"
  printf '%s  %s\n' "${digest%% *}" "$(basename "$archive")" >> "$checksum_file"
done
printf 'Verified release files: %s\n' "$release_dir"
