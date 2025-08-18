# recycle.py
# Safe "Recycle" moves using a local hidden folder + manifest

from __future__ import annotations
import os
import json
import shutil
from typing import Dict, Optional

RECYCLE_DIR_NAME = ".cleanup_recycle"
MANIFEST_FILE = "manifest.json"


def ensure_recycle(root: str) -> str:
    """Ensure a recycle folder under `root` and return its path."""
    recycle_dir = os.path.join(root, RECYCLE_DIR_NAME)
    os.makedirs(recycle_dir, exist_ok=True)
    manifest = os.path.join(recycle_dir, MANIFEST_FILE)
    if not os.path.exists(manifest):
        with open(manifest, 'w', encoding='utf-8') as f:
            json.dump({}, f)
    return recycle_dir


def _manifest_path(recycle_dir: str) -> str:
    return os.path.join(recycle_dir, MANIFEST_FILE)


def load_manifest(recycle_dir: str) -> Dict[str, str]:
    try:
        with open(_manifest_path(recycle_dir), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_manifest(recycle_dir: str, data: Dict[str, str]) -> None:
    with open(_manifest_path(recycle_dir), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def move_to_recycle(root: str, src_path: str) -> Optional[str]:
    """Move `src_path` into recycle dir; record original path. Return new path."""
    recycle_dir = ensure_recycle(root)
    if not os.path.exists(src_path):
        return None

    base = os.path.basename(src_path)
    dst = os.path.join(recycle_dir, base)

    # Handle name collisions inside recycle
    i = 1
    while os.path.exists(dst):
        name, ext = os.path.splitext(base)
        dst = os.path.join(recycle_dir, f"{name} ({i}){ext}")
        i += 1

    shutil.move(src_path, dst)

    manifest = load_manifest(recycle_dir)
    manifest[dst] = src_path  # key = current recycled path, value = original path
    save_manifest(recycle_dir, manifest)
    return dst


def restore_from_recycle(recycle_dir: str, recycled_path: str) -> bool:
    """Restore a recycled file to its original location."""
    manifest = load_manifest(recycle_dir)
    original = manifest.get(recycled_path)
    if not original or not os.path.exists(recycled_path):
        return False
    os.makedirs(os.path.dirname(original), exist_ok=True)
    shutil.move(recycled_path, original)
    manifest.pop(recycled_path, None)
    save_manifest(recycle_dir, manifest)
    return True


def delete_permanently(recycle_dir: str, recycled_path: str) -> bool:
    try:
        if os.path.isdir(recycled_path):
            shutil.rmtree(recycled_path)
        else:
            os.remove(recycled_path)
        manifest = load_manifest(recycle_dir)
        manifest.pop(recycled_path, None)
        save_manifest(recycle_dir, manifest)
        return True
    except Exception:
        return False