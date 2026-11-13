# OpenStack

The template targets any OpenStack cloud. Selectel is the documented example
because it is what the reference deployment runs on.

## Providers

`terraform/versions.tf` requires two providers:

| Provider | Why |
| --- | --- |
| `selectel/selectel` | keypair registration (`selectel_vpc_keypair_v2`) |
| `openstack/openstack` | network, subnet, router, SG, port, floating IP, volume, VM |

The `selectel` provider block is harmless on a generic cloud: leave `sel_account_id`,
`sel_username` and `sel_user_id` empty and point `auth_url` at your Keystone.

## Selectel

```hcl
sel_account_id = "000000000000"
sel_project_id = "00000000000000000000000000000000"
sel_username   = "service-user"
sel_user_id    = "00000000000000000000000000000000"
sel_password   = "changeme"

auth_url = "https://cloud.api.selcloud.ru/identity/v3"
region   = "ru-3"
az       = "ru-3b"

dns_nameservers = ["188.93.16.19", "188.93.17.19"]
flavor_id       = "1054"
volume_type     = "universal2.ru-3b"
```

Notes:

- Port **25** may be filtered on a new project. Open it with a support ticket.
- The Grafana apt CDN can return 403 from some regions; the role downloads a pinned
  `.deb` on the controller and installs it on the host.
- Enable a snapshot schedule on the boot volume after the first apply. Undownloaded
  POP mail is the only copy until a client retrieves it.

## Generic OpenStack

```hcl
sel_account_id = ""
sel_project_id = "your-project-id"
sel_username   = ""
sel_user_id    = ""
sel_password   = "changeme"

auth_url = "https://keystone.example.com:5000/v3"
region   = "RegionOne"
az       = "nova"

dns_nameservers = ["1.1.1.1", "9.9.9.9"]
flavor_id       = "your-flavor-id"
volume_type     = "your-volume-type"
```

The `selectel_vpc_keypair_v2` resource still runs. On a cloud without the Selectel
API, replace it with `openstack_compute_keypair_v2` in `terraform/compute.tf`:

```hcl
resource "openstack_compute_keypair_v2" "mail" {
  name       = "${var.hostname}-key"
  public_key = local.deploy_ssh_public_key
}
```

and point `key_pair` at `openstack_compute_keypair_v2.mail.name`.

## Remote state

Local state is the default. For shared state:

```bash
cp terraform/backend.s3.hcl.example terraform/backend.s3.hcl
$EDITOR terraform/backend.s3.hcl
terraform -chdir=terraform init -backend-config=backend.s3.hcl
```

`backend.s3.hcl` is gitignored. Credentials come from `terraform/s3-backend.env`
(gitignored) or the environment.

## Sizing

| Mailboxes | vCPU | RAM | Boot volume |
| --- | --- | --- | --- |
| up to 100 | 2 | 4 GB | 100 GB |
| 500+ | 4 | 8 GB | 100 GB |
| 1000+ | 4–8 | 16 GB | 200 GB |

Maildir on the boot volume is the constraint, not CPU. `disk_size_gb` cannot shrink
below 100 GB by validation.
