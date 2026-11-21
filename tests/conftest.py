from __future__ import annotations

import pytest

from onecustomer import pipeline
from onecustomer.generate import generate


@pytest.fixture(scope="session")
def small_world():
    return generate(600, seed=3)


@pytest.fixture(scope="session")
def small_run(small_world):
    return pipeline.run(small_world, months=12)
