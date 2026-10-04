"""File selection and bounded, link-free snapshots for packaging and review.

On POSIX, traversal is anchored to directory descriptors with O_NOFOLLOW so a
concurrent symlink swap cannot redirect a read. Other platforms reject links and
junctions and check file identity; do not mutate a source tree during a snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import stat

EXCLUDED_DIRS = {'.git', '.hg', '.svn', '.venv', 'venv', 'node_modules',
                 '__pycache__', '.pytest_cache', 'runs', 'dist', '.ssh', '.aws', '.azure', '.gnupg', '.kube'}
SECRET_PATTERNS = ('.env', '.env.*', '*.pem', '*.key', 'id_rsa*', 'id_ed25519*',
                   '.npmrc', '.pypirc', '.netrc', 'credentials', 'credentials*.json', 'secrets.*')
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TREE_BYTES = 100 * 1024 * 1024


def excluded(relative: Path, *, review=False) -> bool:
    """Return whether a relative source path is excluded; review mode includes evals."""
    if any(p.lower() in EXCLUDED_DIRS for p in relative.parts):
        return True
    name = relative.name.lower()
    if name in {'.ds_store'} or name.endswith(('.pyc', '.pyo', '.skill')):
        return True
    if not review and relative.parts[0] == 'evals':
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_PATTERNS)


@dataclass(frozen=True)
class SourceFile:
    data: bytes
    mode: int


def snapshot(root: Path, *, review=False) -> dict[str, SourceFile]:
    """Read regular source files once; reject links, devices, and oversized input."""
    root = Path(root).resolve(strict=True)
    result = {}
    total = 0
    anchored = (os.name == 'posix' and os.open in os.supports_dir_fd
                and os.scandir in os.supports_fd and hasattr(os, 'O_NOFOLLOW'))

    def visit(directory, relative=Path()):
        """Collect permitted files recursively while enforcing identity and size limits."""
        nonlocal total
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                rel = relative / entry.name
                if excluded(rel, review=review):
                    continue
                info = entry.stat(follow_symlinks=False)
                path = root / rel
                if stat.S_ISLNK(info.st_mode) or (not anchored and path.is_junction()):
                    raise ValueError(f'Links are not allowed in skill sources: {rel}')
                if stat.S_ISDIR(info.st_mode):
                    if anchored:
                        fd = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                        try:
                            visit(fd, rel)
                        finally:
                            os.close(fd)
                    else:
                        visit(path, rel)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(f'Not a regular source file: {rel}')
                flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                fd = os.open(entry.name, flags, dir_fd=directory) if anchored else os.open(path, flags)
                with os.fdopen(fd, 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError(f'Source changed while reading: {rel}')
                    data = stream.read(MAX_FILE_BYTES + 1)
                    if len(data) > MAX_FILE_BYTES:
                        raise ValueError(f'Source file exceeds 20 MiB: {rel}')
                total += len(data)
                if total > MAX_TREE_BYTES:
                    raise ValueError('Skill source exceeds 100 MiB')
                result[rel.as_posix()] = SourceFile(data, stat.S_IMODE(opened.st_mode) & 0o777)

    if anchored:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            visit(fd)
        finally:
            os.close(fd)
    else:
        visit(root)
    return result


def source_manifest(root: Path) -> dict[str, str]:
    """Hash reviewable source bytes, omitting review.yaml to avoid hashing the record itself."""
    return {name: hashlib.sha256(item.data).hexdigest()
            for name, item in snapshot(root, review=True).items() if name != 'review.yaml'}


def copy_snapshot(files: dict[str, SourceFile], target: Path) -> None:
    """Materialize a captured snapshot in a new private temporary directory."""
    target.mkdir(parents=True, exist_ok=False)
    for name, item in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(item.data)
        path.chmod(item.mode)


def package_files(files: dict[str, SourceFile]) -> dict[str, SourceFile]:
    """Optionally restrict distribution to an exact, author-supplied file list.

    The manifest cannot re-include files excluded by the shared security policy.
    """
    manifest_name = 'package-manifest.json'
    if manifest_name not in files:
        return files
    manifest = json.loads(files[manifest_name].data)
    names = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError('package-manifest.json must contain a files list of relative filenames')
    if 'SKILL.md' not in names or any(name not in files for name in names):
        raise ValueError('Package manifest must include SKILL.md and only existing, permitted files')
    selected = set(names) | {manifest_name}
    # Keep the evidence alongside the reviewed package when present.
    if 'review.yaml' in files:
        selected.add('review.yaml')
    return {name: item for name, item in files.items() if name in selected}
