#!/usr/bin/env bash
# Shared helpers for scripts/*.sh — source: source "$(dirname "$0")/_lib.sh"

scripts_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${script_dir}/.." && pwd
}

scripts_load_s3_backend_env() {
  local root="${1:-$(scripts_repo_root)}"
  local s3_env="${root}/terraform/s3-backend.env"
  if [[ -f "${s3_env}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${s3_env}"
    set +a
  fi
}

# Read hostname from terraform/terraform.tfvars (fallback for local tf-plan).
scripts_tfvars_hostname() {
  local root="${1:-$(scripts_repo_root)}"
  local tfvars="${root}/terraform/terraform.tfvars"
  if [[ -f "${tfvars}" ]]; then
    sed -n 's/^[[:space:]]*hostname[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "${tfvars}" | head -1
  fi
}

# Parse "vm ansible_host=IP ... ansible_port=PORT ... ansible_user=USER" from inventory.ini
# Prints: HOST PORT USER
scripts_inventory_connection() {
  local root="${1:-$(scripts_repo_root)}"
  local inv="${root}/ansible/inventory.ini"
  local host port user
  host="$(sed -n 's/.*ansible_host=\([^ ]*\).*/\1/p' "${inv}" | head -1)"
  port="$(sed -n 's/.*ansible_port=\([^ ]*\).*/\1/p' "${inv}" | head -1)"
  user="$(sed -n 's/.*ansible_user=\([^ ]*\).*/\1/p' "${inv}" | head -1)"
  echo "${host} ${port:-666} ${user:-deploy}"
}
