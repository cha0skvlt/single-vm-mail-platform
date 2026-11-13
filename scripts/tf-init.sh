#!/usr/bin/env bash
# Terraform init against the remote S3 backend.
# Loads terraform/s3-backend.env (AWS_* creds) if present.
set -euo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "$0")/_lib.sh"
ROOT="$(scripts_repo_root)"
cd "${ROOT}/terraform"

scripts_load_s3_backend_env "${ROOT}"
if [[ -z "${AWS_ACCESS_KEY_ID:-}" ]]; then
  echo "error: S3 creds not found."
  echo "  copy terraform/s3-backend.env.example → terraform/s3-backend.env and fill in AWS_*"
  exit 1
fi

terraform init "$@"
