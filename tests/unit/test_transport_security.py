import httpx
import pytest
import respx

from samsung_find.exceptions import AuthError, SecurityError
from samsung_find.transport import (
    SmartThingsTransport,
    validate_smartthings_url,
)


def test_validate_smartthings_url_accepts_valid_https():
    valid = "https://api.smartthings.com/v1/installedapps"
    assert validate_smartthings_url(valid) == valid


@pytest.mark.parametrize(
    "invalid_url",
    [
        "http://api.smartthings.com/v1/devices",  # Insecure HTTP
        "https://attacker.com/v1/devices",  # Untrusted domain
        "https://smartthings.com.attacker.com/v1/devices",  # Subdomain trick
        "https://user:pass@api.smartthings.com/v1/devices",  # Userinfo
        "https://api.smartthings.com:8443/v1/devices",  # Non-standard port
    ],
)
def test_validate_smartthings_url_rejects_insecure_targets(invalid_url):
    with pytest.raises(SecurityError):
        validate_smartthings_url(invalid_url)


def test_hostile_pagination_next_href_rejected():
    transport = SmartThingsTransport(lambda: "test-token")
    with respx.mock:
        respx.get("https://api.smartthings.com/v1/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": "dev1"}],
                    "_links": {"next": {"href": "https://evil-server.com/steal-token"}},
                },
            )
        )
        with pytest.raises(SecurityError, match="(Untrusted target host|Hostile or untrusted pagination URL)"):
            transport.paginate("https://api.smartthings.com/v1/devices")


def test_no_automatic_retry_on_non_idempotent_actions():
    refresh_called = 0

    def get_token():
        nonlocal refresh_called
        refresh_called += 1
        return f"token-{refresh_called}"

    transport = SmartThingsTransport(get_token)

    with respx.mock:
        route = respx.post("https://api.smartthings.com/v1/installedapps/app-1/execute").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )

        with pytest.raises(AuthError):
            transport.execute_action(
                "https://api.smartthings.com/v1/installedapps/app-1/execute",
                payload={"command": "ring"},
                idempotent=False,
            )

        # Non-idempotent action must NOT be retried after 401
        assert route.call_count == 1


def test_automatic_retry_allowed_for_idempotent_reads():
    tokens = iter(["expired-token", "fresh-token"])
    transport = SmartThingsTransport(lambda: next(tokens))

    with respx.mock:
        route = respx.get("https://api.smartthings.com/v1/installedapps").mock(
            side_effect=[
                httpx.Response(401, json={"error": "unauthorized"}),
                httpx.Response(200, json={"items": []}),
            ]
        )

        resp = transport.get("https://api.smartthings.com/v1/installedapps")
        assert resp.status_code == 200
        assert route.call_count == 2


def test_protected_fields_cannot_be_overridden():
    transport = SmartThingsTransport(lambda: "token")
    with pytest.raises(SecurityError, match="Protected field"):
        transport.build_installed_app_payload(
            operation="RING",
            device_id="dev-1",
            user_uuid="user-1",
            override_params={"requester": "attacker", "requesterToken": "fake"},
        )
