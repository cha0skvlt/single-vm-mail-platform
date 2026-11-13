"""HTTP panel: login, rate limit, API auth, CRUD, client IP."""

from __future__ import annotations

import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest


@pytest.fixture
def panel_http(repo_root, tmp_path, monkeypatch):
    monkeypatch.setenv("MAILPANEL_DB", str(tmp_path / "users.db"))
    monkeypatch.setenv("MAIL_DOMAIN", "example.com")
    monkeypatch.setenv("SKIP_MAIL_SYNC", "1")
    monkeypatch.setenv("SKIP_AUTOREPLY_SYNC", "1")
    monkeypatch.setenv("MAIL_ADMIN_USER", "admin")
    monkeypatch.setenv("MAIL_ADMIN_PASSWORD", "correct-horse")
    monkeypatch.setenv("MAIL_SESSION_SECRET", "unit-test-session-secret")
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    monkeypatch.setenv("LOGIN_RATE_WINDOW", "300")
    panel = str(repo_root / "panel")
    if panel not in sys.path:
        sys.path.insert(0, panel)
    for name in ("db", "users", "redirects", "autoreplies", "auth", "request_limits", "server"):
        sys.modules.pop(name, None)
    import request_limits
    import server
    import users

    request_limits.reset_for_tests()
    monkeypatch.setattr(users, "hash_password", lambda pw: "{SSHA512}" + pw)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield {"host": host, "port": port, "auth": __import__("auth"), "limits": request_limits}
    httpd.shutdown()
    httpd.server_close()
    request_limits.reset_for_tests()


def _request(ctx, method, path, *, body=None, headers=None, cookie=None):
    conn = http.client.HTTPConnection(ctx["host"], ctx["port"], timeout=3)
    hdrs = dict(headers or {})
    if cookie:
        hdrs["Cookie"] = cookie
    payload = body.encode("utf-8") if body is not None else None
    if payload is not None and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        hdrs["Content-Length"] = str(len(payload))
    conn.request(method, path, body=payload, headers=hdrs)
    res = conn.getresponse()
    raw = res.read()
    hdr = {k.lower(): v for k, v in res.getheaders()}
    conn.close()
    return res.status, raw, hdr


def _login_cookie(ctx) -> str:
    status, _, headers = _request(
        ctx,
        "POST",
        "/login",
        body=urlencode({"username": "admin", "password": "correct-horse"}),
    )
    assert status == 303
    return headers["set-cookie"].split(";", 1)[0]


@pytest.mark.unit
def test_login_rejects_bad_password(panel_http):
    status, body, _ = _request(
        panel_http,
        "POST",
        "/login",
        body=urlencode({"username": "admin", "password": "nope"}),
    )
    assert status == 401
    assert b"login-error" in body


@pytest.mark.unit
def test_login_rate_limit_returns_429(panel_http):
    form = urlencode({"username": "admin", "password": "nope"})
    for _ in range(3):
        status, _, _ = _request(panel_http, "POST", "/login", body=form)
        assert status == 401
    status, _, _ = _request(panel_http, "POST", "/login", body=form)
    assert status == 429


@pytest.mark.unit
def test_api_without_cookie_is_401_json(panel_http):
    status, body, headers = _request(panel_http, "GET", "/api/users")
    assert status == 401
    assert json.loads(body) == {"error": "unauthorized"}
    assert "location" not in headers


