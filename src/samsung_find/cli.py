from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

from .api import SamsungFindClient as _LegacyTransportClient
from .auth import SamsungAuth
from .credentials import (
    MasterStateStore,
    resolve_redirect_path,
)
from .exceptions import (
    AuthError,
    DeviceNotFoundError,
    NetworkError,
    OperationError,
    RateLimitError,
    SecurityError,
    StorageError,
)
from .serialization import serialize_error, serialize_response, to_json
from .service import FindService
from .storage import secure_read_text


class SamsungFindArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser that emits structured JSON envelopes on error in machine mode."""

    def error(self, message: str) -> None:
        payload = serialize_error(code="invalid_arguments", message=message)
        print(to_json(payload))
        sys.exit(2)


def emit(value: object, *, legacy_json: bool = False) -> None:
    if legacy_json:
        print(to_json(value))
    else:
        print(to_json(serialize_response(value)))


def parser() -> argparse.ArgumentParser:
    root = SamsungFindArgumentParser(
        prog="samsung-re-find",
        description="Unofficial reverse-engineered Samsung Find SDK, JSON CLI & MCP server",
    )
    root.add_argument("--legacy-json", action="store_true", help="Output raw legacy JSON without v1 envelope")
    root.add_argument("--master-state", default=None, help="Path to shared Samsung master state v1")
    root.add_argument("--state", default=None, help="Path to canonical Samsung Find derived state")
    root.add_argument("--legacy-state", default=None, help="Path to legacy Samsung Find state")
    root.add_argument("--pending", default=None, help="Path to pending authentication file")
    root.add_argument("--redirect-file", default=None, help="Path to OAuth redirect URI file")
    root.add_argument("--country", default=os.environ.get("SAMSUNG_FIND_COUNTRY", "US"))
    root.add_argument("--language", default=os.environ.get("SAMSUNG_FIND_LANGUAGE", "en"))
    root.add_argument("--timezone", default=os.environ.get("SAMSUNG_FIND_TIMEZONE", "UTC"))
    commands = root.add_subparsers(dest="command", required=True, parser_class=SamsungFindArgumentParser)
    commands.add_parser("install-handler", help="Register a private ms-app:// redirect catcher")
    start = commands.add_parser("auth-start", help="Generate the Samsung Account login URL")
    start.add_argument("--country", default="us")
    start.add_argument("--locale", default="en-US")
    commands.add_parser("auth-complete", help="Consume the securely captured redirect URI")
    commands.add_parser("account-status", help="Check the shared Samsung Account master state")
    migrate = commands.add_parser("migrate-master", help="Migrate legacy state to neutral master state v1")
    migrate.add_argument("--from-state", default=None, help="Legacy state path (defaults to legacy standard path)")
    migrate.add_argument("--force", action="store_true", help="Force overwrite existing master state")
    commands.add_parser("status", help="Check local authentication status")
    commands.add_parser("verify", help="Verify connection and SmartThings Find session")
    devices = commands.add_parser("devices", help="List registered Samsung Find devices")
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
    locate = commands.add_parser("locate", help="Get device location")
    locate.add_argument("query", help="Unique name, model substring or device id")
    locate.add_argument("--passive", action="store_true", help="Do not request a fresh device fix")
    locate.add_argument("--poll-seconds", type=int, default=180)
    return root


def install_handler(
    redirect_path: str | Path | None = None,
    master_path: str | Path | None = None,
) -> dict[str, object]:
    target_redirect = resolve_redirect_path(redirect_path, master_path)
    applications = Path("~/.local/share/applications").expanduser()
    applications.mkdir(parents=True, exist_ok=True)
    desktop = applications / "samsung-account-callback.desktop"
    import shlex

    env_path = str(target_redirect)
    exec_line = (
        f"env SAMSUNG_ACCOUNT_REDIRECT_PATH={shlex.quote(env_path)} "
        f"{shlex.quote(sys.executable)} -m samsung_find.capture_redirect %u"
    )
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Samsung Account private callback\n"
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


def main(
    argv: list[str] | None = None,
    *,
    service: FindService | None = None,
    auth: SamsungAuth | None = None,
) -> int:
    try:
        args = parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    auth_instance = auth
    if auth_instance is None and service is None:
        auth_instance = SamsungAuth(
            state_path=args.state,
            pending_path=args.pending,
            master_path=args.master_state,
            legacy_state_path=args.legacy_state,
        )

    svc = service
    legacy = getattr(args, "legacy_json", False)

    try:
        if args.command == "install-handler":
            emit(install_handler(args.redirect_file, args.master_state), legacy_json=legacy)
        elif args.command == "auth-start":
            if auth_instance is None:
                auth_instance = SamsungAuth(
                    state_path=args.state,
                    pending_path=args.pending,
                    master_path=args.master_state,
                    legacy_state_path=args.legacy_state,
                )
            emit({"login_url": auth_instance.start(args.country, args.locale)}, legacy_json=legacy)
        elif args.command == "auth-complete":
            if auth_instance is None:
                auth_instance = SamsungAuth(
                    state_path=args.state,
                    pending_path=args.pending,
                    master_path=args.master_state,
                    legacy_state_path=args.legacy_state,
                )
            redirect_target = resolve_redirect_path(args.redirect_file, args.master_state)
            redirect = secure_read_text(redirect_target)
            emit(auth_instance.complete(redirect), legacy_json=legacy)
        elif args.command == "migrate-master":
            store = MasterStateStore(
                master_path=args.master_state,
                canonical_state_path=args.state,
                legacy_path=args.from_state or args.legacy_state,
            )
            emit(store.migrate_legacy(force=args.force), legacy_json=legacy)
        elif args.command in {"account-status", "status"}:
            if auth_instance is None:
                auth_instance = SamsungAuth(
                    state_path=args.state,
                    pending_path=args.pending,
                    master_path=args.master_state,
                    legacy_state_path=args.legacy_state,
                )
            if args.command == "account-status":
                status = auth_instance.account_status()
            else:
                status = auth_instance.public_status()
            emit(status, legacy_json=legacy)
        else:
            if svc is None:
                if auth_instance is None:
                    auth_instance = SamsungAuth(
                        state_path=args.state,
                        pending_path=args.pending,
                        master_path=args.master_state,
                        legacy_state_path=args.legacy_state,
                    )
                transport = _LegacyTransportClient(
                    auth_instance,
                    country=args.country,
                    language=args.language,
                    timezone=args.timezone,
                )
                svc = FindService(transport)

            if args.command == "verify":
                if auth_instance is None:
                    auth_instance = SamsungAuth(
                        state_path=args.state,
                        pending_path=args.pending,
                        master_path=args.master_state,
                        legacy_state_path=args.legacy_state,
                    )
                cookie = auth_instance.web_session_cookie()
                emit(
                    {
                        "persistent_master_token_present": auth_instance.public_status()["authenticated"],
                        "web_session_valid": auth_instance._validate_web_cookie(cookie),
                    },
                    legacy_json=legacy,
                )
            elif args.command == "devices":
                devices = svc.list_devices(include_ids=args.include_ids)
                emit([d.to_dict(include_id=args.include_ids) for d in devices], legacy_json=legacy)
            elif args.command == "capabilities":
                emit(svc.get_capabilities(args.query), legacy_json=legacy)
            elif args.command == "check":
                emit(svc.check_connection(args.query, poll_seconds=args.poll_seconds), legacy_json=legacy)
            elif args.command == "ring":
                emit(
                    svc.ring(
                        args.query,
                        status=args.status,
                        message=args.message,
                        poll_seconds=args.poll_seconds,
                    ),
                    legacy_json=legacy,
                )
            elif args.command == "track":
                emit(
                    svc.set_tracking(args.query, enabled=args.action == "start", poll_seconds=args.poll_seconds),
                    legacy_json=legacy,
                )
            elif args.command == "locate":
                if args.passive:
                    res = svc.get_last_location(args.query)
                else:
                    res = svc.request_location(args.query, poll_seconds=args.poll_seconds)
                emit(res, legacy_json=legacy)
        return 0

    except AuthError as exc:
        err = serialize_error(code=exc.code, message=str(exc))
        if not legacy:
            print(to_json(err))
        print(f"Authentication error: {exc}", file=sys.stderr)
        return 3
    except (NetworkError, Exception) as exc:
        if isinstance(exc, (SecurityError, StorageError, PermissionError, FileNotFoundError)):
            code = getattr(exc, "code", "storage_error")
            err = serialize_error(code=code, message=str(exc))
            if not legacy:
                print(to_json(err))
            print(f"Storage or security error: {exc}", file=sys.stderr)
            return 5
        elif isinstance(exc, (DeviceNotFoundError, OperationError, RateLimitError)):
            code = getattr(exc, "code", "operation_error")
            err = serialize_error(code=code, message=str(exc))
            if not legacy:
                print(to_json(err))
            print(f"Operation error: {exc}", file=sys.stderr)
            return 1
        elif isinstance(exc, NetworkError) or "httpx" in exc.__class__.__module__:
            code = getattr(exc, "code", "network_error")
            err = serialize_error(code=code, message=str(exc))
            if not legacy:
                print(to_json(err))
            print(f"Network error: {exc}", file=sys.stderr)
            return 4
        else:
            err = serialize_error(code="unknown_error", message=str(exc))
            if not legacy:
                print(to_json(err))
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1
    finally:
        if svc is not None and service is None:
            svc.close()
        if auth_instance is not None and auth is None:
            auth_instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
