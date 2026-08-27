from app.config import Config


def test_defaults_point_at_local_compose(monkeypatch):
    for key in ("REDIS_URL", "DATABASE_URL", "API_KEY", "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)

    config = Config.from_env()

    assert config.redis_url == "redis://localhost:6379"
    assert config.database_url.endswith("/research")
    assert config.api_key == ""


def test_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://cache.internal:6379")
    monkeypatch.setenv("API_KEY", "secret")

    config = Config.from_env()

    assert config.redis_url == "redis://cache.internal:6379"
    assert config.api_key == "secret"
