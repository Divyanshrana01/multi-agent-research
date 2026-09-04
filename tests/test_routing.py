# Tests that the API and the frontend's own routes don't collide, and that
# auth works without waiting for startup to finish.
#
# TestClient is used without entering the lifespan on purpose: these checks are
# about routing and dependencies, and shouldn't need redis or postgres running.

import pytest
from fastapi.testclient import TestClient
from app.main import app, DIST

# raise_server_exceptions=False so a handler that needs the database returns a
# 500 response here instead of exploding the test — these tests only care about
# what routing and auth decided, not what happened afterwards.
client = TestClient(app, raise_server_exceptions=False)


def test_api_key_is_checked_without_waiting_for_startup():
    # require_api_key reads app.state.config. it used to be set inside lifespan,
    # so a request arriving during a failed startup raised AttributeError
    # instead of returning a clean 401.
    response = client.get("/api/reports")
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_a_valid_key_gets_past_auth():
    # 401 means it was rejected; anything else means auth let it through and it
    # failed later on the database, which is what we want here
    response = client.get("/api/reports", headers={"X-API-Key": "test-key-12345"})
    assert response.status_code != 401


def test_health_needs_no_key():
    # the load balancer can't send one
    assert client.get("/health").status_code == 200


def test_unknown_api_paths_are_404_not_the_app_shell():
    # the SPA catch-all must not swallow a mistyped API path, or a typo in a
    # fetch would return HTML and fail somewhere far away
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert "<div id=" not in response.text


@pytest.mark.skipif(not DIST.is_dir(), reason="frontend not built")
@pytest.mark.parametrize("path", ["/", "/reports", "/reports/some-id", "/settings", "/anything-else"])
def test_client_routes_serve_the_app_shell(path):
    # refreshing the browser on a client-side route has to work
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="root">' in response.text
