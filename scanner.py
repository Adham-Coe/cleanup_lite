# scanner.py
# Core, memory-efficient scanning & hashing utilities used by the UI

from __future__ import annotations
import os
import hashlib
import time
from typing import Generator, List, Tuple, Dict, Optional

# ===============
# File iteration
# ===============

def walk_files(root: str) -> Generator[str, None, None]:
    """Yield full file paths under `root` (streaming)."""
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            yield os.path.join(dirpath, name)


def big_files(root: str, min_size_bytes: int,
              stop_flag, pause_flag) -> Generator[Tuple[str, int], None, None]:
    """Yield (path, size_bytes) for files >= min_size_bytes.

    Respects stop_flag and pause_flag.
    """
    for path in walk_files(root):
        if stop_flag.is_set():
            return
        pause_flag.wait()
        try:
            size = os.path.getsize(path)
        except OSError:
            # skip unreadable files
            continue
        if size >= min_size_bytes:
            yield path, size


# ======================
# Content hashing (chunked)
# ======================

def hash_file(path: str, stop_flag, pause_flag,
              chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Return SHA-256 of file contents reading in small chunks.

    - Respects pause/stop flags during long reads.
    - Returns None on permission errors, etc.
    """
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                if stop_flag.is_set():
                    return None
                pause_flag.wait()
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ===============================
# Duplicate detection (size -> hash)
# ===============================

def duplicate_groups(root: str,
                     min_size_bytes: int,
                     executor,
                     stop_flag, pause_flag) -> Generator[List[str], None, None]:
    """Yield lists of duplicate file paths (≥2 files with identical content).

    Strategy:
      1) Stream files and group by size.
      2) For each size group with >1 path, compute hashes in a small thread pool.
      3) Yield groups of files sharing the same hash.
    """
    size_buckets: Dict[int, List[str]] = {}

    for path in walk_files(root):
        if stop_flag.is_set():
            return
        pause_flag.wait()
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size < min_size_bytes:
            continue
        bucket = size_buckets.setdefault(size, [])
        bucket.append(path)
        # Heuristic: when a bucket gets big, process and clear to cap memory
        if len(bucket) >= 64:
            # process this size group in batches
            yield from _process_size_group(size_buckets.pop(size), executor, stop_flag, pause_flag)

    # process remaining buckets
    for size, paths in list(size_buckets.items()):
        if stop_flag.is_set():
            return
        yield from _process_size_group(paths, executor, stop_flag, pause_flag)


def _process_size_group(paths: List[str], executor, stop_flag, pause_flag) -> Generator[List[str], None, None]:
    """Hash candidates in a thread pool and yield duplicate groups."""
    if len(paths) < 2:
        return
    futures = {executor.submit(hash_file, p, stop_flag, pause_flag): p for p in paths}
    by_hash: Dict[str, List[str]] = {}
    for fut in futures:
        try:
            h = fut.result()
        except Exception:
            # hashing failed for this file
            continue
        if h is None:
            continue
        by_hash.setdefault(h, []).append(futures[fut])

    for group in by_hash.values():
        if len(group) >= 2:
            yield group
