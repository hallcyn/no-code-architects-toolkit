.PHONY: up down logs smoke lint test validate-config check

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f nca-toolkit

smoke:
	./scripts/smoke-test.sh

lint:
	ruff check .
	ruff format --check .
	yamllint .github docker-compose.yml .yamllint.yml
	shellcheck entrypoint.sh scripts/smoke-test.sh

test:
	python -m pytest

validate-config:
	python -m json.tool railway.json >/dev/null
	docker compose config --quiet
	docker build --check .

check: lint test validate-config
