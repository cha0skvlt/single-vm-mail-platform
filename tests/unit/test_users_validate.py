"""Local-part validation rejects traversal and mail separators."""

from __future__ import annotations

import sys

import pytest


@pytest.mark.unit
def test_validate_local_rejects_bad_names(repo_root, monkeypatch):
    monkeypatch.setenv("SKIP_MAIL_SYNC", "1")
    monkeypatch.setenv("SKIP_AUTOREPLY_SYNC", "1")
    sys.path.insert(0, str(repo_root / "panel"))
    from users import UsersError, validate_local

    assert validate_local("Abramov") == "abramov"
    for bad in ("", "a@b", "../root", "foo/bar", "a..b", "-no", ".dot"):
        try:
            validate_local(bad)
            raise AssertionError(bad)
        except UsersError:
            pass
