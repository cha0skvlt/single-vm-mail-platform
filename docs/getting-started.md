# Getting started

From an empty cloud account to a working mailbox. Roughly 20 minutes plus DNS
propagation.

## Prerequisites

- Terraform `>= 1.10`
- Ansible `>= 2.15` with `ansible-galaxy collection install -r ansible/requirements.yml`
- Python `>= 3.11` (for `make test-quick` and the `ops` CLI)
- An OpenStack or Selectel project with a floating IP pool
- A domain you control, and a wildcard TLS certificate for it
- An SSH keypair for the `deploy` user

## 1. Deploy key

```bash
ssh-keygen -t ed25519 -C "deploy@mail" -f ~/.ssh/mail_deploy
cp ~/.ssh/mail_deploy.pub keys/deploy.pub
```

`keys/deploy.pub` is the single source of truth for the VM keypair and cloud-init.

## 2. Terraform variables

```bash
cp terraform/examples/selectel.tfvars.example terraform/terraform.tfvars
$EDITOR terraform/terraform.tfvars
```

Set `sel_project_id`, `sel_password`, `hostname`, and `dns_nameservers`.
`terraform/terraform.tfvars` is gitignored.

## 3. Apply

```bash
make tf-init
terraform -chdir=terraform apply
```

Human-only step. Read the plan; anything that replaces the boot volume is data loss.

## 4. Inventory

```bash
make inventory          # writes ansible/inventory.ini from terraform output
```

The inventory group name must equal `hostname` from `terraform.tfvars`.

## 5. Secrets on the controller

Materialize the files the roles expect (all gitignored):

| Path | Content |
| --- | --- |
| `ssl/fullchain.pem` | wildcard certificate chain |
| `ssl/privkey.pem` | wildcard private key |
| `dkim/mail.private` | OpenDKIM private key |
| `data/mail_users.csv` | optional first import |

Generate the DKIM key once:

```bash
opendkim-genkey -b 2048 -d example.com -s mail -D dkim/
```

Publish `dkim/mail.txt` as a TXT record and keep `dkim/mail.private` off git.

## 6. Deploy the host

```bash
export MAIL_ADMIN_USER=admin
export MAIL_ADMIN_PASSWORD='...'
export MAIL_SESSION_SECRET="$(openssl rand -hex 32)"
export GRAFANA_ADMIN_PASSWORD='...'
make deploy
```

## 7. DNS

| Record | Value |
| --- | --- |
| `A mail.example.com` | `terraform -chdir=terraform output -raw public_ip_address` |
| `PTR` | same IP → `mail.example.com` (forward-confirmed reverse DNS) |
| `SPF` | `v=spf1 ip4:<floating-ip> ~all` |
| `DKIM` | `mail._domainkey` TXT from `dkim/mail.txt` |
| `MX` | `mail.example.com` |

Some clouds filter port 25 on new projects — open it via a support ticket before
inbound mail from the internet works.

## 8. Verify

```bash
make smoke HOST=<floating-ip>
```

Checks TCP 25/443/465/995 and TLS verification on 443/465/995.

## First mailbox

Open `https://mail.example.com`, log in with `MAIL_ADMIN_USER`, create a mailbox.
The panel writes SQLite and triggers the map sync; no deploy needed.

Test with a POP3S client: host `mail.example.com`, port 995, implicit TLS, login
`user` or `user@example.com`.

## Next

- [`architecture.md`](architecture.md) — how the pieces fit
- [`mail.md`](mail.md) — Postfix/Dovecot/maps/retention/DKIM details
- [`openstack.md`](openstack.md) — Selectel and generic OpenStack specifics
