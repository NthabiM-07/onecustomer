import numpy as np
import pandas as pd

from onecustomer.duck import DuckDBEngine
from onecustomer.generate import snapshot
from onecustomer.match import ComparisonCache, link
from onecustomer.standardise import standardise


def test_duckdb_matches_the_python_reference_exactly(small_world):
    """Same candidate pairs, same comparison vectors, same parties: the engines differ only in speed."""
    snap = snapshot(standardise(small_world.versions), 24)
    py, duck = ComparisonCache(), DuckDBEngine()
    pairs = py.pairs(snap)
    pd.testing.assert_frame_equal(pairs, duck.pairs(snap))
    assert np.array_equal(py.compare(snap, pairs), duck.compare(snap, pairs))
    rng = np.random.default_rng(0)
    n = len(snap)
    random_pairs = pd.DataFrame({"a": rng.integers(0, n, 5000), "b": rng.integers(0, n, 5000)})
    assert np.array_equal(py.compare(snap, random_pairs), duck.compare(snap, random_pairs))
    assert np.array_equal(link(snap, "fellegi_sunter", cache=py).labels,
                          link(snap, "fellegi_sunter", cache=DuckDBEngine()).labels)


def test_duckdb_handles_edge_values():
    rows = pd.DataFrame({
        "record_key": ["A", "B", "C", "D"],
        "load_month": [1, 1, 1, 1],
        "first_name": ["Luke", "GAZZOLA", None, "Lebo"],
        "middle_name": [None, None, None, None],
        "surname": ["Gazzola", "Luke", "Dlamini-Nkosi", "DLAMINI"],
        "national_id": [None, "123", "123", None],
        "dob": ["1990-01-02", "1990-02-01", None, "1990-01-02"],
        "phone": [None, None, None, None],
        "email": [None, None, None, None],
        "address_line": ["1 Main Rd", None, "1 MAIN ROAD", "1 Main Road"],
        "postal_code": [None, None, None, "2000"],
    })
    snap = standardise(rows, id_scheme="none")
    pairs = pd.DataFrame({"a": [0, 0, 1, 2, 0], "b": [1, 2, 2, 3, 3]})
    assert np.array_equal(ComparisonCache().compare(snap, pairs), DuckDBEngine().compare(snap, pairs))
