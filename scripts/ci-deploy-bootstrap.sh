#!/usr/bin/env bash
# CI — materialize inventory + secret files from GitHub Actions env (no stdout secrets).
# Secrets are injected as env vars; files here are gitignored and never committed.
set -euo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "$0")/_lib.sh"
ROOT="$(scripts_repo_root)"
cd "${ROOT}"
umask 077

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_KNOWN_HOSTS:?DEPLOY_KNOWN_HOSTS is required}"

# 1) known_hosts
mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
printf '%s\n' "${DEPLOY_KNOWN_HOSTS}" | sed 's/\r$//' > "${HOME}/.ssh/known_hosts"
chmod 600 "${HOME}/.ssh/known_hosts"

# 2) ansible inventory (group name = hostname = mail)
mkdir -p ansible
cat > ansible/inventory.ini <<EOF
[mail]
vm ansible_host=${DEPLOY_HOST} ansible_user=deploy ansible_port=666
EOF
chmod 600 ansible/inventory.ini

write_secret_file() {
  local dest="$1" content="$2"
  printf '%s' "${content}" | sed 's/\r$//' > "${dest}"
  # PEM/CSV parsers require a trailing newline; GitHub secrets often omit it.
  if [[ -s "${dest}" && "$(tail -c 1 "${dest}" | wc -l)" -eq 0 ]]; then
    printf '\n' >> "${dest}"
  fi
  chmod 600 "${dest}"
}

# 3) accounts CSV (plaintext passwords) — consumed by role mail
if [[ -n "${MAIL_USERS_CSV:-}" ]]; then
  mkdir -p data
  write_secret_file data/mail_users.csv "${MAIL_USERS_CSV}"
fi

# 4) TLS cert + key — consumed by role mail
mkdir -p ssl
if [[ -n "${MAIL_TLS_CERT:-}" ]]; then
  write_secret_file ssl/fullchain.pem "${MAIL_TLS_CERT}"
fi
if [[ -n "${MAIL_TLS_KEY:-}" ]]; then
  write_secret_file ssl/privkey.pem "${MAIL_TLS_KEY}"
fi

# 5) DKIM private key — consumed by role dkim
if [[ -n "${MAIL_DKIM_PRIVATE:-}" ]]; then
  mkdir -p dkim
  write_secret_file "dkim/${DKIM_SELECTOR:-mail}.private" "${MAIL_DKIM_PRIVATE}"
fi

echo "bootstrap: wrote inventory + secret files for ${DEPLOY_HOST}"
