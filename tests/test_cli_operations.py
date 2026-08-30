import json

import pytest

from samsung_find.cli import main, parser


def test_locate_uses_extended_polling_by_default():
    args = parser().parse_args(["locate", "Primary Galaxy Phone"])
    assert args.poll_seconds == 180


def test_ring_requires_explicit_confirmation():
    with pytest.raises(SystemExit):
        parser().parse_args(["ring", "Primary Galaxy Phone"])
    args = parser().parse_args(["ring", "Primary Galaxy Phone", "--yes", "--status", "stop"])
    assert args.yes is True
    assert args.status == "stop"


def test_tracking_requires_explicit_confirmation():
    with pytest.raises(SystemExit):
        parser().parse_args(["track", "Primary Galaxy Phone", "start"])
    args = parser().parse_args(["track", "Primary Galaxy Phone", "start", "--yes"])
    assert args.action == "start"
    assert args.yes is True


def test_capabilities_and_check_commands_parse():
    capabilities = parser().parse_args(["capabilities", "Primary Galaxy Phone"])
    check = parser().parse_args(["check", "Primary Galaxy Phone", "--poll-seconds", "60"])
    assert capabilities.query == "Primary Galaxy Phone"
    assert check.poll_seconds == 60


def test_public_defaults_are_global_and_device_ids_are_opt_in():
    args = parser().parse_args(["devices"])
    assert args.country == "US"
    assert args.language == "en"
    assert args.timezone == "UTC"
    assert args.include_ids is False

    with_ids = parser().parse_args(["devices", "--include-ids"])
    assert with_ids.include_ids is True


def test_cli_usage_error_produces_json_envelope_on_stdout(capsys):
    ret = main(["--unknown-option"])
    assert ret == 2
    captured = capsys.readouterr()
    assert captured.err == ""  # No usage prose on stderr
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["schema_version"] == "1.0"
    assert payload["error"]["code"] == "invalid_arguments"


def test_cli_missing_required_args_produces_json_envelope(capsys):
    ret = main(["ring", "Primary Galaxy Phone"])
    assert ret == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_arguments"


def test_cli_unknown_command_produces_json_envelope(capsys):
    ret = main(["non-existent-subcommand"])
    assert ret == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_arguments"
