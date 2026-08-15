.PHONY: up down logs smoke storage-smoke runtime-contract check-upstream lint test validate-config check

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f nca-toolkit

smoke:
	./scripts/smoke-test.sh

storage-smoke:
	./scripts/storage-smoke-test.sh

runtime-contract:
	./scripts/runtime-contract.sh

check-upstream:
	python scripts/check_upstream_update.py --dry-run

lint:
	ruff check .
	ruff format --check .
	yamllint .github docker-compose.yml docker-compose.runtime.yml .yamllint.yml
	shellcheck entrypoint.sh scripts/runtime-contract.sh scripts/smoke-test.sh scripts/storage-smoke-test.sh

test:
	python -m pytest

validate-config:
	python -m json.tool railway.json >/dev/null
	docker compose config --quiet
	docker compose -f docker-compose.yml -f docker-compose.runtime.yml config --quiet
	docker build --check .

check: lint test validate-config
