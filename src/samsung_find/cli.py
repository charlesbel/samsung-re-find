from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

import httpx

from .api import SamsungFindClient
from .auth import SamsungAuth, SamsungAuthError
from .constants import DEFAULT_PENDING_PATH, DEFAULT_REDIRECT_PATH, DEFAULT_STATE_PATH
from .credentials import MasterStateStore
from .storage import secure_read_text


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="samsung-find")
    root.add_argument("--master-state", default=None, help="Path to shared Samsung master state v1")
    root.add_argument("--state", default=DEFAULT_STATE_PATH)
    root.add_argument("--pending", default=DEFAULT_PENDING_PATH)
    root.add_argument("--redirect-file", default=DEFAULT_REDIRECT_PATH)
    root.add_argument("--country", default=os.environ.get("SAMSUNG_FIND_COUNTRY", "US"))
    root.add_argument("--language", default=os.environ.get("SAMSUNG_FIND_LANGUAGE", "en"))
    root.add_argument("--timezone", default=os.environ.get("SAMSUNG_FIND_TIMEZONE", "UTC"))
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("install-handler", help="Register a private ms-app:// redirect catcher")
    start = commands.add_parser("auth-start", help="Generate the Samsung Account login URL")
    start.add_argument("--country", default="us")
    start.add_argument("--locale", default="en-US")
    commands.add_parser("auth-complete", help="Consume the securely captured redirect URI")
    migrate = commands.add_parser("migrate-master", help="Migrate legacy state to neutral master state v1")
    migrate.add_argument("--from-state", default=None, help="Legacy state path")
    migrate.add_argument("--force", action="store_true", help="Force overwrite existing master state")
    commands.add_parser("status")
    commands.add_parser("verify")
    devices = commands.add_parser("devices")
    devices.add_argument("--include-ids", action="store_true", help="Include internal device identifiers")
    capabilities = commands.add_parser("capabilities", help="Show safe features exposed for one device")
    capabilities.add_argument("query")
    check = commands.add_parser("check", help="Check reachability and battery status")
    check.add_argument("query")
    check.add_argument("--poll-seconds", type=int, default=40)
    ring = commands.add_parser("ring", help="Start or stop ringing a device")
    ring.add_argument("query")
    ring.add_argument("--status", choices=("start", "stop"), default="start")
    ring.add_argument("--message")
    ring.add_argument("--poll-seconds", type=int, default=40)
    ring.add_argument("--yes", action="store_true", required=True, help="Confirm the audible side effect")
    track = commands.add_parser("track", help="Start or stop continuous location tracking")
    track.add_argument("query")
    track.add_argument("action", choices=("start", "stop"))
    track.add_argument("--poll-seconds", type=int, default=30)
    track.add_argument("--yes", action="store_true", required=True, help="Confirm the tracking state change")
    locate = commands.add_parser("locate")
    locate.add_argument("query", help="Unique name, model substring or device id")
    locate.add_argument("--passive", action="store_true", help="Do not request a fresh device fix")
    locate.add_argument("--poll-seconds", type=int, default=180)
    return root


def install_handler(redirect_path: str) -> dict[str, object]:
    applications = Path("~/.local/share/applications").expanduser()
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / "samsung-find-callback.desktop"
    env_path = str(Path(redirect_path).expanduser().resolve())
    exec_line = (
        f"env SAMSUNG_FIND_REDIRECT_PATH={env_path} "
        f"{sys.executable} -m samsung_find.capture_redirect %u"
    )
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Samsung Find private callback\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "MimeType=x-scheme-handler/ms-app;\n",
        encoding="utf-8",
    )
    os.chmod(desktop, 0o700)
    xdg_mime = shutil.which("xdg-mime")
    if not xdg_mime:
        raise RuntimeError("xdg-mime is required to install the callback handler")
    # The executable is resolved to an absolute path and no shell is involved.
    subprocess.run(  # nosec B603
        [xdg_mime, "default", desktop.name, "x-scheme-handler/ms-app"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"installed": True, "handler": str(desktop), "redirect_file": env_path}


def main() -> int:
    args = parser().parse_args()
    auth = SamsungAuth(args.state, args.pending, master_path=args.master_state)
    client: SamsungFindClient | None = None
    try:
        if args.command == "install-handler":
            emit(install_handler(args.redirect_file))
        elif args.command == "auth-start":
            emit({"login_url": auth.start(args.country, args.locale)})
        elif args.command == "auth-complete":
            redirect = secure_read_text(args.redirect_file)
            emit(auth.complete(redirect))
        elif args.command == "migrate-master":
            store = MasterStateStore(
                master_path=args.master_state,
                legacy_path=args.from_state or args.state,
            )
            emit(store.migrate_legacy(force=args.force))
        elif args.command == "status":
            emit(auth.public_status())
        else:
            client = SamsungFindClient(
                auth,
                country=args.country,
                language=args.language,
                timezone=args.timezone,
            )
            if args.command == "verify":
                cookie = auth.web_session_cookie()
                emit({
                    "persistent_master_token_present": auth.public_status()["authenticated"],
                    "web_session_valid": auth._validate_web_cookie(cookie),
                })
            elif args.command == "devices":
                keys = (
                    ("id", "name", "model", "location_type")
                    if args.include_ids
                    else ("name", "model", "location_type")
                )
                emit([{key: d.get(key) for key in keys} for d in client.devices()])
            elif args.command == "capabilities":
                emit(client.capabilities(args.query))
            elif args.command == "check":
                emit(client.check_connection(args.query, poll_seconds=args.poll_seconds))
            elif args.command == "ring":
                emit(client.ring(
                    args.query, status=args.status, message=args.message, poll_seconds=args.poll_seconds
                ))
            elif args.command == "track":
                emit(client.track(
                    args.query, enabled=args.action == "start", poll_seconds=args.poll_seconds
                ))
            elif args.command == "locate":
                emit(client.locate(args.query, active=not args.passive, poll_seconds=args.poll_seconds))
        return 0
    except (SamsungAuthError, FileNotFoundError, ValueError, httpx.HTTPError) as exc:  # type: ignore[name-defined]
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()
        auth.close()


if __name__ == "__main__":
    raise SystemExit(main())
