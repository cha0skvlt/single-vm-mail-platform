#!/usr/bin/env python3
"""mail.example.com — mailbox panel (fork of prod-status auth + chrome)."""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

import request_limits
from auth import (
    clear_session_cookie,
    credentials_configured,
    issue_session_cookie,
    session_user,
    verify_login,
)
from autoreplies import list_autoreply, set_autoreply
from redirects import list_redirects, set_redirects
from users import UsersError, add_user, delete_user, list_users, mail_domain, set_password

MAIL_HEALTH_UNITS = ("postfix", "dovecot", "opendkim")


def _unit_is_active(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.stdout.strip() == "active"


def mail_health() -> dict[str, object]:
    checks = [{"name": name, "ok": _unit_is_active(name)} for name in MAIL_HEALTH_UNITS]
    ok = all(bool(item["ok"]) for item in checks)
    return {"overall": "ok" if ok else "down", "ok": ok, "checks": checks}


STATIC = Path(__file__).resolve().parent / "static"
STATIC_ROOT = STATIC.resolve()
PORT = int(os.environ.get("PORT", "8080"))
BIND = os.environ.get("PANEL_BIND", "127.0.0.1")
MAX_FORM_BODY_BYTES = 65536
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
STRICT_TRANSPORT_SECURITY = "max-age=31536000; includeSubDomains; preload"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}

PUBLIC_PATHS = frozenset(
    {
        "/login",
        "/css/tokens.css",
        "/css/login.css",
        "/img/mark.svg",
        "/img/favicon-mail.svg",
        "/js/login.js",
        "/js/theme-boot.js",
    }
)


class BadRequestError(Exception):
    pass


