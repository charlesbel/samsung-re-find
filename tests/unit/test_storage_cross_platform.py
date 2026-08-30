import concurrent.futures
import json
import multiprocessing
import os
import stat
import sys
from pathlib import Path

import pytest

from samsung_find import storage
from samsung_find.credentials import resolve_master_state_path
from samsung_find.exceptions import SecurityError
from samsung_find.storage import (
    atomic_write_json,
    locked,
    read_json,
)


def _worker_increment(file_path: str, iterations: int):
    target = Path(file_path)
    for _ in range(iterations):
        with locked(target):
            try:
                data = read_json(target, required=False)
            except Exception:
                data = {}
            count = data.get("count", 0) + 1
            atomic_write_json(target, {"count": count})


def test_windows_lock_backend_uses_msvcrt_locking_contract(tmp_path, monkeypatch):
    class FakeMsvcrt:
        LK_LOCK = 1
        LK_UNLCK = 2

        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        def locking(self, fd: int, mode: int, length: int) -> None:
            assert fd >= 0
            self.calls.append((mode, length))

    fake = FakeMsvcrt()
    monkeypatch.setattr(storage, "fcntl", None)
    monkeypatch.setattr(storage, "msvcrt", fake)

    with locked(tmp_path / "windows-state.json"):
        pass

    assert fake.calls == [(fake.LK_LOCK, 1), (fake.LK_UNLCK, 1)]


def test_thread_contention_locking(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"count": 0})

    num_threads = 8
    iterations_per_thread = 25

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker_increment, str(target), iterations_per_thread) for _ in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    final_data = read_json(target)
    assert final_data["count"] == num_threads * iterations_per_thread


def test_multiprocess_contention_locking(tmp_path):
    target = tmp_path / "proc_state.json"
    atomic_write_json(target, {"count": 0})

    num_procs = 4
    iterations_per_proc = 15

    procs = [
        multiprocessing.Process(
            target=_worker_increment,
            args=(str(target), iterations_per_proc),
        )
        for _ in range(num_procs)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
        assert p.exitcode == 0

    final_data = read_json(target)
    assert final_data["count"] == num_procs * iterations_per_proc


def test_read_json_fails_closed_on_insecure_permissions(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX permissions not applicable on Windows")

    target = tmp_path / "insecure_state.json"
    target.write_text(json.dumps({"key": "val"}), encoding="utf-8")
    target.chmod(0o644)  # Insecure (group/world readable)

    with pytest.raises(SecurityError) as exc_info:
        read_json(target)
    assert "Insecure" in str(exc_info.value) or "permissions" in str(exc_info.value)

    # Must NOT have silently chmodded the file
    current_mode = stat.S_IMODE(target.stat().st_mode)
    assert current_mode == 0o644, "File should remain 0644; should fail closed without altering attacker file"


def test_insecure_lock_file_fails_closed(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX permissions not applicable on Windows")

    target = tmp_path / "state.json"
    lock_file = tmp_path / "state.json.lock"
    lock_file.write_text("", encoding="utf-8")
    lock_file.chmod(0o666)  # Insecure lock permissions

    with pytest.raises(SecurityError) as exc_info, locked(target):
        pass
    assert "Insecure" in str(exc_info.value) or "mode" in str(exc_info.value) or "permission" in str(exc_info.value)
    assert stat.S_IMODE(lock_file.stat().st_mode) == 0o666


def test_insecure_parent_directory_fails_closed_on_read_and_write(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX permissions not applicable on Windows")

    parent_dir = tmp_path / "insecure_dir"
    parent_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    os.chmod(parent_dir, 0o755)  # Group/other readable/executable

    target = parent_dir / "data.json"
    target.write_text(json.dumps({"a": "b"}), encoding="utf-8")
    os.chmod(target, 0o600)

    # Read should fail closed because parent dir is 0755
    with pytest.raises(SecurityError) as exc_read:
        read_json(target)
    assert "Insecure" in str(exc_read.value) or "parent" in str(exc_read.value) or "directory" in str(exc_read.value)

    # Write should fail closed because existing parent dir is 0755
    with pytest.raises(SecurityError) as exc_write:
        atomic_write_json(target, {"a": "c"})
    assert "Insecure" in str(exc_write.value) or "parent" in str(exc_write.value) or "directory" in str(exc_write.value)

    # Parent mode must not have been silently changed
    assert stat.S_IMODE(parent_dir.stat().st_mode) == 0o755


def test_symlink_parent_directory_rejection(tmp_path):
    real_parent = tmp_path / "real_dir"
    real_parent.mkdir(mode=0o700)

    symlink_parent = tmp_path / "symlink_dir"
    try:
        symlink_parent.symlink_to(real_parent)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    target = symlink_parent / "state.json"
    with pytest.raises(SecurityError):
        read_json(target, required=False)

    with pytest.raises(SecurityError):
        atomic_write_json(target, {"key": "val"})

    with pytest.raises(SecurityError), locked(target):
        pass


def test_symlink_rejection(tmp_path):
    real_file = tmp_path / "real.json"
    atomic_write_json(real_file, {"key": "val"})

    symlink_file = tmp_path / "symlink.json"
    try:
        symlink_file.symlink_to(real_file)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    with pytest.raises(SecurityError):
        read_json(symlink_file)

    with pytest.raises(SecurityError):
        atomic_write_json(symlink_file, {"key": "new_val"})


def test_windows_and_darwin_path_resolution(monkeypatch):
    monkeypatch.setenv("SAMSUNG_ACCOUNT_MASTER_STATE", "")
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)

    # Windows simulation
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:\\Users\\SyntheticUser\\AppData\\Roaming")
    resolved_win = resolve_master_state_path()
    assert "samsung-account" in str(resolved_win)
    assert resolved_win.name == "master.json"

    # Darwin simulation
    monkeypatch.setattr(sys, "platform", "darwin")
    resolved_mac = resolve_master_state_path()
    assert "Library" in str(resolved_mac) or "samsung-account" in str(resolved_mac)
    assert resolved_mac.name == "master.json"
