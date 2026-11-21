.PHONY: install data run experiment demo test lint clean

install:
	pip install -e ".[dev]"

data:
	onecustomer generate --people 10000 --seed 7

run:
	onecustomer run

experiment:
	onecustomer experiment

demo: data run
	onecustomer audit
	onecustomer lookup LN0000505
	onecustomer lookup LN0000505 --as-of 2024-06
	onecustomer replay --month 12

test:
	pytest

lint:
	ruff check src tests

clean:
	rm -rf data .pytest_cache
