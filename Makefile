test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src/hks

coverage:
	uv run pytest --cov=src/hks --cov-report=term-missing

fixtures:
	uv run python tests/fixtures/build_office.py
