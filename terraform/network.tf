resource "openstack_networking_network_v2" "private" {
  name           = "${var.hostname}-net"
  admin_state_up = true
}

resource "openstack_networking_subnet_v2" "private" {
  name            = "${var.hostname}-subnet"
  network_id      = openstack_networking_network_v2.private.id
  cidr            = "192.168.0.0/24"
  ip_version      = 4
  dns_nameservers = var.dns_nameservers
}

data "openstack_networking_network_v2" "external" {
  external = true
}

resource "openstack_networking_router_v2" "router" {
  name                = "${var.hostname}-router"
  admin_state_up      = true
  external_network_id = data.openstack_networking_network_v2.external.id

  lifecycle {
    prevent_destroy = true
  }
}

resource "openstack_networking_router_interface_v2" "router_iface" {
  router_id = openstack_networking_router_v2.router.id
  subnet_id = openstack_networking_subnet_v2.private.id
}

resource "openstack_networking_secgroup_v2" "mail" {
  name        = "${var.hostname}-sg"
  description = "ingress: ssh ${var.ssh_port}, smtp 25, smtps 465, pop3s 995, https 443"
}

# Public mail + ssh + panel HTTPS. No :80 (bring your own wildcard cert, no ACME).
locals {
  public_tcp_ports = [var.ssh_port, 25, 443, 465, 995]
}

resource "openstack_networking_secgroup_rule_v2" "public" {
  for_each          = toset([for p in local.public_tcp_ports : tostring(p)])
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = tonumber(each.value)
  port_range_max    = tonumber(each.value)
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = openstack_networking_secgroup_v2.mail.id
}

resource "openstack_networking_port_v2" "mail" {
  name               = "${var.hostname}-port"
  network_id         = openstack_networking_network_v2.private.id
  security_group_ids = [openstack_networking_secgroup_v2.mail.id]

  fixed_ip {
    subnet_id = openstack_networking_subnet_v2.private.id
  }
}

resource "openstack_networking_floatingip_v2" "mail" {
  pool = data.openstack_networking_network_v2.external.name

  lifecycle {
    prevent_destroy = true
  }
}

resource "openstack_networking_floatingip_associate_v2" "mail" {
  floating_ip = openstack_networking_floatingip_v2.mail.address
  port_id     = openstack_networking_port_v2.mail.id

  depends_on = [
    openstack_networking_floatingip_v2.mail,
    openstack_networking_port_v2.mail,
    openstack_networking_router_interface_v2.router_iface,
  ]
}
