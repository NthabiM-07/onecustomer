.PHONY: install data run experiment benchmark scale demo test lint clean

install:
	pip install -e ".[dev,bench]"

data:
	onecustomer generate --people 10000 --seed 7

run:
	onecustomer run

experiment:
	onecustomer experiment

benchmark:
	onecustomer benchmark

scale:
	onecustomer scale

demo: data run
	onecustomer audit
	onecustomer lookup LN0006169
	onecustomer lookup PTY00001005 --as-of 2024-06
	onecustomer explain LN0002442 LN0004420
	onecustomer review-queue
	onecustomer replay --month 12

test:
	pytest

lint:
	ruff check src tests

clean:
	rm -rf data .pytest_cache
