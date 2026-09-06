.PHONY: install contracts format lint typecheck test verify dev up down

install:
	python3 -m pip install -e '.[dev]'
	pnpm install

contracts:
	python3 scripts/export_openapi.py
	pnpm --filter @cloudctl/api-contracts build

format:
	ruff format .
	ruff check --fix .
	pnpm --recursive --if-present format

lint:
	ruff format --check .
	ruff check .
	pnpm lint

typecheck:
	pyright
	mypy
	pnpm typecheck

test:
	pytest -q
	pnpm test

verify: lint typecheck test

dev:
	pnpm dev

up:
	docker compose -f infra/compose/docker-compose.yml up -d

down:
	docker compose -f infra/compose/docker-compose.yml down
