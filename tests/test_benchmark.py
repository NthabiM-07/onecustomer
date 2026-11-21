import pytest

recordlinkage = pytest.importorskip("recordlinkage")


def test_febrl4_regression():
    """Public data the repository did not generate: guard the published FEBRL4 figures."""
    from onecustomer import febrl

    records, truth = febrl.load()
    assert len(records) == 10_000
    result = febrl.run_onecustomer(records, truth)
    main = next(r for r in result["rows"] if r["system"] == "onecustomer" and r["threshold"] == 0.9)
    assert main["precision"] >= 0.999
    assert main["recall"] >= 0.98
    assert result["pair_completeness"] >= 0.99
