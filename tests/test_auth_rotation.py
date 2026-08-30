import httpx
import pytest
import respx

from samsung_find.auth import FIND, SamsungAuth, SamsungAuthError
from samsung_find.constants import REDIRECT_URI
from samsung_find.exceptions import SecurityError
from samsung_find.storage import atomic_write_json, read_json


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class HTTP:
    def __init__(self, response):
        self.response = response

    def post(self, *_args, **_kwargs):
        return self.response


def write_master(path, *, generation="gen-current", token="master-current"):
    atomic_write_json(
        path,
        {
            "schema": "io.github.charlesbel.samsung-account.master",
            "schema_version": 1,
            "generation": generation,
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "account": {"login_id": "test@example.invalid", "user_id": "user-current"},
            "installation": {"physical_address": "device-current"},
            "identity": {
                "auth_server_url": "https://eu-auth2.samsungosp.com",
                "userauth_token": token,
            },
        },
    )


@pytest.mark.parametrize("derived_generation", [None, "gen-previous"])
def test_access_token_reissues_before_reusing_derived_token_from_unknown_master_generation(
    tmp_path, monkeypatch, derived_generation
):
    state_path = tmp_path / "state.json"
    master_path = tmp_path / "master.json"
    state = {
        "schema": 1,
        "created_at": 1000,
        "updated_at": 1000,
        "find": {"access_token": "stale-account-token", "expires_at": 4_000_000_000},
    }
    if derived_generation is not None:
        state["master_generation"] = derived_generation
    atomic_write_json(state_path, state)
    write_master(master_path)

    auth = SamsungAuth(state_path, tmp_path / "pending.json", master_path=master_path)
    issued_from: list[str] = []

    def reissue(token, kind, **master):
        assert token == {}, "a stale account token must not be refreshed across the generation boundary"
        issued_from.append(master["userauth_token"])
        return {"access_token": "fresh-current-token", "expires_at": 4_000_000_000}

    monkeypatch.setattr(auth, "_refresh_or_reissue", reissue)
    try:
        assert auth.access_token(FIND) == "fresh-current-token"
    finally:
        auth.close()

    assert issued_from == ["master-current"]
    persisted = read_json(state_path)
    assert persisted["master_generation"] == "gen-current"
    assert persisted["find"]["access_token"] == "fresh-current-token"


def test_access_token_clears_derived_credentials_when_current_master_is_missing(tmp_path):
    state_path = tmp_path / "state.json"
    atomic_write_json(
        state_path,
        {
            "schema": 1,
            "master_generation": "gen-orphaned",
            "created_at": 1000,
            "updated_at": 1000,
            "find": {"access_token": "orphaned-token", "expires_at": 4_000_000_000},
            "iot": {"access_token": "orphaned-iot-token", "expires_at": 4_000_000_000},
        },
    )
    auth = SamsungAuth(state_path, tmp_path / "pending.json", master_path=tmp_path / "missing-master.json")
    try:
        with pytest.raises(SamsungAuthError, match="no master token"):
            auth.access_token(FIND)
    finally:
        auth.close()

    persisted = read_json(state_path)
    assert "find" not in persisted
    assert "iot" not in persisted
    assert "master_generation" not in persisted


