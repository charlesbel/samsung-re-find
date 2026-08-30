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
        "https://evil.example/v1/devices",  # Evil domain
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
        respx.get("https://api.smartthings.com/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": "dev1"}],
                    "_links": {"next": {"href": "https://evil-server.com/steal-token"}},
                },
            )
        )
        with pytest.raises(SecurityError, match="(Untrusted target host|Hostile or untrusted pagination URL)"):
            transport.paginate("https://api.smartthings.com/devices")


def test_pagination_detects_cycle_loop():
    transport = SmartThingsTransport(lambda: "test-token")
    with respx.mock:
        respx.get("https://api.smartthings.com/devices").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [{"id": "dev1"}],
                    "_links": {"next": {"href": "https://api.smartthings.com/devices"}},
                },
            )
        )
        with pytest.raises(SecurityError, match="Pagination loop detected"):
            transport.paginate("https://api.smartthings.com/devices")


def test_pagination_enforces_path_allowlist():
    transport = SmartThingsTransport(lambda: "test-token")
    with pytest.raises(SecurityError, match="Unauthorized pagination endpoint path"):
        transport.paginate("https://api.smartthings.com/unauthorized/path")


@pytest.mark.parametrize(
    "invalid_path",
    [
        "/userscripts",
        "/userscripts/run",
        "/devices_extra",
        "/locations_fake",
        "/installedappstore",
    ],
)
def test_pagination_rejects_non_segment_boundary_path_prefixes(invalid_path):
    transport = SmartThingsTransport(lambda: "test-token")
    with pytest.raises(SecurityError, match="Unauthorized pagination endpoint path"):
        transport.paginate(f"https://api.smartthings.com{invalid_path}")


def test_no_automatic_retry_on_narrow_location_operation():
    refresh_called = 0

    def get_token():
        nonlocal refresh_called
        refresh_called += 1
        return f"token-{refresh_called}"

    transport = SmartThingsTransport(get_token)

    with respx.mock:
        route = respx.post("https://api.smartthings.com/installedapps/app-1/execute").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )

        with pytest.raises(AuthError, match="automatic retry disabled for non-idempotent action"):
            transport.request_location(
                installed_app_id="app-1",
                device_id="dev-1",
                user_uuid="user-1",
            )

        # Non-idempotent action must NOT be retried after 401
        assert route.call_count == 1


def test_automatic_retry_allowed_for_idempotent_reads():
    tokens = iter(["expired-token", "fresh-token"])
    transport = SmartThingsTransport(lambda: next(tokens))

    with respx.mock:
        route = respx.get("https://api.smartthings.com/installedapps").mock(
            side_effect=[
                httpx.Response(401, json={"error": "unauthorized"}),
                httpx.Response(200, json={"items": []}),
            ]
        )

        resp = transport.get("https://api.smartthings.com/installedapps")
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


def test_mock_transport_probe_post_307_exfiltration_rejected_with_zero_evil_requests():
    """Adversarial probe: server attempts 307 Temporary Redirect on secret POST to evil host."""
    evil_contacted = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal evil_contacted
        if "evil.example" in str(request.url):
            evil_contacted = True
            return httpx.Response(200, text="exfiltrated")
        if request.method == "POST":
            return httpx.Response(307, headers={"Location": "https://evil.example/steal"})
        return httpx.Response(200, json={})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = SmartThingsTransport(lambda: "secret-bearer-token", http_client=mock_client)

    with pytest.raises(SecurityError, match="Redirect.*forbidden"):
        transport.request_location(
            installed_app_id="app-1",
            device_id="dev-1",
            user_uuid="user-1",
        )

    assert evil_contacted is False, "Secret POST followed redirect to evil host!"


def test_mock_transport_probe_get_redirect_to_evil_host_rejected_with_zero_evil_requests():
    """Adversarial probe: GET request receives 302 redirecting to evil.example."""
    evil_contacted = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal evil_contacted
        if "evil.example" in str(request.url):
            evil_contacted = True
            return httpx.Response(200, text="evil")
        if str(request.url) == "https://api.smartthings.com/installedapps":
            return httpx.Response(302, headers={"Location": "https://evil.example/malicious"})
        return httpx.Response(200, json={})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    transport = SmartThingsTransport(lambda: "secret-bearer-token", http_client=mock_client)

    with pytest.raises(SecurityError, match="Redirect.*forbidden"):
        transport.get("https://api.smartthings.com/installedapps")

    assert evil_contacted is False, "GET followed redirect to untrusted evil host!"


