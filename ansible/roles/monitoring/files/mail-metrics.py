#!/usr/bin/env python3
"""Tail mail.log + Postfix queue → Prometheus on 127.0.0.1:9154."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BIND = os.environ.get("MAIL_METRICS_BIND", "127.0.0.1")
PORT = int(os.environ.get("MAIL_METRICS_PORT", "9154"))
LOG_PATH = Path(os.environ.get("MAIL_LOG", "/var/log/mail.log"))
QUEUE_INTERVAL = 15

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_gauges: dict[str, float] = {
    "mail_postfix_queue_messages": 0.0,
    "mail_metrics_up": 1.0,
}


def _inc(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    key = (name, tuple(sorted((labels or {}).items())))
    with _lock:
        _counters[key] += value


def _set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def classify(line: str) -> None:
    _inc("mail_log_lines_total")
    if "postfix/" in line:
        if ": connect from " in line:
            service = "smtps" if "postfix/smtps" in line else "smtp"
            _inc("mail_postfix_connects_total", {"service": service})
        if "status=sent" in line:
            _inc("mail_postfix_status_total", {"status": "sent"})
        elif "status=bounced" in line:
            _inc("mail_postfix_status_total", {"status": "bounced"})
        elif "status=deferred" in line:
            _inc("mail_postfix_status_total", {"status": "deferred"})
        if "NOQUEUE: reject" in line or " reject: " in line:
            _inc("mail_postfix_status_total", {"status": "rejected"})
        if "blocked using " in line:
            _inc("mail_postfix_rbl_reject_total")
    if "dovecot:" in line:
        if "pop3-login:" in line and "Login:" in line and "auth_failed" not in line:
            _inc("mail_dovecot_pop3_login_total", {"result": "ok"})
        if "auth_failed" in line:
            _inc("mail_dovecot_pop3_login_total", {"result": "fail"})
        if "saved mail to INBOX" in line:
            _inc("mail_dovecot_lmtp_saved_total")
    if "opendkim[" in line:
        if "DKIM verification successful" in line:
            _inc("mail_opendkim_verify_total", {"result": "ok"})
        elif "verification failed" in line or "bad signature" in line:
            _inc("mail_opendkim_verify_total", {"result": "fail"})


def follow_log() -> None:
    while True:
        try:
            with LOG_PATH.open(encoding="utf-8", errors="replace") as fh:
                fh.seek(0, os.SEEK_END)
                while True:
                    line = fh.readline()
                    if line:
                        classify(line)
                        continue
                    time.sleep(0.25)
                    if not LOG_PATH.exists() or fh.tell() > LOG_PATH.stat().st_size:
                        break
        except OSError:
            time.sleep(1)


_QUEUE_REQ = re.compile(r"in (\d+) Request")


def poll_queue() -> None:
    while True:
        try:
            proc = subprocess.run(
                ["postqueue", "-p"],
                capture_output=True,
                text=True,
                check=False,
            )
            text = proc.stdout or ""
            if "Mail queue is empty" in text:
                _set_gauge("mail_postfix_queue_messages", 0)
            else:
                match = _QUEUE_REQ.search(text)
                _set_gauge("mail_postfix_queue_messages", float(match.group(1)) if match else 0)
        except OSError:
            _set_gauge("mail_postfix_queue_messages", 0)
        time.sleep(QUEUE_INTERVAL)


def render() -> bytes:
    lines = [
        "# HELP mail_metrics_up Mail log scraper is running.",
        "# TYPE mail_metrics_up gauge",
        "# HELP mail_postfix_queue_messages Messages waiting in the Postfix queue.",
        "# TYPE mail_postfix_queue_messages gauge",
        "# HELP mail_log_lines_total Mail log lines consumed.",
        "# TYPE mail_log_lines_total counter",
        "# HELP mail_postfix_connects_total SMTP/SMTPS inbound connects.",
        "# TYPE mail_postfix_connects_total counter",
        "# HELP mail_postfix_status_total Postfix delivery / reject outcomes.",
        "# TYPE mail_postfix_status_total counter",
        "# HELP mail_postfix_rbl_reject_total Recipients rejected by DNSBL.",
        "# TYPE mail_postfix_rbl_reject_total counter",
        "# HELP mail_dovecot_pop3_login_total POP3S login attempts.",
        "# TYPE mail_dovecot_pop3_login_total counter",
        "# HELP mail_dovecot_lmtp_saved_total Messages stored via LMTP.",
        "# TYPE mail_dovecot_lmtp_saved_total counter",
        "# HELP mail_opendkim_verify_total Inbound DKIM verify results.",
        "# TYPE mail_opendkim_verify_total counter",
    ]
    with _lock:
        for name, value in _gauges.items():
            lines.append(f"{name} {value}")
        for (name, labels), value in sorted(_counters.items()):
            if labels:
                joined = ",".join(f'{k}="{v}"' for k, v in labels)
                lines.append(f"{name}{{{joined}}} {value}")
            else:
                lines.append(f"{name} {value}")
    lines.append("")
    return ("\n".join(lines)).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/metrics":
            self.send_error(404)
            return
        body = render()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    threading.Thread(target=follow_log, daemon=True).start()
    threading.Thread(target=poll_queue, daemon=True).start()
    print(f"mail-metrics listening {BIND}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
