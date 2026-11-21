import numpy as np
import pandas as pd
import pytest

from onecustomer.evaluate import b_cubed, cluster_exact, pair_completeness, pairwise


def test_b_cubed_worked_example():
    # predicted {0,1,2},{3}; truth {0,1},{2,3}
    labels, truth = np.array([0, 0, 0, 1]), np.array([0, 0, 1, 1])
    b3 = b_cubed(labels, truth)
    assert b3["b3_precision"] == pytest.approx((2 / 3 + 2 / 3 + 1 / 3 + 1) / 4)
    assert b3["b3_recall"] == pytest.approx((1 + 1 + 0.5 + 0.5) / 4)
    assert cluster_exact(labels, truth) == {"cluster_precision": 0.0, "cluster_recall": 0.0}


def test_perfect_clustering_scores_one_everywhere():
    truth = np.array([5, 5, 7, 8, 8, 8])
    labels = np.array([1, 1, 2, 3, 3, 3])
    assert pairwise(labels, truth)["f1"] == 1.0
    assert b_cubed(labels, truth)["b3_f1"] == 1.0
    assert cluster_exact(labels, truth) == {"cluster_precision": 1.0, "cluster_recall": 1.0}


def test_pair_completeness():
    truth = np.array([1, 1, 2, 2, 3])
    assert pair_completeness(np.array([0]), np.array([1]), truth) == 0.5
    assert pair_completeness(np.array([0, 2]), np.array([1, 3]), truth) == 1.0


def test_matcher_never_sees_ground_truth(small_world):
    """Leakage audit: the source extract carries no person, household or truth columns."""
    forbidden = {"person_id", "household_id", "twin_of", "junior_of", "gender"}
    assert not forbidden & set(small_world.versions.columns)
    # Record keys are issued in onboarding order per system, not by person.
    keys = small_world.links.sort_values("record_key")
    assert not keys["person_id"].is_monotonic_increasing
    assert isinstance(small_world.versions, pd.DataFrame)
