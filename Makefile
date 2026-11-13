# Command contract for CI and local machines
.PHONY: help fmt validate test-quick test-service test-full \
	test-install test-install-ansible deps-gha \
	tf-init tf-plan bootstrap deploy smoke doctor inventory check-maps \
	ci-setup ci-key-install

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
export PYTHONPATH := $(CURDIR)$(if $(PYTHONPATH),:$(PYTHONPATH),)

help:
	@echo "Quality and tests:"
	@echo "  make fmt               terraform fmt -check"
	@echo "  make validate          terraform init -backend=false && validate"
	@echo "  make test-quick        unit tests"
	@echo "  make test-service      service layer (ansible, terraform, shellcheck)"
	@echo "  make test-full         test-quick + test-service"
	@echo "  make verify-ansible    ansible syntax-check + handler notify contracts"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make tf-init           terraform init (local state)"
	@echo "  make tf-plan           terraform plan (requires terraform.tfvars)"
	@echo "  make bootstrap         lab: key, tfvars, apply, inventory, playbook"
	@echo "  make inventory         write ansible/inventory.ini from terraform output"
	@echo ""
	@echo "Operations:"
	@echo "  make deploy            ansible-playbook (code only; keeps server .env)"
	@echo "  make smoke             post-deploy ports + TLS (HOST=<ip>)"
	@echo "  make doctor            diagnostic bundle from the server"
	@echo "  make check-maps        diff rendered maps against deployed files"
	@echo ""
	@echo "One-time CI bootstrap (operator-run):"
	@echo "  make ci-setup          mint keys/ci_deploy (never overwrites)"
	@echo "  make ci-key-install    append CI pubkey on the VM (ansible)"

fmt:
	terraform -chdir=terraform fmt -check -recursive

validate:
	terraform -chdir=terraform init -backend=false -input=false -reconfigure
	terraform -chdir=terraform validate

test-install:
	$(PYTHON) -m pip install -q "pytest>=8.0,<10" "PyYAML>=6.0" "Jinja2>=3.1"

test-install-ansible: test-install
	$(PYTHON) -m pip install -q "ansible-core>=2.15.13"
	@if [ -f ansible/requirements.yml ]; then \
		ansible-galaxy collection install -r ansible/requirements.yml; \
	fi

test-quick: test-install
	$(PYTHON) -m pytest tests/unit

SHELLCHECK_VERSION ?= 0.11.0

deps-gha:
	@if [ -n "$$GITHUB_ACTIONS" ]; then \
		curl -fsSL "https://github.com/koalaman/shellcheck/releases/download/v$(SHELLCHECK_VERSION)/shellcheck-v$(SHELLCHECK_VERSION).linux.x86_64.tar.xz" \
			| tar -xJ -C /tmp; \
		sudo install -m 0755 "/tmp/shellcheck-v$(SHELLCHECK_VERSION)/shellcheck" /usr/local/bin/shellcheck; \
		shellcheck --version | head -2; \
	fi

test-service: deps-gha test-install-ansible
	$(PYTHON) -m pytest tests/service -m service --tb=short

verify-ansible: test-install-ansible
	$(PYTHON) -m pytest tests/service/test_ansible.py tests/service/test_ansible_handlers.py -m service --tb=short

test-full: test-quick test-service

tf-init:
	scripts/tf-init.sh

tf-plan:
	scripts/tf-plan.sh

bootstrap:
	scripts/bootstrap.sh

inventory:
	$(PYTHON) -m scripts.cli inventory --from-terraform

deploy: test-install-ansible
	@test -f ansible/inventory.ini || { echo "ansible/inventory.ini missing — run make inventory"; exit 1; }
	ansible-playbook -i ansible/inventory.ini ansible/playbook.yml

smoke:
	@test -n "$(HOST)" || { echo "HOST= required (public IP)"; exit 1; }
	$(PYTHON) -m scripts.cli smoke --host "$(HOST)"

doctor:
	$(PYTHON) -m scripts.cli doctor --out .

check-maps:
	$(PYTHON) -m scripts.cli check-maps

ci-setup:
	scripts/ci-keygen.sh
	@echo ""
	@echo "Next steps (manual, non-delegable):"
	@echo "  1. make ci-key-install    # SSH to the VM; append CI pubkey"
	@echo "  2. make inventory         # write ansible/inventory.ini from terraform output"
	@echo "CI key is separate from keys/deploy.pub (operator); revoke by removing ci_deploy.pub on the VM."

ci-key-install: test-install-ansible
	@test -f keys/ci_deploy.pub || { echo "run make ci-setup first"; exit 1; }
	ansible-playbook -i ansible/inventory.ini ansible/ci-key.yml
