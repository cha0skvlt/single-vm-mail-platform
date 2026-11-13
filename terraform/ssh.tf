# single source of truth for deploy public key — keys/deploy.pub (in git).
locals {
  deploy_ssh_public_key = trimspace(file("${path.module}/../keys/deploy.pub"))
}
