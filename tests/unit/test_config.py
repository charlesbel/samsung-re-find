from samsung_find.config import FindConfig


def test_default_config(monkeypatch):
    monkeypatch.delenv("SAMSUNG_FIND_COUNTRY", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_LANGUAGE", raising=False)
    monkeypatch.delenv("SAMSUNG_FIND_TIMEZONE", raising=False)
    monkeypatch.delenv("SAMSUNG_ACCOUNT_MASTER_STATE", raising=False)

    config = FindConfig()
    assert config.country == "US"
    assert config.language == "en"
    assert config.timezone == "UTC"
    assert config.timeout_s == 30.0


def test_config_env_overrides(monkeypatch, tmp_path):
    master_path = tmp_path / "master.json"
    monkeypatch.setenv("SAMSUNG_FIND_COUNTRY", "FR")
    monkeypatch.setenv("SAMSUNG_FIND_LANGUAGE", "fr")
    monkeypatch.setenv("SAMSUNG_FIND_TIMEZONE", "Europe/Paris")
    monkeypatch.setenv("SAMSUNG_ACCOUNT_MASTER_STATE", str(master_path))

    config = FindConfig()
    assert config.country == "FR"
    assert config.language == "fr"
    assert config.timezone == "Europe/Paris"
    assert config.master_state_path == master_path.resolve()


def test_config_explicit_overrides():
    config = FindConfig(
        country="gb",
        language="en-GB",
        timezone="Europe/London",
        timeout_s=15.0,
    )
    assert config.country == "GB"
    assert config.language == "en-GB"
    assert config.timezone == "Europe/London"
    assert config.timeout_s == 15.0
