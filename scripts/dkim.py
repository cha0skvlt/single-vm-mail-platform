"""DKIM private key and published DNS record checks."""

from __future__ import annotations

import re
from pathlib import Path

RECORD_RE = re.compile(
    r'^(?P<name>[^\s]+)\s+IN\s+TXT\s+"(?P<value>[^"]+)"',
    re.MULTILINE,
)


def check(
    *,
    domain: str,
    selector: str,
    keyfile: Path,
    record_file: Path,
) -> list[str]:
    problems: list[str] = []
    if not keyfile.is_file():
        problems.append(f"missing private key {keyfile}")
    if not record_file.is_file():
        problems.append(f"missing DNS record {record_file}")
        return problems

    text = record_file.read_text(encoding="utf-8")
    match = RECORD_RE.search(text)
    if match is None:
        problems.append(f"{record_file}: no TXT record found")
        return problems

    expected = f"{selector}._domainkey.{domain}."
    if match.group("name") != expected:
        problems.append(
            f"{record_file}: expected {expected}, found {match.group('name')}"
        )
    value = match.group("value")
    if "v=DKIM1" not in value:
        problems.append(f"{record_file}: missing v=DKIM1")
    if "p=" not in value:
        problems.append(f"{record_file}: missing p= public key")
    return problems
