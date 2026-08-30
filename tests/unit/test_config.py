from samsung_find.config import FindConfig


def test_default_config(monkeypatch):
    monkeypatch.delenv("SAMSUNG_FIND_COUNTRY", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_LANGUAGE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_TIMEZONE", raising=False)
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_STATE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_LEGACY_STATE", raising=False)

    config = FindConfig()
    assert config.country == "US"
    assert config.language == "en"
    assert config.timezone == "UTC"
    assert config.timeout_s == 30.0
    assert config.state_path is not None
    assert config.legacy_state_path is not None
    assert config.master_state_path is not None


def test_config_env_overrides(monkeypatch, tmp_path):
    master_path = tmp_path / "master.json"
    state_path = tmp_path / "derived_state.json"
    legacy_path = tmp_path / "legacy_state.json"

    monkeypatch.setenv("SAMSUNG_FIND_COUNTRY", "FR")
    monkeypatch.setenv("SAMSUNG_FIND_LANGUAGE", "fr")
    monkeypatch.setenv("SAMSUNG_FIND_TIMEZONE", "Europe/Paris")
    monkeypatch.setenv("SAMSUNG_ACCOUNT_MASTER_STATE", str(master_path))
    monkeypatch.setenv("SAMSUNG_FIND_STATE", str(state_path))
    monkeypatch.setenv("SAMSUNG_FIND_LEGACY_STATE", str(legacy_path))

    config = FindConfig()
    assert config.country == "FR"
    assert config.language == "fr"
    assert config.timezone == "Europe/Paris"
    assert config.master_state_path == master_path.resolve()
    assert config.state_path == state_path.resolve()
    assert config.legacy_state_path == legacy_path.resolve()


def test_config_explicit_overrides(tmp_path):
    master_path = tmp_path / "custom_master.json"
    state_path = tmp_path / "custom_state.json"
    legacy_path = tmp_path / "custom_legacy.json"

    config = FindConfig(
        country="gb",
        language="en-GB",
        timezone="Europe/London",
        timeout_s=15.0,
        master_state_path=master_path,
        state_path=state_path,
        legacy_state_path=legacy_path,
    )
    assert config.country == "GB"
    assert config.language == "en-GB"
    assert config.timezone == "Europe/London"
    assert config.timeout_s == 15.0
    assert config.master_state_path == master_path.resolve()
    assert config.state_path == state_path.resolve()
    assert config.legacy_state_path == legacy_path.resolve()
