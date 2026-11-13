#!/usr/bin/env bash
# Write or clear one mailbox vacation script. Does not touch users maps.
set -euo pipefail

DOMAIN="${MAIL_DOMAIN:-example.com}"
VMAIL_HOME="${VMAIL_HOME:-/var/vmail}"
VMAIL_USER="${VMAIL_USER:-vmail}"
VMAIL_GROUP="${VMAIL_GROUP:-vmail}"

if [[ $# -ne 1 ]]; then
  echo "usage: mail-autoreply-sync LOCAL" >&2
  exit 2
fi

LOCAL="$1"
if [[ ! "${LOCAL}" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || [[ "${LOCAL}" == *..* ]] || [[ "${LOCAL}" == */* ]] || [[ "${LOCAL}" == *@* ]]; then
  echo "error: invalid login" >&2
  exit 2
fi

HOME_DIR="${VMAIL_HOME}/${DOMAIN}/${LOCAL}"
SIEVE_DIR="${HOME_DIR}/sieve"
ACTIVE="${HOME_DIR}/.dovecot.sieve"
SCRIPT="${SIEVE_DIR}/autoreply.sieve"
SCRIPT_TMP="${SIEVE_DIR}/.autoreply.sieve.tmp"
BIN="${SIEVE_DIR}/autoreply.svbin"
DUPES="${HOME_DIR}/.dovecot.lda-dupes"
DUPES_LOCK="${HOME_DIR}/.dovecot.lda-dupes.lock"

BODY="$(python3 -c 'import sys; print(sys.stdin.read().replace("\r\n","\n").replace("\r","\n").strip(), end="")')"

clear_files() {
  rm -f "${ACTIVE}" "${SCRIPT}" "${SCRIPT_TMP}" "${BIN}" "${DUPES}" "${DUPES_LOCK}"
}

if [[ -z "${BODY}" ]]; then
  clear_files
  echo "cleared ${LOCAL}"
  exit 0
fi

SIEVE="$(printf '%s' "${BODY}" | MAIL_DOMAIN="${DOMAIN}" python3 -c '
import os
import re
import sys

local = sys.argv[1]
domain = os.environ.get("MAIL_DOMAIN", "example.com").strip().lower()
body = sys.stdin.read()
if "\x00" in body or len(body) > 4000:
    sys.exit(2)
if re.search(r"(?i)\b(fileinto|redirect|discard|reject|execute|pipe)\b", body):
    sys.exit(2)
lines = []
for line in body.split("\n"):
    lines.append("." + line if line.startswith(".") else line)
text = "\n".join(lines)
sys.stdout.write(
    "require [\"vacation\"];\n"
    "vacation\n"
    "  :days 1\n"
    "  :subject \"Autoreply\"\n"
    f"  :addresses \"{local}@{domain}\"\n"
    "text:\n"
    f"{text}\n"
    ".\n"
    ";\n"
)
' "${LOCAL}")" || {
  echo "error: invalid autoreply" >&2
  exit 2
}

ensure_dir() {
  local path="$1"
  if [[ "${SKIP_CHOWN:-}" == "1" ]]; then
    mkdir -p "${path}"
    chmod 0700 "${path}" || true
    return
  fi
  install -d -o "${VMAIL_USER}" -g "${VMAIL_GROUP}" -m 0700 "${path}"
}

if [[ ! -d "${HOME_DIR}" ]]; then
  ensure_dir "${HOME_DIR}"
fi
ensure_dir "${SIEVE_DIR}"

printf '%s' "${SIEVE}" > "${SCRIPT_TMP}"

if [[ "${SKIP_SIEVEC:-}" != "1" ]]; then
  if [[ "${SKIP_CHOWN:-}" == "1" ]]; then
    sievec "${SCRIPT_TMP}" || { rm -f "${SCRIPT_TMP}"; exit 1; }
  else
    chown "${VMAIL_USER}:${VMAIL_GROUP}" "${SCRIPT_TMP}"
    sudo --non-interactive -u "${VMAIL_USER}" sievec "${SCRIPT_TMP}" || { rm -f "${SCRIPT_TMP}"; exit 1; }
  fi
  rm -f "${SCRIPT_TMP}.svbin"
fi

mv -f "${SCRIPT_TMP}" "${SCRIPT}"
ln -sfn "sieve/autoreply.sieve" "${ACTIVE}"
rm -f "${DUPES}" "${DUPES_LOCK}"

if [[ "${SKIP_CHOWN:-}" != "1" ]]; then
  chown "${VMAIL_USER}:${VMAIL_GROUP}" "${SCRIPT}" "${ACTIVE}"
  if [[ -f "${BIN}" ]]; then
    chown "${VMAIL_USER}:${VMAIL_GROUP}" "${BIN}"
  fi
fi

echo "set ${LOCAL}"
