"""CSV import and map sync, delegating to the panel package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_DIR = REPO_ROOT / "panel"


def _panel():
    if str(PANEL_DIR) not in sys.path:
        sys.path.insert(0, str(PANEL_DIR))
    import users as panel_users  # noqa: PLC0415

    return panel_users


def import_csv(
    csv_path: Path,
    *,
    db: Path,
    domain: str,
    missing: bool = False,
) -> int | None:
    """Import accounts from CSV. Returns the count, or None when skipped."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"{csv_path} missing")
    os.environ["MAILPANEL_DB"] = str(db)
    os.environ["MAIL_DOMAIN"] = domain
    panel = _panel()
    if missing:
        return panel.import_csv_missing(str(csv_path))
    return panel.import_csv_if_empty(str(csv_path))
