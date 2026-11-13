data "openstack_images_image_v2" "debian" {
  name        = var.image_name
  most_recent = true
  visibility  = "public"
}

resource "selectel_vpc_keypair_v2" "mail" {
  name       = "${var.hostname}-key"
  public_key = local.deploy_ssh_public_key
  user_id    = var.sel_user_id
}

resource "openstack_blockstorage_volume_v3" "boot" {
  name                 = "${var.hostname}-boot"
  size                 = var.disk_size_gb
  image_id             = data.openstack_images_image_v2.debian.id
  volume_type          = var.volume_type
  availability_zone    = var.az
  enable_online_resize = true

  metadata = {
    total_iops_sec  = var.disk_iops
    total_bytes_sec = "209715200"
  }

  lifecycle {
    ignore_changes  = [image_id]
    prevent_destroy = true
  }
}

resource "openstack_compute_instance_v2" "mail" {
  name              = var.hostname
  flavor_id         = var.flavor_id
  key_pair          = selectel_vpc_keypair_v2.mail.name
  availability_zone = var.az

  network { port = openstack_networking_port_v2.mail.id }

  block_device {
    uuid             = openstack_blockstorage_volume_v3.boot.id
    source_type      = "volume"
    destination_type = "volume"
    boot_index       = 0
  }

  user_data = base64encode(local.cloud_init)

  lifecycle {
    ignore_changes = [
      image_id,
      user_data,
    ]
  }

  vendor_options { ignore_resize_confirmation = true }
}
