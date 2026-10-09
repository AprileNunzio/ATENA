import hashlib
from pathlib import Path

SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".part"}
MAX_FILES = 2000
MAX_BYTES = 8 * 1024 * 1024


class FolderFingerprint:
    def __init__(self, ignore: tuple[str, ...] = ()) -> None:
        self._cache: dict[tuple, str] = {}
        self._ignore = tuple(token.encode("utf-8") for token in ignore if token)

    def _file_digest(self, path: Path, stat) -> str:
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        digest = self._cache.get(key)
        if digest is None:
            hasher = hashlib.sha256()
            if stat.st_size <= MAX_BYTES:
                content = path.read_bytes()
                for token in self._ignore:
                    content = content.replace(token, b"")
                hasher.update(content)
            else:
                hasher.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
            digest = hasher.hexdigest()
            self._cache[key] = digest
        return digest

    def __call__(self, folder: Path) -> str:
        hasher = hashlib.sha256()
        files = sorted(p for p in folder.rglob("*")
                       if p.is_file() and not p.is_symlink() and p.suffix not in SKIP_SUFFIXES
                       and not SKIP_DIRS.intersection(p.relative_to(folder).parts))[:MAX_FILES]
        for path in files:
            try:
                digest = self._file_digest(path, path.stat())
            except OSError:
                continue
            hasher.update(path.relative_to(folder).as_posix().encode())
            hasher.update(b"\0")
            hasher.update(digest.encode())
        return hasher.hexdigest()