def test_web_session_does_not_reuse_cookie_from_mismatched_master_generation(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    master_path = tmp_path / "master.json"
    atomic_write_json(
        state_path,
        {
            "schema": 1,
            "master_generation": "gen-previous",
            "created_at": 1000,
            "updated_at": 1000,
            "web": {"jsessionid": "stale-account-cookie", "updated_at": 1000},
        },
    )
    write_master(master_path)
    auth = SamsungAuth(state_path, tmp_path / "pending.json", master_path=master_path)
    monkeypatch.setattr(auth, "_validate_web_cookie", lambda _cookie: True)
    monkeypatch.setattr(
        auth,
        "_authenticated_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("web session reissue started")),
    )
    try:
        with pytest.raises(RuntimeError, match="reissue started"):
            auth.web_session_cookie()
    finally:
        auth.close()

    persisted = read_json(state_path)
    assert persisted["master_generation"] == "gen-current"
    assert "web" not in persisted


def test_web_session_uses_server_state_and_bootstrap_cookie(tmp_path):
    state_path = tmp_path / "state.json"
    pending_path = tmp_path / "pending.json"
    master_path = tmp_path / "master.json"
    atomic_write_json(
        state_path,
        {
            "schema": 1,
            "master_generation": "gen-current",
            "created_at": 1000,
            "updated_at": 1000,
        },
    )
    write_master(master_path)

    with respx.mock(assert_all_called=True) as routes:
        bootstrap = routes.get("https://smartthingsfind.samsung.com/getState.do").mock(
            return_value=httpx.Response(
                200,
                json={"state": "server-state"},
                headers={"set-cookie": "JSESSIONID=bootstrap; Path=/; Secure; HttpOnly"},
            )
        )
        routes.get("https://eu-auth2.samsungosp.com/auth/oauth2/v2/authorize").mock(
            return_value=httpx.Response(200, json={"code": "web-code", "code_expires_in": 300})
        )

        def login(request):
            assert request.url.params["state"] == "server-state"
            assert "JSESSIONID=bootstrap" in request.headers.get("cookie", "")
            return httpx.Response(
                200,
                headers={"set-cookie": "JSESSIONID=valid-session; Path=/; Secure; HttpOnly"},
            )

        routes.get("https://smartthingsfind.samsung.com/login.do").mock(side_effect=login)
        routes.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(
            return_value=httpx.Response(200, text="success", headers={"_csrf": "csrf"})
        )

        auth = SamsungAuth(str(state_path), str(pending_path), master_path=str(master_path))
        try:
            assert auth.web_session_cookie() == "valid-session"
        finally:
            auth.close()

    assert bootstrap.called
    assert read_json(state_path)["web"]["jsessionid"] == "valid-session"


def test_validate_web_cookie_rejects_invalid_responses():
    # 1. HTTP 401 Unauthorized
    with respx.mock:
        respx.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(
            return_value=httpx.Response(401, text="unauthorized")
        )
        assert SamsungAuth._validate_web_cookie("invalid-cookie") is False

    # 2. HTTP 200 without _csrf header
    with respx.mock:
        respx.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(return_value=httpx.Response(200, text="ok"))
        assert SamsungAuth._validate_web_cookie("no-csrf-cookie") is False

    # 3. HTTP 302 Redirect
    with respx.mock:
        respx.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(
            return_value=httpx.Response(302, headers={"Location": "/login.do"})
        )
        assert SamsungAuth._validate_web_cookie("redirect-cookie") is False

    # 4. Empty or invalid cookie value
    assert SamsungAuth._validate_web_cookie("") is False
    assert SamsungAuth._validate_web_cookie(None) is False  # type: ignore[arg-type]

    # 5. Network / connection exception
    with respx.mock:
        respx.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(
            side_effect=httpx.ConnectError("Network down")
        )
        assert SamsungAuth._validate_web_cookie("error-cookie") is False


def test_web_session_refreshes_when_stored_cookie_is_invalid(tmp_path):
    state_path = tmp_path / "state.json"
    pending_path = tmp_path / "pending.json"
    master_path = tmp_path / "master.json"
    atomic_write_json(
        state_path,
        {
            "schema": 1,
            "master_generation": "gen-1",
            "created_at": 1000,
            "updated_at": 1000,
            "web": {"jsessionid": "expired-cookie", "obtained_at": 1000},
        },
    )
    atomic_write_json(
        master_path,
        {
            "schema": "io.github.charlesbel.samsung-account.master",
            "schema_version": 1,
            "generation": "gen-1",
            "created_at": 1000.0,
            "updated_at": 1000.0,
            "account": {"login_id": "test@example.invalid"},
            "installation": {"physical_address": "device-uuid"},
            "identity": {"auth_server_url": "https://eu-auth2.samsungosp.com", "userauth_token": "master-token"},
        },
    )

    with respx.mock(assert_all_called=True) as routes:
        # First chkLogin.do for expired-cookie returns 401
        routes.get("https://smartthingsfind.samsung.com/chkLogin.do").mock(
            side_effect=[
                httpx.Response(401, text="unauthorized"),
                httpx.Response(200, text="success", headers={"_csrf": "csrf-new"}),
            ]
        )
        routes.get("https://smartthingsfind.samsung.com/getState.do").mock(
            return_value=httpx.Response(
                200,
                json={"state": "new-server-state"},
                headers={"set-cookie": "JSESSIONID=bootstrap-new; Path=/; Secure; HttpOnly"},
            )
        )
        routes.get("https://eu-auth2.samsungosp.com/auth/oauth2/v2/authorize").mock(
            return_value=httpx.Response(200, json={"code": "web-code-new", "code_expires_in": 300})
        )
        routes.get("https://smartthingsfind.samsung.com/login.do").mock(
            return_value=httpx.Response(
                200,
                headers={"set-cookie": "JSESSIONID=fresh-valid-session; Path=/; Secure; HttpOnly"},
            )
        )

        auth = SamsungAuth(str(state_path), str(pending_path), master_path=str(master_path))
        try:
            assert auth.web_session_cookie() == "fresh-valid-session"
        finally:
            auth.close()

    assert read_json(state_path)["web"]["jsessionid"] == "fresh-valid-session"


def test_dead_refresh_token_falls_back_to_master_reissue(monkeypatch):
    auth = SamsungAuth.__new__(SamsungAuth)
    auth.http = HTTP(Response(400))
    expected = {"access_token": "new", "refresh_token": "rotated"}
    monkeypatch.setattr(auth, "_issue_token", lambda state, kind: expected)
    state = {
        "auth_server_url": "https://auth.example",
        "userauth_token": "master",
        "find": {"refresh_token": "dead"},
    }
    assert auth._refresh_or_reissue(state, FIND) == expected


def test_refresh_rotation_replaces_both_tokens():
    auth = SamsungAuth.__new__(SamsungAuth)
    auth.http = HTTP(Response(200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 3600}))
    state = {"auth_server_url": "https://auth.example", "find": {"refresh_token": "refresh-1"}}
    result = auth._refresh_or_reissue(state, FIND)
    assert result["access_token"] == "access-2"
    assert result["refresh_token"] == "refresh-2"
    assert result["expires_at"] > result["obtained_at"]


