.PHONY: test lint check

test:
	python -m unittest discover -s tests

lint:
	ruff check .

check: lint test
