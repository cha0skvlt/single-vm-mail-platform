terraform {
  required_version = ">= 1.10"
  required_providers {
    selectel = {
      source  = "selectel/selectel"
      version = "~> 7.1"
    }
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "2.1.0"
    }
  }
}
