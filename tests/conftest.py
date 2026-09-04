# Shared test setup.
#
# Config() normally reads AWS Secrets Manager, which would make every test need
# an AWS account. LOCAL_CONFIG=1 makes it read these env vars instead, so the
# whole suite runs offline. This has to happen before app modules are imported.

import os

os.environ.setdefault("LOCAL_CONFIG", "1")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")
os.environ.setdefault("TENSORZERO_URL", "http://localhost:3000")
os.environ.setdefault("API_KEY", "test-key-12345")

import pytest
from app.config import Config


@pytest.fixture
def config() -> Config:
    return Config()
