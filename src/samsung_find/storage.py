from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


@contextmanager
def locked(path: str | Path) -> Iterator[None]:
    target = expand(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = target.with_suffix(target.suffix + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_json(path: str | Path, *, required: bool = True) -> dict[str, Any]:
    target = expand(path)
    if not target.exists():
        if required:
            raise FileNotFoundError(target)
        return {}
    with target.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid object in {target}")
    return value


def atomic_write_json(path: str | Path, value: dict[str, Any]) -> None:
    target = expand(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def secure_read_text(path: str | Path) -> str:
    target = expand(path)
    value = target.read_text(encoding="utf-8").strip()
    target.unlink(missing_ok=True)
    return value
