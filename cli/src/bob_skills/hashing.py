"""Content digests for skills and packs.

A directory digest is sha256 over the lines ``<relative posix path>\\n<sha256 of
file>\\n`` for every regular file under the directory, sorted by path. Ignored
entries: ``.DS_Store``, ``Thumbs.db``, ``__pycache__``, ``.git``, ``*.pyc``.
Symlinks are refused so a skill can never point outside its own folder.

The same function is used by the registry (pack.json checksums), the installer
(lock file) and the guard hook, so a digest computed anywhere compares equal.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

IGNORED_NAMES = {".DS_Store", "Thumbs.db", "__pycache__", ".git"}
IGNORED_SUFFIXES = {".pyc"}


class DigestError(Exception):
    """Raised when a tree cannot be hashed safely."""


def iter_files(root: Path) -> Iterator[Path]:
    """Yield regular files under ``root`` in digest order. Refuses symlinks."""
    root = Path(root)
    if not root.is_dir():
        raise DigestError(f"not a directory: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in rel.parts):
            continue
        if path.is_symlink():
            raise DigestError(f"symlink not allowed inside a skill: {rel.as_posix()}")
        if path.is_file() and path.suffix not in IGNORED_SUFFIXES:
            files.append(path)
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    yield from files


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    """Digest of a directory, as ``sha256:<hex>``."""
    digest = hashlib.sha256()
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        digest.update(f"{rel}\n{file_sha256(path)}\n".encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def path_digest(path: Path) -> str:
    """Digest of a directory or a single file, as ``sha256:<hex>``."""
    path = Path(path)
    if path.is_dir():
        return tree_digest(path)
    if path.is_symlink():
        raise DigestError(f"symlink not allowed: {path}")
    return "sha256:" + file_sha256(path)
