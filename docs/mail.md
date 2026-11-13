# Mail

Postfix, Dovecot, OpenDKIM and the maps that connect them to the panel database.

## Ports

| Port | Service | Notes |
| --- | --- | --- |
| 25 | SMTP inbound | RBL + cidr blacklist after auth checks |
| 465 | SMTPS submission | implicit TLS, SASL required, RBL does not apply |
| 995 | POP3S | implicit TLS |
| 443 | HTTPS | panel + Grafana behind `auth_request` |
| `ssh_port` | SSH | default 666 |

No `:80`, no `:110`, no `:143`, no `:993`.

## Postfix

`ansible/roles/mail/templates/main.cf.j2` and `master.cf.j2`.

- `mydestination = localhost` — every mailbox is virtual.
- `virtual_transport = lmtp:unix:private/dovecot-lmtp` — Dovecot owns delivery.
- `smtpd_relay_restrictions = permit_mynetworks permit_sasl_authenticated reject_unauth_destination`
  — no open relay.
- `message_size_limit = 52428800` (50 MB).
- `smtpd_milters = inet:127.0.0.1:8891` — OpenDKIM only.

### Antispam order

```
permit_mynetworks
permit_sasl_authenticated
reject_unauth_destination
check_client_access cidr:/etc/postfix/client_blacklist
reject_rbl_client zen.spamhaus.org
reject_rbl_client bl.spamcop.net
```

The manual list lives in `ansible/roles/mail/files/client_blacklist` (cidr, no
`postmap`). Prefer a git change and a deploy; an on-host edit is overwritten next run.

## Dovecot

Self-contained `dovecot.conf` — no `conf.d` includes. **Dovecot 2.4 syntax**; 2.3
will not start.

| Item | Value |
| --- | --- |
| Protocols | `pop3` + `lmtp` |
| POP3S | `:995`, `ssl = yes`; plain `:110` disabled |
| Auth | `PLAIN`/`LOGIN`, `auth_allow_cleartext = no`, `ssl = required` |
| passdb/userdb | `/etc/dovecot/users`, `SSHA512` |
| Home | `/var/vmail/<domain>/%{user \| username}`, uid/gid `vmail` (5000) |
| Seen | `pop3_no_flag_updates = no` — RETR marks `\Seen` |

Clients log in as `user` or `user@example.com`; both keys exist in the passwd-file.

## Maps

Source of truth is SQLite `/var/lib/mailpanel/users.db` (hashes only). The sync
script rewrites three files atomically and runs `postmap`:

| File | Content |
| --- | --- |
| `/etc/dovecot/users` | `email:hash::::::` and `local:hash::::::` |
| `/etc/postfix/vmailbox` | `email<TAB>domain/local/Maildir/` |
| `/etc/postfix/virtual` | `postmaster@domain` only |
| `/etc/postfix/virtual_redirect` | `src@domain<TAB>src@domain, dest@domain, …` |

`ops check-maps` renders the same maps from a local database copy and diffs them
against the deployed files — the CI-safe way to catch drift.

## Accounts

| Action | Path |
| --- | --- |
| First import | CSV, only when the database is empty (`INSERT OR IGNORE`) |
| Later imports | `IMPORT_MISSING=1` inserts locals missing from SQLite |
| Create / reset / delete | Panel UI or `POST /api/users…` → `doveadm pw -s SSHA512` → sync |

CSV columns: `username,email,full_name,password,archived`. The last column is legacy
import metadata and does not disable a mailbox.

Never delete `users.db` or `/etc/dovecot/users` on a live host to "refresh" from CSV —
the import is empty-database only. Use the panel.

## Retention

`mail-cleanup.timer` runs daily with a randomized delay:

```bash
doveadm expunge -A mailbox INBOX SEEN savedbefore 30d
```

Only downloaded (`\Seen`) mail is expunged. Undownloaded mail is never touched, which
is why the boot volume is the only copy until a client retrieves it.

## Autoreplies

Per-mailbox vacation messages with a date window. `mail-autoreply-sync.sh` writes a
Sieve script into the user's home; `mail-autoreply-expire.timer` clears expired
windows hourly. Managed from the panel.

## Redirects

Per-mailbox forwarding, stored in SQLite and rendered into `virtual_redirect`.
A redirect keeps the original address in the destination list, so mail is both
delivered and forwarded.

## OpenDKIM

| Item | Value |
| --- | --- |
| Selector | `mail` (override `DKIM_SELECTOR`) |
| Socket | `inet:8891@127.0.0.1` |
| Key | `dkim/mail.private` → `/etc/opendkim/keys/<domain>/mail.private` |
| Signs | authenticated submissions on 465 (`{auth_type}` macro) |

Generate once:

```bash
opendkim-genkey -b 2048 -d example.com -s mail -D dkim/
```

Publish `dkim/mail.txt` as `mail._domainkey` TXT. `ops dkim-check` verifies the record
name, `v=DKIM1` and the `p=` value against the configured domain.

## DNS

| Record | Value |
| --- | --- |
| `A mail.example.com` | floating IP |
| `PTR` | floating IP → `mail.example.com` (must match the A record) |
| `SPF` | `v=spf1 ip4:<floating-ip> ~all` |
| `DKIM` | `mail._domainkey` TXT |
| `MX` | `mail.example.com` |

## Optional external milter

Any content filter can be prepended to `smtpd_milters` in `main.cf.j2`. Set
`ess_milter_host` in `ansible/group_vars/all.yml` and open the port in
`terraform/network.tf`. Empty by default — OpenDKIM alone is the shipped configuration.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Client cannot connect | DNS points at the floating IP; port 995 open; implicit TLS |
| Login rejected | Panel password, not the old server's; `user` or `user@example.com` |
| Outbound stuck | `sudo postsuper -r ALL && sudo postqueue -f` |
| Mail deferred to one MX | Remote MX is down; deferred is correct, do not flush blindly |
| Panel 429 | 5 failed logins / 300 s per IP; wait or clear the fail2ban ban |