def test_get_redirect_loop_detected():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://api.smartthings.com/installedapps":
            return httpx.Response(302, headers={"Location": "https://api.smartthings.com/installedapps/loop"})
        if str(request.url) == "https://api.smartthings.com/installedapps/loop":
            return httpx.Response(302, headers={"Location": "https://api.smartthings.com/installedapps"})
        return httpx.Response(200, json={})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = SmartThingsTransport(lambda: "token", http_client=mock_client)

    with pytest.raises(SecurityError, match="Redirect.*forbidden"):
        transport.get("https://api.smartthings.com/installedapps")


def test_injected_follow_redirects_client_is_overridden_per_request_for_secret_post():
    contacted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted.append(str(request.url))
        if request.url.host == "evil.example":
            return httpx.Response(200, json={"stolen": True})
        return httpx.Response(307, headers={"Location": "https://evil.example/collect"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    transport = SmartThingsTransport(lambda: "secret-token", http_client=client)
    try:
        with pytest.raises(SecurityError, match="Redirect.*forbidden"):
            transport.request_location(installed_app_id="app-1", device_id="dev-1", user_uuid="user-1")
    finally:
        transport.close()

    assert contacted == ["https://api.smartthings.com/installedapps/app-1/execute"]


def test_injected_client_response_history_is_rejected_even_with_trusted_final_url():
    request = httpx.Request("GET", "https://api.smartthings.com/devices?limit=1")
    prior = httpx.Response(
        302,
        headers={"Location": "https://api.smartthings.com/devices?limit=1"},
        request=httpx.Request("GET", "https://evil.example/collect"),
    )
    response = httpx.Response(200, json={"items": []}, request=request, history=[prior])

    class HistoryClient(httpx.Client):
        def send(self, request, **_kwargs):
            del request
            return response

    transport = SmartThingsTransport(lambda: "secret-token", http_client=HistoryClient())
    try:
        with pytest.raises(SecurityError, match="history"):
            transport.get("https://api.smartthings.com/devices", params={"limit": 1})
    finally:
        transport.close()


@pytest.mark.parametrize(
    "final_url",
    [
        "http://api.smartthings.com/devices?limit=1",
        "https://evil.example/devices?limit=1",
        "https://api.smartthings.com:444/devices?limit=1",
        "https://api.smartthings.com/locations?limit=1",
        "https://api.smartthings.com/devices?limit=2",
    ],
)
def test_injected_client_forged_final_destination_is_rejected(final_url):
    class ForgedFinalClient(httpx.Client):
        def send(self, request, **_kwargs):
            del request
            return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", final_url))

    transport = SmartThingsTransport(lambda: "secret-token", http_client=ForgedFinalClient())
    try:
        with pytest.raises(SecurityError, match="destination"):
            transport.get("https://api.smartthings.com/devices", params={"limit": 1})
    finally:
        transport.close()


@pytest.mark.parametrize(
    "malicious_path",
    [
        "/installedapps/%2e%2e/admin",
        "/installedapps/%2E%2E/admin",
        "/installedapps/%252e%252e/admin",
        "/installedapps/%252fadmin",
        "/installedapps%2fadmin",
        "/installedapps%2Fadmin",
        "/installedapps\\admin",
        "/installedapps/%5c../admin",
        "/installedapps/%5C../admin",
        "/installedapps/../admin",
        "/installedapps/../../sensitive",
        "/installedapps/%00/admin",
        "/devices/%c0%ae%c0%ae/admin",
        "/devices/%e0%80%ae%e0%80%ae/admin",
        "/devices/%f0%80%80%ae%f0%80%80%ae/admin",
        "/devices/%",
        "/devices/%G0/admin",
    ],
)
def test_pagination_rejects_adversarial_paths_with_zero_unauthorized_requests(malicious_path):
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"items": []})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = SmartThingsTransport(lambda: "secret-token", http_client=mock_client)

    with pytest.raises(SecurityError):
        transport.paginate(f"https://api.smartthings.com{malicious_path}")

    # No authenticated request may be dispatched to the unauthorized/malicious endpoint
    assert len(requested_urls) == 0


@pytest.mark.parametrize(
    "malicious_next_href",
    [
        "/installedapps/%2e%2e/admin",
        "/installedapps/%252e%252e/admin",
        "/installedapps%2fadmin",
        "/installedapps\\admin",
        "/installedapps/%5c../admin",
        "/installedapps/../admin",
        "/unauthorized/endpoint",
    ],
)
def test_pagination_rejects_adversarial_next_links_without_unauthorized_request(malicious_next_href):
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == "https://api.smartthings.com/devices":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "dev-1"}],
                    "_links": {"next": {"href": malicious_next_href}},
                },
            )
        return httpx.Response(200, json={"items": []})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = SmartThingsTransport(lambda: "secret-token", http_client=mock_client)

    with pytest.raises(SecurityError):
        transport.paginate("https://api.smartthings.com/devices")

    # Initial legitimate page was fetched, but ZERO unauthorized next requests were sent
    assert requested_urls == ["https://api.smartthings.com/devices"]
