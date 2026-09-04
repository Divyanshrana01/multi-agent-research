# Tests for config loading, including the local mode that lets the app run
# without an AWS account.

import os
import pytest
from app import config as config_mod


def test_local_config_reads_environment_variables(config):
    assert config.redis_url == os.environ["REDIS_URL"]
    assert config.database_url == os.environ["DATABASE_URL"]
    assert config.tensorzero_url == os.environ["TENSORZERO_URL"]


def test_defaults_are_applied_for_optional_settings(config):
    assert config.cache_ttl == 3600
    assert config.agent_max_iterations == 2
    assert config.consumer_group == "workers"
    # guardrails are optional so local runs don't need a bedrock guardrail
    assert config.bedrock_guardrail_id == ""


def test_missing_required_setting_says_which_one():
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        config_mod._required({"DATABASE_URL": "x"}, "REDIS_URL")


def test_required_rejects_an_empty_value():
    # an empty string in the secret is as broken as a missing key
    with pytest.raises(RuntimeError):
        config_mod._required({"REDIS_URL": ""}, "REDIS_URL")


def test_env_loader_only_picks_up_known_settings(monkeypatch):
    monkeypatch.setenv("CACHE_TTL", "99")
    monkeypatch.setenv("SOMETHING_UNRELATED", "ignore me")
    data = config_mod._load_from_env()
    assert data["CACHE_TTL"] == "99"
    assert "SOMETHING_UNRELATED" not in data