@pytest.mark.unit
def test_api_crud_with_session(panel_http):
    cookie = _login_cookie(panel_http)
    status, body, _ = _request(
        panel_http,
        "POST",
        "/api/users",
        body=urlencode({"local": "sokolov", "password": "secret12"}),
        cookie=cookie,
    )
    assert status == 201, body
    assert json.loads(body)["local"] == "sokolov"

    status, body, _ = _request(panel_http, "GET", "/api/users", cookie=cookie)
    assert status == 200
    assert json.loads(body)["users"][0]["local"] == "sokolov"

    status, _, _ = _request(
        panel_http,
        "POST",
        "/api/users/sokolov/password",
        body=urlencode({"password": "newpass99"}),
        cookie=cookie,
    )
    assert status == 200

    status, body, _ = _request(
        panel_http,
        "POST",
        "/api/users",
        body=urlencode({"local": "main", "password": "secret12"}),
        cookie=cookie,
    )
    assert status == 201, body
    status, body, _ = _request(panel_http, "GET", "/api/users/sokolov/redirects", cookie=cookie)
    assert status == 200
    assert json.loads(body)["destinations"] == []
    status, body, _ = _request(
        panel_http,
        "POST",
        "/api/users/sokolov/redirects",
        body=urlencode({"destinations": "main"}),
        cookie=cookie,
    )
    assert status == 200, body
    assert json.loads(body)["destinations"] == ["main"]
    status, body, _ = _request(panel_http, "GET", "/api/users/sokolov/redirects", cookie=cookie)
    assert json.loads(body)["destinations"] == ["main"]

    status, body, _ = _request(
        panel_http, "GET", "/api/users/sokolov/autoreply", cookie=cookie
    )
    assert status == 200
    assert json.loads(body)["body"] == ""
    status, body, _ = _request(
        panel_http,
        "POST",
        "/api/users/sokolov/autoreply",
        body=urlencode({"body": "Not at my desk"}),
        cookie=cookie,
    )
    assert status == 200, body
    assert json.loads(body)["body"] == "Not at my desk"
    status, body, _ = _request(
        panel_http, "GET", "/api/users/sokolov/autoreply", cookie=cookie
    )
    assert json.loads(body)["body"] == "Not at my desk"

    status, _, _ = _request(
        panel_http,
        "POST",
        "/api/users/sokolov/delete",
        body="",
        cookie=cookie,
    )
    assert status == 200
    status, _, _ = _request(
        panel_http,
        "POST",
        "/api/users/main/delete",
        body="",
        cookie=cookie,
    )
    assert status == 200
    status, body, _ = _request(panel_http, "GET", "/api/users", cookie=cookie)
    assert json.loads(body)["users"] == []


@pytest.mark.unit
def test_api_decodes_percent_encoded_local(panel_http):
    cookie = _login_cookie(panel_http)
    status, _, _ = _request(
        panel_http,
        "POST",
        "/api/users",
        body=urlencode({"local": "ok.user", "password": "secret12"}),
        cookie=cookie,
    )
    assert status == 201
    status, body, _ = _request(
        panel_http,
        "POST",
        "/api/users/ok%2Euser/delete",
        body="",
        cookie=cookie,
    )
    assert status == 200, body
    status, body, _ = _request(panel_http, "GET", "/api/users", cookie=cookie)
    assert json.loads(body)["users"] == []


@pytest.mark.unit
def test_client_ip_prefers_x_real_ip(panel_http):
    form = urlencode({"username": "admin", "password": "nope"})
    _request(
        panel_http,
        "POST",
        "/login",
        body=form,
        headers={"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "198.51.100.1"},
    )
    assert panel_http["limits"].login_blocked("203.0.113.9") is False
    for _ in range(2):
        _request(
            panel_http,
            "POST",
            "/login",
            body=form,
            headers={"X-Real-IP": "203.0.113.9", "X-Forwarded-For": "198.51.100.1"},
        )
    assert panel_http["limits"].login_blocked("203.0.113.9") is True
    assert panel_http["limits"].login_blocked("198.51.100.1") is False


@pytest.mark.unit
def test_auth_verify_requires_session(panel_http):
    status, body, headers = _request(panel_http, "GET", "/auth/verify")
    assert status == 401
    assert body == b""
    assert "location" not in headers

    cookie = _login_cookie(panel_http)
    status, body, headers = _request(panel_http, "GET", "/auth/verify", cookie=cookie)
    assert status == 200
    assert body == b""
    assert headers.get("x-user") == "admin"


@pytest.mark.unit
def test_api_health_requires_session(panel_http, monkeypatch):
    import server

    monkeypatch.setattr(
        server,
        "mail_health",
        lambda: {
            "overall": "ok",
            "ok": True,
            "checks": [{"name": "postfix", "ok": True}],
        },
    )
    status, body, headers = _request(panel_http, "GET", "/api/health")
    assert status == 401
    assert json.loads(body) == {"error": "unauthorized"}
    assert "location" not in headers

    cookie = _login_cookie(panel_http)
    status, body, _ = _request(panel_http, "GET", "/api/health", cookie=cookie)
    assert status == 200
    assert json.loads(body)["ok"] is True


@pytest.mark.unit
def test_health_is_local_only(panel_http):
    status, body, _ = _request(panel_http, "GET", "/health")
    assert status == 200
    assert body == b"ok\n"

    status, _, headers = _request(
        panel_http, "GET", "/health", headers={"X-Real-IP": "203.0.113.10"}
    )
    assert status == 303
    assert "/login" in headers.get("location", "")
