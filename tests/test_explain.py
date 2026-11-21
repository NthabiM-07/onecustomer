import pytest

from onecustomer.explain import explain_pair, render, review_queue
from onecustomer.generate import snapshot
from onecustomer.match import train
from onecustomer.standardise import standardise


@pytest.fixture(scope="module")
def snap_and_model(small_world):
    snap = snapshot(standardise(small_world.versions), 24)
    return snap, train(snap)


def test_waterfall_adds_up(snap_and_model, small_world):
    snap, model = snap_and_model
    links = small_world.links
    person = links.groupby("person_id").filter(lambda g: g["system"].nunique() == 2)["person_id"].iloc[0]
    a, b = sorted(links[links["person_id"] == person]["record_key"])[:2]
    e = explain_pair(snap, model, a, b)
    total = e["prior_weight"] + sum(s["weight"] + s["tf_adjustment"] for s in e["steps"])
    assert e["total_weight"] == pytest.approx(total)
    assert e["posterior"] == pytest.approx(1 / (1 + 2 ** -total))
    assert [s["field"] for s in e["steps"]] == ["nid", "dob", "first", "surname", "phone", "email", "address"]
    text = render(e)
    assert "verdict" in text and a in text


def test_unknown_record_is_reported(snap_and_model):
    snap, model = snap_and_model
    with pytest.raises(KeyError):
        explain_pair(snap, model, "LN9999999", snap["record_key"].iloc[0])


def test_review_queue_has_reasons_and_an_empty_decision_column(snap_and_model):
    snap, model = snap_and_model
    queue = review_queue(snap, model)
    assert set(queue["reason"]) <= {"uncertain score", "identity guard vetoed a confident link"}
    assert (queue["decision"] == "").all()
    assert queue["posterior"].is_monotonic_decreasing
