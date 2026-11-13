#!/usr/bin/env bash
# Import CSV into SQLite only when the database is empty. Always refresh maps if DB exists.
set -euo pipefail
CSV="${1:?usage: mail-users-import.sh <csv>}"
export MAILPANEL_DB="${MAILPANEL_DB:-/var/lib/mailpanel/users.db}"
export MAIL_DOMAIN="${MAIL_DOMAIN:-example.com}"
PANEL_PY="${PYTHONPATH:-/opt/mail/panel}"
export PYTHONPATH="${PANEL_PY}"

python3 - "$CSV" "$PANEL_PY" <<'PY'
import os
import sys

sys.path.insert(0, sys.argv[2])
from users import import_csv_if_empty, import_csv_missing

if os.environ.get("IMPORT_MISSING", "").strip() in {"1", "true", "yes"}:
    n = import_csv_missing(sys.argv[1])
    print(f"imported {n} missing accounts")
else:
    n = import_csv_if_empty(sys.argv[1])
    if n is None:
        print("import skipped (database not empty)")
    else:
        print(f"imported {n} accounts")
PY

if [[ "${SKIP_MAIL_SYNC:-}" != "1" && -f "${MAILPANEL_DB}" ]]; then
  "${MAIL_USERS_SYNC:-/usr/local/sbin/mail-users-sync}"
fi