class Handler(BaseHTTPRequestHandler):
    server_version = "mail"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return self.server_version

    def end_headers(self) -> None:
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("Strict-Transport-Security", STRICT_TRANSPORT_SECURITY)
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        return

    def _path(self) -> str:
        path = self.path.split("?", 1)[0]
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        return path

    def _current_user(self) -> str | None:
        return session_user(self.headers.get("Cookie"))

    def _public_origin(self) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "https").split(",", 1)[0].strip()
        host = (
            self.headers.get("X-Forwarded-Host")
            or self.headers.get("Host")
            or "mail.example.com"
        )
        host = host.split(",", 1)[0].strip()
        return f"{proto}://{host}"

    def _redirect(self, location: str, *, cookies: list[str] | None = None) -> None:
        if location.startswith("/"):
            location = f"{self._public_origin()}{location}"
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        if cookies:
            for header in cookies:
                self.send_header("Set-Cookie", header)
        self.end_headers()

    def _require_user(self) -> str | None:
        user = self._current_user()
        if user:
            return user
        if self._path() in PUBLIC_PATHS:
            return None
        if self._path().startswith("/api/"):
            self._send_json({"error": "unauthorized"}, status=401)
            return None
        self._redirect("/login")
        return None

    def _client_ip(self) -> str:
        if self.headers:
            real = self.headers.get("X-Real-IP", "").strip()
            if real:
                return real.split(",")[0].strip()
            xff = self.headers.get("X-Forwarded-For", "").strip()
            if xff:
                return xff.split(",")[-1].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _resolve_static(self, rel: str) -> Path | None:
        try:
            candidate = (STATIC_ROOT / rel).resolve()
        except (OSError, ValueError, RuntimeError):
            return None
        try:
            candidate.relative_to(STATIC_ROOT)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def _parse_form(self) -> dict[str, str]:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise BadRequestError("invalid Content-Length") from exc
        if length < 0 or length > MAX_FORM_BODY_BYTES:
            raise BadRequestError("body too large")
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = parse_qs(body, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def _send_bytes(self, data: bytes, *, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: object, *, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self._send_bytes(body, content_type="application/json; charset=utf-8", status=status)

    def _send_login_page(self, *, show_error: bool = False, status: int = 200) -> None:
        file_path = self._resolve_static("login.html")
        if file_path is None:
            self.send_error(404)
            return
        body = file_path.read_bytes()
        if show_error:
            body = body.replace(
                b'id="login-error" class="login-error" hidden',
                b'id="login-error" class="login-error"',
            )
        self._send_bytes(body, content_type="text/html; charset=utf-8", status=status)

    def _send_static(self, rel: str) -> None:
        file_path = self._resolve_static(rel)
        if file_path is None:
            self.send_error(404)
            return
        body = file_path.read_bytes()
        if rel == "index.html":
            body = body.replace(b"__MAIL_DOMAIN__", mail_domain().encode())
        self._send_bytes(
            body,
            content_type=MIME.get(file_path.suffix, "application/octet-stream"),
        )

    def _is_loopback_client(self) -> bool:
        addr = self.client_address[0] if self.client_address else ""
        if addr not in ("127.0.0.1", "::1"):
            return False
        # nginx makes every request look local; forwarded headers mean "via proxy".
        if self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For"):
            return False
        return True

    def do_GET(self) -> None:
        path = self._path()
        if path == "/health":
            if self._current_user() or self._is_loopback_client():
                self._send_bytes(b"ok\n", content_type="text/plain; charset=utf-8")
                return
            self._redirect("/login")
            return
        if path == "/auth/verify":
            user = self._current_user()
            if user:
                self.send_response(200)
                self.send_header("X-User", user)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(401)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/login":
            if self._current_user():
                self._redirect("/")
                return
            self._send_login_page()
            return
        if path in PUBLIC_PATHS:
            self._send_static(path.lstrip("/"))
            return
        if path in ("", "/"):
            if not self._require_user():
                return
            self._send_static("index.html")
            return
        if path == "/api/health":
            if not self._require_user():
                return
            self._send_json(mail_health())
            return
        if path == "/api/users":
            if not self._require_user():
                return
            self._send_json({"users": list_users()})
            return
        if path.endswith("/redirects") and path.startswith("/api/users/"):
            if not self._require_user():
                return
            local = unquote(path[len("/api/users/") : -len("/redirects")])
            try:
                self._send_json(list_redirects(local))
            except UsersError as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if path.endswith("/autoreply") and path.startswith("/api/users/"):
            if not self._require_user():
                return
            local = unquote(path[len("/api/users/") : -len("/autoreply")])
            try:
                self._send_json(list_autoreply(local))
            except UsersError as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        if not self._require_user():
            return
        self._send_static(path.lstrip("/"))

    def do_POST(self) -> None:
        path = self._path()
        if path == "/login":
            if not credentials_configured():
                self.send_error(503)
                return
            client_ip = self._client_ip()
            if request_limits.login_blocked(client_ip):
                self.send_error(429)
                return
            try:
                form = self._parse_form()
            except BadRequestError:
                self.send_error(400)
                return
            username = form.get("username", "")
            password = form.get("password", "")
            if not verify_login(username, password):
                request_limits.record_login_failure(client_ip)
                print(f'auth.login_fail remote="{client_ip}"', flush=True)
                self._send_login_page(show_error=True, status=401)
                return
            request_limits.clear_login_failures(client_ip)
            print(f'auth.login_ok username="{username}"', flush=True)
            self._redirect("/", cookies=[issue_session_cookie(username)])
            return
        if path == "/logout":
            self._redirect("/login", cookies=[clear_session_cookie()])
            return
        if not self._require_user():
            return
        try:
            form = self._parse_form()
        except BadRequestError:
            self.send_error(400)
            return
        try:
            if path == "/api/users":
                user = add_user(form.get("local", ""), form.get("password", ""))
                self._send_json(user, status=201)
                return
            if path.endswith("/password") and path.startswith("/api/users/"):
                local = unquote(path[len("/api/users/") : -len("/password")])
                set_password(local, form.get("password", ""))
                self._send_json({"ok": True})
                return
            if path.endswith("/delete") and path.startswith("/api/users/"):
                local = unquote(path[len("/api/users/") : -len("/delete")])
                delete_user(local)
                self._send_json({"ok": True})
                return
            if path.endswith("/redirects") and path.startswith("/api/users/"):
                local = unquote(path[len("/api/users/") : -len("/redirects")])
                self._send_json(set_redirects(local, form.get("destinations", "")))
                return
            if path.endswith("/autoreply") and path.startswith("/api/users/"):
                local = unquote(path[len("/api/users/") : -len("/autoreply")])
                self._send_json(
                    set_autoreply(
                        local,
                        form.get("body", ""),
                        form.get("start_date", ""),
                        form.get("end_date", ""),
                    )
                )
                return
        except UsersError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        except (OSError, subprocess.CalledProcessError):
            self._send_json({"error": "sync failed"}, status=500)
            return
        self.send_error(405)


def main() -> None:
    print(f"mailpanel listening {BIND}:{PORT}", flush=True)
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
