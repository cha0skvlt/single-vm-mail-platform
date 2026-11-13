#!/usr/bin/env bash
# Post-deploy smoke: mail ports reachable + TLS valid on submission/POP3S.
# Usage: DEPLOY_HOST=<ip> scripts/smoke-mail.sh   (or reads ansible/inventory.ini)
set -euo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "$0")/_lib.sh"
ROOT="$(scripts_repo_root)"

HOST="${DEPLOY_HOST:-}"
if [[ -z "${HOST}" && -f "${ROOT}/ansible/inventory.ini" ]]; then
  read -r HOST _ _ < <(scripts_inventory_connection "${ROOT}")
fi
if [[ -z "${HOST}" ]]; then
  echo "error: DEPLOY_HOST not set and ansible/inventory.ini missing" >&2
  exit 1
fi

EXPECT_CN="mail.example.com"
fail=0

check_tcp() {
  local port="$1" name="$2"
  if timeout 10 bash -c "cat < /dev/null > /dev/tcp/${HOST}/${port}" 2>/dev/null; then
    echo "smoke: ${name} (${HOST}:${port}) reachable"
  else
    echo "error: ${name} (${HOST}:${port}) NOT reachable" >&2
    fail=1
  fi
}

check_tls() {
  local port="$1" name="$2"
  local out
  out="$(echo | timeout 15 openssl s_client -connect "${HOST}:${port}" -servername "${EXPECT_CN}" 2>/dev/null || true)"
  if echo "${out}" | grep -q "Verify return code: 0 (ok)"; then
    echo "smoke: ${name} TLS verify ok"
  else
    echo "error: ${name} TLS verify failed on ${HOST}:${port}" >&2
    fail=1
  fi
}

check_tcp 25 "smtp"
check_tcp 443 "https"
check_tcp 465 "smtps"
check_tcp 995 "pop3s"
check_tls 443 "https"
check_tls 465 "smtps"
check_tls 995 "pop3s"

if [[ "${fail}" -ne 0 ]]; then
  echo "smoke: FAILED" >&2
  exit 1
fi
echo "smoke: ok (25/443/465/995 reachable, TLS valid)"
