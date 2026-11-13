#!/usr/bin/env bash
# Lab bootstrap: key → tfvars → apply → inventory → playbook.
# Idempotent: never overwrites keys/deploy.pub or terraform/terraform.tfvars.
set -euo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "$0")/_lib.sh"
ROOT="$(scripts_repo_root)"
cd "${ROOT}"

if [[ ! -f keys/deploy.pub ]]; then
  echo "error: keys/deploy.pub missing (operator public key)" >&2
  exit 1
fi

if [[ ! -f terraform/terraform.tfvars ]]; then
  echo "bootstrap: terraform/terraform.tfvars missing"
  echo "  copy terraform/examples/selectel.tfvars.example → terraform/terraform.tfvars and fill it in"
  exit 1
fi

echo "bootstrap: terraform init + apply"
terraform -chdir=terraform init -input=false
terraform -chdir=terraform apply -input=false -auto-approve

echo "bootstrap: inventory"
python3 -m scripts.cli inventory --from-terraform

echo "bootstrap: ansible"
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml

echo "bootstrap: done — run 'make smoke HOST=<public-ip>'"
