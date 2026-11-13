output "public_ip_address" {
  description = "Public IPv4 (floating IP)"
  value       = openstack_networking_floatingip_v2.mail.address
}

output "hostname" {
  description = "VM hostname (also the OpenStack resource prefix)"
  value       = var.hostname
}

output "ssh_port" {
  description = "SSH port"
  value       = var.ssh_port
}
