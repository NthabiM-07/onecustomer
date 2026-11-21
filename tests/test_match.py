import numpy as np
import pandas as pd
import pytest

from onecustomer.evaluate import pairwise
from onecustomer.generate import snapshot
from onecustomer.match import FIELDS, LEVELS, cluster, compare_rows, fit_em, link
from onecustomer.standardise import standardise

# COMPARE_COLUMNS: nid, dob, first, first_canon, middle, surname, phone, email, address, postal
BASE = ("9902205312083", "1999-02-20", "TSHEPO", "TSHEPO", None, "ISAACS", "0720147841", None,
        "312 ACACIA ROAD", "2068")


def with_(**changes):
    names = ["nid", "dob", "first", "canon", "middle", "surname", "phone", "email", "address", "postal"]
    row = dict(zip(names, BASE, strict=True))
    row.update(changes)
    return tuple(row[n] for n in names)


def test_identical_rows_agree_on_every_present_field():
    assert compare_rows(BASE, BASE) == (3, 3, 3, 3, 2, 0, 3)


def test_graded_levels():
    gamma = compare_rows(BASE, with_(nid="9902205312038", dob="1999-20-02", first="TSHEPI", canon="TSHEPI",
                                     surname="ISAAKS", phone=None, address="312 ACACIA ROAD", postal="2069"))
    assert gamma == (2, 2, 2, 2, 0, 0, 2)


def test_first_name_matching_middle_name_is_partial_agreement():
    a = with_(first="THABO", canon="THABO", middle="KAGISO")
    b = with_(first="KAGISO", canon="KAGISO", middle=None)
    assert compare_rows(a, b)[FIELDS.index("first")] == 2


def test_cannot_link_blocks_chaining_between_two_ids():
    # 0 -- 1 -- 2, where 0 and 2 hold different trusted IDs; the weaker link must lose.
    a, b, w = np.array([0, 1]), np.array([1, 2]), np.array([10.0, 5.0])
    labels = cluster(3, a, b, w, np.array(["ID-A", None, "ID-B"], dtype=object))
    assert labels[0] == labels[1] != labels[2]
    unconstrained = cluster(3, a, b, w)
    assert len(set(unconstrained)) == 1


def test_em_recovers_m_with_known_u():
    rng = np.random.default_rng(1)
    true_m = {f: np.r_[0, np.linspace(0.1, 1, LEVELS[f]) ** 2] for f in FIELDS}
    true_u = {f: np.r_[0, np.linspace(1, 0.1, LEVELS[f]) ** 2] for f in FIELDS}
    for d in (true_m, true_u):
        for f in FIELDS:
            d[f][1:] /= d[f][1:].sum()
    n, prior = 40_000, 0.3
    is_match = rng.random(n) < prior
    gamma = np.zeros((n, len(FIELDS)), dtype=np.int8)
    for k, f in enumerate(FIELDS):
        levels = np.arange(1, LEVELS[f] + 1)
        gamma[is_match, k] = rng.choice(levels, size=is_match.sum(), p=true_m[f][1:])
        gamma[~is_match, k] = rng.choice(levels, size=(~is_match).sum(), p=true_u[f][1:])
    model = fit_em(gamma, true_u)
    assert model.prior == pytest.approx(prior, abs=0.02)
    for f in FIELDS:
        assert np.allclose(model.m[f][1:], true_m[f][1:], atol=0.03)


def test_strategies_order_as_expected_on_a_small_world(small_world):
    final = snapshot(standardise(small_world.versions), 24)
    truth = final["record_key"].map(small_world.links.set_index("record_key")["person_id"]).to_numpy()
    scores = {s: pairwise(link(final, s).labels, truth) for s in ("id_exact", "rules", "fellegi_sunter")}
    assert scores["id_exact"]["precision"] == 1.0
    assert scores["fellegi_sunter"]["recall"] > scores["id_exact"]["recall"] + 0.1
    assert scores["fellegi_sunter"]["precision"] > scores["rules"]["precision"]
    assert scores["fellegi_sunter"]["f1"] > 0.98


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError):
        link(pd.DataFrame(), "magic")


def test_swapped_names_are_partial_agreement():
    a = with_(first="LUKE", canon="LUKE", surname="GAZZOLA")
    b = with_(first="GAZZOLA", canon="GAZZOLA", surname="LUKE")
    gamma = compare_rows(a, b)
    assert gamma[FIELDS.index("first")] == 2 and gamma[FIELDS.index("surname")] == 2


def test_identity_guard():
    from onecustomer.match import identity_ok

    col = {f: k for k, f in enumerate(FIELDS)}

    def g(**levels):
        row = np.zeros(len(FIELDS), dtype=np.int8)
        for f, v in levels.items():
            row[col[f]] = v
        return row[None, :]

    assert identity_ok(g(nid=3, first=1, dob=1))[0]  # the ID alone is enough
    assert identity_ok(g(first=3, dob=3))[0]  # name and birth date
    assert identity_ok(g(first=2, dob=0))[0]  # birth date missing on one side
    assert not identity_ok(g(first=3, dob=1, surname=3, phone=2, address=3))[0]  # father and son
    assert not identity_ok(g(first=1, dob=3, surname=3, phone=2, address=3))[0]  # twins without IDs


def test_term_frequency_adjustment_rewards_rare_names(small_world):
    from onecustomer.match import pair_values, train

    final = snapshot(standardise(small_world.versions), 24)
    model = train(final)
    freq = model.tf["surname"]
    common, rare = max(freq, key=freq.get), min(freq, key=freq.get)
    gamma = np.zeros((2, len(FIELDS)), dtype=np.int8)
    gamma[:, FIELDS.index("surname")] = 3
    values = {"surname": np.array([common, rare], dtype=object),
              "first": np.array([None, None], dtype=object)}
    adj = model.tf_adjustment(gamma, values)["surname"]
    assert adj[0] < 0 < adj[1]
    assert set(pair_values(final, pd.DataFrame({"a": [0], "b": [1]}))) == {"surname", "first"}
