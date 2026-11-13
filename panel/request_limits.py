"""In-memory rate limits for panel login."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_login_failures: dict[str, list[float]] = defaultdict(list)
_MAX_TRACKED_IPS = 4096


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def login_max_attempts() -> int:
    return max(1, _env_int("LOGIN_RATE_LIMIT", 5))


def login_window_seconds() -> int:
    return max(1, _env_int("LOGIN_RATE_WINDOW", 300))


def _prune(times: list[float], now: float, window: float) -> list[float]:
    return [stamp for stamp in times if now - stamp < window]


def _prune_login_map(store: dict[str, list[float]], now: float, window: float) -> None:
    for ip in list(store.keys()):
        fails = _prune(store[ip], now, window)
        if fails:
            store[ip] = fails
        else:
            del store[ip]
    while len(store) > _MAX_TRACKED_IPS:
        store.pop(next(iter(store)))


def login_blocked(client_ip: str) -> bool:
    window = float(login_window_seconds())
    now = time.time()
    with _lock:
        _prune_login_map(_login_failures, now, window)
        fails = _login_failures.get(client_ip, [])
        return len(fails) >= login_max_attempts()


def record_login_failure(client_ip: str) -> None:
    now = time.time()
    window = float(login_window_seconds())
    with _lock:
        fails = _login_failures.get(client_ip, [])
        fails.append(now)
        _login_failures[client_ip] = fails
        _prune_login_map(_login_failures, now, window)


def clear_login_failures(client_ip: str) -> None:
    with _lock:
        _login_failures.pop(client_ip, None)


def reset_for_tests() -> None:
    with _lock:
        _login_failures.clear()
