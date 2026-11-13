"""Post-deploy reachability and TLS checks."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass

PORTS = {25: "smtp", 443: "https", 465: "smtps", 995: "pop3s"}
TLS_PORTS = (443, 465, 995)


@dataclass(frozen=True)
class Result:
    port: int
    name: str
    ok: bool
    detail: str


def _tcp(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        pass


def _tls(host: str, port: int, server_name: str, timeout: float) -> None:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=server_name):
            pass


def run(host: str, *, domain: str, timeout: float = 10.0) -> list[Result]:
    results: list[Result] = []
    for port, name in PORTS.items():
        try:
            _tcp(host, port, timeout)
            results.append(Result(port, name, True, "reachable"))
        except OSError as exc:
            results.append(Result(port, name, False, str(exc)))
    for port in TLS_PORTS:
        try:
            _tls(host, port, domain, timeout)
            results.append(Result(port, f"{PORTS[port]} tls", True, "verify ok"))
        except (OSError, ssl.SSLError) as exc:
            results.append(Result(port, f"{PORTS[port]} tls", False, str(exc)))
    return results
