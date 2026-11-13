variable "hostname" {
  type        = string
  description = "OpenStack resource name prefix and VM hostname (terraform.tfvars)."
  default     = "mail"
}

variable "sel_account_id" {
  type        = string
  description = "Selectel account ID (leave empty for a generic OpenStack cloud)."
  default     = ""
}

variable "sel_project_id" {
  type        = string
  description = "ID of your OpenStack/Selectel project."
}

variable "sel_username" {
  type        = string
  description = "Selectel service user name (leave empty for a generic OpenStack cloud)."
  default     = ""
}

variable "sel_user_id" {
  type        = string
  description = "Selectel service user ID (leave empty for a generic OpenStack cloud)."
  default     = ""
}

variable "sel_password" {
  type      = string
  sensitive = true
}

variable "region" {
  type    = string
  default = "ru-3"
}

variable "auth_url" {
  type        = string
  description = "Keystone v3 endpoint of your cloud."
  default     = "https://cloud.api.selcloud.ru/identity/v3"
}

variable "az" {
  type    = string
  default = "ru-3b"
}

variable "ssh_port" {
  type        = number
  description = "SSH port on the VM and in the security group."
  default     = 666
}

variable "flavor_id" {
  type        = string
  description = "Compute flavor ID for the mail VM (2 vCPU / 4 GB is enough for 500+ mailboxes)."
  default     = "1054"
}

variable "image_name" {
  type        = string
  description = "Boot image name in the cloud."
  default     = "Debian 13 (Trixie) 64-bit"
}

variable "volume_type" {
  type        = string
  description = "Block storage volume type."
  default     = "universal2.ru-3b"
}

variable "disk_size_gb" {
  type    = number
  default = 100

  validation {
    condition     = var.disk_size_gb >= 100
    error_message = "Boot volume size cannot decrease below 100 GB (shrink forces replace and data loss)."
  }
}

variable "disk_iops" {
  type    = string
  default = "2000"
}

variable "dns_nameservers" {
  type        = list(string)
  default     = ["1.1.1.1", "9.9.9.9"]
  description = "DNS resolvers for the private subnet (IPv4)."
}
