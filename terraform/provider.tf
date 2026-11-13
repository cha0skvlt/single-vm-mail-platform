provider "selectel" {
  domain_name = var.sel_account_id
  username    = var.sel_username
  password    = var.sel_password
  auth_region = var.region
  auth_url    = var.auth_url
}

provider "openstack" {
  auth_url    = var.auth_url
  domain_name = var.sel_account_id
  tenant_id   = var.sel_project_id
  user_name   = var.sel_username
  password    = var.sel_password
  region      = var.region
}
