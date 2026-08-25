from __future__ import annotations

import os
import sys
from pathlib import Path

from .constants import DEFAULT_REDIRECT_PATH


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("ms-app://"):
        return 2
    target = Path(os.environ.get("SAMSUNG_FIND_REDIRECT_PATH", DEFAULT_REDIRECT_PATH)).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(sys.argv[1])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
