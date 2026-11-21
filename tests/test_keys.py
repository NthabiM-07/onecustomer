import pandas as pd
import pytest

from onecustomer.keys import assign, churn


def months(*groupings):
    """Each argument is one month: a list of groups, each a list of record keys."""
    out = {}
    for m, groups in enumerate(groupings, start=1):
        rows = [(k, g) for g, keys in enumerate(groups) for k in keys]
        out[m] = pd.DataFrame(rows, columns=["record_key", "cluster"])
    return out


def ids(assignments, month):
    a = assignments[assignments["month"] == month]
    return dict(zip(a["record_key"], a["party_id"], strict=True))


def test_new_record_joining_keeps_the_party_id():
    clusters = months([["LN1"], ["LN2"]], [["CD9", "LN1"], ["LN2"]])
    stable, xref = assign(clusters, "stable")
    assert ids(stable, 1)["LN1"] == ids(stable, 2)["LN1"] == ids(stable, 2)["CD9"]
    assert xref.empty
    anchor, _ = assign(clusters, "anchor")
    assert ids(anchor, 1)["LN1"] != ids(anchor, 2)["LN1"]  # CD9 < LN1 takes over as anchor


def test_merge_retires_one_id_with_a_crosswalk_row():
    clusters = months([["LN1"], ["CD2"]], [["LN1", "CD2"]])
    stable, xref = assign(clusters, "stable")
    first = ids(stable, 1)
    survivor = ids(stable, 2)["LN1"]
    retired = ({first["LN1"], first["CD2"]} - {survivor}).pop()
    assert survivor == min(first.values())  # the older party survives
    assert xref.to_dict("records") == [
        {"month": 2, "from_party": retired, "to_party": survivor, "reason": "merged_into"}]


def test_split_gets_a_new_id_pointing_back():
    clusters = months([["LN1", "LN2", "CD3"]], [["LN1", "CD3"], ["LN2"]])
    stable, xref = assign(clusters, "stable")
    original = ids(stable, 1)["LN1"]
    assert ids(stable, 2)["LN1"] == original
    new = ids(stable, 2)["LN2"]
    assert new != original
    assert xref[["from_party", "to_party", "reason"]].values.tolist() == [[new, original, "split_from"]]


def test_churn_separates_explained_from_unexplained():
    clusters = months([["LN1"], ["LN2"]], [["CD0"], ["LN1"], ["LN2"]])
    rebuild, _ = assign(clusters, "rebuild")
    c = churn(rebuild, clusters)
    assert c.loc[0, "changed"] == 2 and c.loc[0, "unexplained"] == 2  # renumbered, nothing regrouped
    stable, _ = assign(clusters, "stable")
    assert churn(stable, clusters).loc[0, "changed"] == 0


def test_unknown_keying_is_rejected():
    with pytest.raises(ValueError):
        assign({}, "random")
