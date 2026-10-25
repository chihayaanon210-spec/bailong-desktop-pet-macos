"""Read-only bundled resources and writable per-user state are separate."""
import os
from pathlib import Path
import sys


def app_bundle_path():
    if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
        return next((p for p in Path(sys.executable).resolve().parents if p.suffix == '.app'), None)
    return None


def resource_root():
    bundle = app_bundle_path()
    if bundle is not None:
        return bundle / 'Contents' / 'Resources'
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def data_root():
    override = os.environ.get('BAILONG_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'BailongPetMac'
    return resource_root() / 'app'
