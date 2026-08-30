from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .exceptions import SecurityError, StorageError

# Platform-specific locking
try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

_acquired_locks: dict[Path, tuple[int, int]] = {}
_lock_mutex = threading.Lock()


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def ensure_secure_permissions(path: Path) -> None:
    """Verify and enforce secure POSIX permissions (0600 for file, 0700 for parent)."""
    if sys.platform == "win32":
        return

    # Check symlinks
    if path.is_symlink():
        raise SecurityError(f"Insecure state path: {path.name} is a symlink")

    if path.parent.exists():
        if path.parent.is_symlink():
            raise SecurityError(f"Insecure directory: {path.parent.name} is a symlink")
        parent_stat = path.parent.stat()
        # Verify ownership matches current user
        if hasattr(os, "getuid") and parent_stat.st_uid != os.getuid():
            raise SecurityError("Parent directory is not owned by current user")
        # Enforce 0700
        parent_mode = stat.S_IMODE(parent_stat.st_mode)
        if parent_mode & 0o077 != 0:
            try:
                path.parent.chmod(0o700)
            except OSError as exc:
                raise SecurityError("Failed to enforce private directory permissions") from exc

    if path.exists():
        file_stat = path.stat()
        if hasattr(os, "getuid") and file_stat.st_uid != os.getuid():
            raise SecurityError("State file is not owned by current user")
        file_mode = stat.S_IMODE(file_stat.st_mode)
        if file_mode & 0o077 != 0:
            try:
                path.chmod(0o600)
            except OSError as exc:
                raise SecurityError("Failed to enforce private file permissions") from exc


@contextmanager
def locked(path: str | Path) -> Iterator[None]:
    target = expand(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = target.with_suffix(target.suffix + ".lock").resolve()

    with _lock_mutex:
        if lock_path in _acquired_locks:
            fd, count = _acquired_locks[lock_path]
            _acquired_locks[lock_path] = (fd, count + 1)
        else:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            _acquired_locks[lock_path] = (fd, 1)

    try:
        yield
    finally:
        with _lock_mutex:
            if lock_path in _acquired_locks:
                fd, count = _acquired_locks[lock_path]
                if count > 1:
                    _acquired_locks[lock_path] = (fd, count - 1)
                else:
                    del _acquired_locks[lock_path]
                    if fcntl is not None:
                        with contextlib.suppress(OSError):
                            fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)


def read_json(path: str | Path, *, required: bool = True) -> dict[str, Any]:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise SecurityError(f"Rejected reading from symlink: {target.name}")

    resolved = target.resolve()
    if not resolved.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {target.name}")
        return {}

    ensure_secure_permissions(resolved)

    try:
        with resolved.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except json.JSONDecodeError as exc:
        raise StorageError(f"Invalid JSON in {target.name}") from exc
    except OSError as exc:
        raise StorageError(f"Cannot read file {target.name}") from exc

    if not isinstance(value, dict):
        raise StorageError(f"Invalid object structure in {target.name}")
    return value


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise SecurityError(f"Refusing to write to symlink: {target.name}")

    resolved = target.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if hasattr(os, "chmod") and sys.platform != "win32":
        with contextlib.suppress(OSError):
            resolved.parent.chmod(0o700)

    tmp = resolved.with_name(f".{resolved.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, resolved)
        if hasattr(os, "chmod") and sys.platform != "win32":
            resolved.chmod(0o600)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def secure_read_text(path: str | Path) -> str:
    target = Path(path).expanduser()
    if target.is_symlink():
        raise SecurityError(f"Rejected reading from symlink: {target.name}")
    resolved = target.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {target.name}")
    ensure_secure_permissions(resolved)
    value = resolved.read_text(encoding="utf-8").strip()
    resolved.unlink(missing_ok=True)
    return value
