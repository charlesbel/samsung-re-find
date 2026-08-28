import httpx
import pytest
import respx

from samsung_find.auth import FIND, SamsungAuth, SamsungAuthError
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


def test_web_session_uses_server_state_and_bootstrap_cookie(tmp_path):
    state_path = tmp_path / "state.json"
    pending_path = tmp_path / "pending.json"
    atomic_write_json(state_path, {
        "auth_server_url": "https://eu-auth2.samsungosp.com",
        "userauth_token": "master",
        "device_id": "device",
        "login_id": "login",
    })

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

        auth = SamsungAuth(str(state_path), str(pending_path))
        try:
            assert auth.web_session_cookie() == "valid-session"
        finally:
            auth.close()

    assert bootstrap.called
    assert read_json(state_path)["web"]["jsessionid"] == "valid-session"


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
    auth.http = HTTP(Response(200, {
        "access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 3600
    }))
    state = {"auth_server_url": "https://auth.example", "find": {"refresh_token": "refresh-1"}}
    result = auth._refresh_or_reissue(state, FIND)
    assert result["access_token"] == "access-2"
    assert result["refresh_token"] == "refresh-2"
    assert result["expires_at"] > result["obtained_at"]


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
