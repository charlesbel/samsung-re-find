"""Hardened storage and cross-platform locking abstractions."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
import threading
import uuid
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

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


class _PathLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.rlock = threading.RLock()
        self.fd: int | None = None
        self.count = 0


_path_locks: dict[Path, _PathLock] = {}
_path_locks_guard = threading.Lock()


def _get_path_lock(lock_path: Path) -> _PathLock:
    with _path_locks_guard:
        if lock_path not in _path_locks:
            _path_locks[lock_path] = _PathLock(lock_path)
        return _path_locks[lock_path]


def expand(path: str | Path) -> Path:
    p = Path(path).expanduser()
    _verify_no_symlink_components(p)
    return p.resolve()


def _get_o_nofollow() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _verify_no_symlink_components(path: Path) -> None:
    """Verify that neither the path nor any of its existing ancestor directories are symlinks."""
    curr = path
    while curr != curr.parent:
        if curr.is_symlink():
            raise SecurityError(f"Insecure state path: {curr.name} is a symlink")
        curr = curr.parent


def _check_parent_dir(parent_path: Path, *, for_write: bool = False) -> None:
    _verify_no_symlink_components(parent_path)

    if sys.platform == "win32":
        if not parent_path.exists() and for_write:
            parent_path.mkdir(parents=True, exist_ok=True)
        return

    if not parent_path.exists():
        if for_write:
            parent_path.mkdir(parents=True, exist_ok=True, mode=0o700)
            with contextlib.suppress(OSError):
                parent_path.chmod(0o700)
        return

    parent_stat = parent_path.stat()
    if hasattr(os, "getuid") and parent_stat.st_uid != os.getuid():
        raise SecurityError("Parent directory is not owned by current user")

    parent_mode = stat.S_IMODE(parent_stat.st_mode)
    if parent_mode & 0o077 != 0:
        raise SecurityError(
            f"Insecure directory permissions on {parent_path.name}: mode is 0{parent_mode:o}, must be 0700"
        )


@contextmanager
def locked(path: str | Path) -> Iterator[None]:
    target = Path(path).expanduser()
    _verify_no_symlink_components(target)

    resolved = target.resolve()
    _check_parent_dir(resolved.parent, for_write=True)

    lock_path = resolved.with_suffix(resolved.suffix + ".lock")
    _verify_no_symlink_components(lock_path)

    path_lock = _get_path_lock(lock_path)
    path_lock.rlock.acquire()

    try:
        path_lock.count += 1
        if path_lock.count == 1:
            flags = os.O_CREAT | os.O_RDWR | _get_o_nofollow()
            fd = os.open(lock_path, flags, 0o600)

            # Check descriptor with fstat
            if sys.platform != "win32":
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    os.close(fd)
                    raise SecurityError(f"Lock target {lock_path.name} is not a regular file")
                if hasattr(os, "getuid") and st.st_uid != os.getuid():
                    os.close(fd)
                    raise SecurityError("Lock file is not owned by current user")
                file_mode = stat.S_IMODE(st.st_mode)
                if file_mode & 0o077 != 0:
                    os.close(fd)
                    raise SecurityError(
                        f"Insecure lock file permissions on {lock_path.name}: mode is 0{file_mode:o}, must be 0600"
                    )

            # Process-level locking
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            elif msvcrt is not None:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

            path_lock.fd = fd

        yield

    finally:
        try:
            if path_lock.count == 1 and path_lock.fd is not None:
                fd = path_lock.fd
                path_lock.fd = None
                if fcntl is not None:
                    with contextlib.suppress(OSError):
                        fcntl.flock(fd, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    with contextlib.suppress(OSError):
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                os.close(fd)
        finally:
            path_lock.count -= 1
            path_lock.rlock.release()


def read_json(path: str | Path, *, required: bool = True) -> dict[str, Any]:
    target = Path(path).expanduser()
    _verify_no_symlink_components(target)

    resolved = target.resolve()
    if not resolved.exists():
        if required:
            raise FileNotFoundError(f"Required file not found: {target.name}")
        return {}

    _check_parent_dir(resolved.parent, for_write=False)

    flags = os.O_RDONLY | _get_o_nofollow()
    try:
        fd = os.open(resolved, flags)
    except OSError as exc:
        raise SecurityError(f"Cannot open state file securely: {target.name}") from exc

    try:
        if sys.platform != "win32":
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise SecurityError(f"State file {target.name} is not a regular file")
            if hasattr(os, "getuid") and st.st_uid != os.getuid():
                raise SecurityError("State file is not owned by current user")
            file_mode = stat.S_IMODE(st.st_mode)
            if file_mode & 0o077 != 0:
                raise SecurityError(f"Insecure file permissions on {target.name}: mode is 0{file_mode:o}, must be 0600")

        with os.fdopen(fd, "r", encoding="utf-8") as handle:
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
    _verify_no_symlink_components(target)

    resolved = target.resolve()
    _check_parent_dir(resolved.parent, for_write=True)

    tmp_id = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
    tmp = resolved.with_name(f".{resolved.name}.{tmp_id}.tmp")

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | _get_o_nofollow()
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(tmp, resolved)

        # Sync parent directory descriptor where supported
        if hasattr(os, "O_DIRECTORY") and sys.platform != "win32":
            try:
                dir_flags = os.O_RDONLY | os.O_DIRECTORY | _get_o_nofollow()
                dir_fd = os.open(str(resolved.parent), dir_flags)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass

        if hasattr(os, "chmod") and sys.platform != "win32":
            with contextlib.suppress(OSError):
                resolved.chmod(0o600)

    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def secure_read_text(path: str | Path) -> str:
    target = Path(path).expanduser()
    _verify_no_symlink_components(target)

    resolved = target.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {target.name}")

    _check_parent_dir(resolved.parent, for_write=False)

    flags = os.O_RDONLY | _get_o_nofollow()
    try:
        fd = os.open(resolved, flags)
    except OSError as exc:
        raise SecurityError(f"Cannot open file securely: {target.name}") from exc

    try:
        if sys.platform != "win32":
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise SecurityError(f"File {target.name} is not a regular file")
            if hasattr(os, "getuid") and st.st_uid != os.getuid():
                raise SecurityError("File is not owned by current user")
            file_mode = stat.S_IMODE(st.st_mode)
            if file_mode & 0o077 != 0:
                raise SecurityError(f"Insecure file permissions: mode is 0{file_mode:o}, must be 0600")

        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
    finally:
        with contextlib.suppress(OSError):
            resolved.unlink(missing_ok=True)

    return value
