# Contributing

This repository is a source-available portfolio sample under [PolyForm Shield 1.0.0](LICENSE). Issues and PRs that fix sanitization leaks, tests, or docs are welcome. The project ships as a reference sample.

```bash
make test-full
make fmt
make validate
```

Keep `panel/.env`, `terraform/terraform.tfvars`, `terraform/s3-backend.env`, state files, PEMs, DKIM private keys, `ansible/inventory.ini`, and client domains out of git. A sanitization sweep keeps the tree clean: `bioline`, `biomail`, `bioprod`, production IPs — the documented Selectel example under `terraform/examples/` is the exception.

Mail-specific rules:

- `dkim/*.private`, `ssl/`, `data/*.csv`, and `.panel-creds` never enter the tree.
- Every domain in code, templates, and tests is `example.com`; every address is RFC 5737 (`203.0.113.0/24`, `198.51.100.0/24`, `192.0.2.0/24`).
- The panel reads its domain from `MAIL_DOMAIN`; no template hardcodes a hostname.