def test_refresh_token_post_rejects_307_without_contacting_redirect_host():
    """Adversarial fixture: verify token endpoint 307 redirect fails closed with zero exfiltration.

    Even when the underlying transport client has follow_redirects=True configured,
    secret-bearing token refresh/exchange requests must reject HTTP redirects immediately
    via _secret_post without dispatching any follow-up request to the adversarial host.
    """
    contacted_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        contacted_hosts.append(request.url.host)
        if request.url.host == "evil.example":
            return httpx.Response(200, json={"access_token": "stolen", "refresh_token": "stolen"})
        return httpx.Response(307, headers={"Location": "https://evil.example/collect"})

    auth = SamsungAuth.__new__(SamsungAuth)
    auth.http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    try:
        with pytest.raises(SecurityError, match="redirect"):
            auth._refresh_or_reissue(
                {"refresh_token": "synthetic-refresh"},
                FIND,
                userauth_token="synthetic-master",
                auth_server_url="https://auth.samsungosp.com",
                device_id="synthetic-device",
                login_id="synthetic-login",
            )
    finally:
        auth.http.close()

    # Assert exactly zero requests reached the adversarial exfiltration target
    assert contacted_hosts == ["auth.samsungosp.com"]


def test_auth_server_url_must_be_https_on_a_samsung_domain():
    assert SamsungAuth._trusted_auth_server_url("https://eu-auth2.samsungosp.com") == (
        "https://eu-auth2.samsungosp.com"
    )
    assert SamsungAuth._trusted_auth_server_url("https://account.samsung.com") == "https://account.samsung.com"

    for value in (
        "http://eu-auth2.samsungosp.com",
        "https://samsungosp.com.evil.example",
        "https://example.com",
    ):
        with pytest.raises(SamsungAuthError, match="untrusted authentication server"):
            SamsungAuth._trusted_auth_server_url(value)


def test_pending_authentication_expires_after_fifteen_minutes(tmp_path, monkeypatch):
    pending_path = tmp_path / "pending.json"
    atomic_write_json(
        pending_path,
        {"state": "synthetic", "code_verifier": "synthetic", "device_id": "synthetic", "created_at": 1_000},
    )
    auth = SamsungAuth.__new__(SamsungAuth)
    auth.pending_path = str(pending_path)
    monkeypatch.setattr("samsung_find.auth.time.time", lambda: 1_901)

    with pytest.raises(SamsungAuthError, match="expired"):
        auth.complete("ms-app://callback")


@pytest.mark.parametrize(
    "hostile_callback",
    [
        "ms-app://callback?state=synthetic",
        f"{REDIRECT_URI}.evil?state=synthetic",
        f"{REDIRECT_URI}/other?state=synthetic",
        f"MS-APP://{REDIRECT_URI.removeprefix('ms-app://')}?state=synthetic",
    ],
)
def test_complete_rejects_callback_outside_exact_configured_redirect_target(tmp_path, monkeypatch, hostile_callback):
    pending_path = tmp_path / "pending.json"
    monkeypatch.setattr("samsung_find.auth.time.time", lambda: 1_001)
    atomic_write_json(
        pending_path,
        {
            "state": "synthetic-state",
            "code_verifier": "synthetic-verifier",
            "device_id": "synthetic-device",
            "created_at": 1_000,
        },
    )
    auth = SamsungAuth.__new__(SamsungAuth)
    auth.pending_path = pending_path

    with pytest.raises(SamsungAuthError, match="configured callback"):
        auth.complete(hostile_callback)
