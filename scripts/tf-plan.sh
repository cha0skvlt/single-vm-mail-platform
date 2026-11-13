#!/usr/bin/env bash
# Terraform plan for CI/local (skips when SEL_* secrets are absent).
set -euo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "$0")/_lib.sh"
ROOT="$(scripts_repo_root)"
cd "${ROOT}/terraform"

# Skip when no credentials available: neither env var (CI) nor local tfvars file.
if [[ -z "${TF_VAR_sel_password:-}" ]] && [[ ! -f terraform.tfvars ]]; then
  echo "terraform plan skipped: TF_VAR_sel_password not set and terraform.tfvars not found"
  exit 0
fi

scripts_load_s3_backend_env "${ROOT}"

# TF_VAR_hostname from terraform.tfvars when not exported (CI sets it in workflow).
if [[ -z "${TF_VAR_hostname:-}" ]]; then
  TF_VAR_hostname="$(scripts_tfvars_hostname "${ROOT}")"
  if [[ -n "${TF_VAR_hostname}" ]]; then
    export TF_VAR_hostname
  fi
fi
if [[ -z "${TF_VAR_hostname:-}" ]]; then
  echo "error: TF_VAR_hostname not set (add hostname = \"...\" to terraform/terraform.tfvars or export TF_VAR_hostname)" >&2
  exit 1
fi

terraform init -input=false
terraform plan -no-color -input=false | tee plan.txt
