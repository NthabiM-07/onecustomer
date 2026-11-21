import pandas as pd

from onecustomer.generate import generate, month_end, snapshot
from onecustomer.sa_id import dob_from_id, is_valid_id


def test_same_seed_same_world():
    a, b = generate(300, seed=11), generate(300, seed=11)
    pd.testing.assert_frame_equal(a.versions, b.versions)
    assert not generate(300, seed=12).versions.equals(a.versions)


def test_true_ids_are_valid_unique_and_encode_birth_date(small_world):
    people = small_world.people
    assert people["national_id"].is_unique
    assert people["national_id"].map(is_valid_id).all()
    assert (people["national_id"].map(lambda x: dob_from_id(x).isoformat()) == people["dob"]).all()


def test_twins_share_birth_date_but_not_id(small_world):
    p = small_world.people.set_index("person_id")
    twins = p.dropna(subset=["twin_of"])
    assert len(twins) > 0
    for _, row in twins.iterrows():
        sibling = p.loc[row["twin_of"]]
        assert row["dob"] == sibling["dob"] and row["national_id"] != sibling["national_id"]
        assert row["household_id"] == sibling["household_id"]


def test_snapshot_returns_latest_version_only(small_world):
    v = small_world.versions
    snap = snapshot(v, 24)
    assert snap["record_key"].is_unique
    assert len(snap) == small_world.links["record_key"].nunique()
    changed = v.groupby("record_key").size()
    key = changed[changed > 1].index[0]
    latest = v[v["record_key"] == key]["load_month"].max()
    assert snap.set_index("record_key").loc[key, "load_month"] == latest


def test_snapshots_only_contain_records_opened_by_then(small_world):
    opened = small_world.links.set_index("record_key")["open_month"]
    for m in (1, 6, 18):
        assert (snapshot(small_world.versions, m)["record_key"].map(opened) <= m).all()


def test_month_end():
    assert month_end(1).isoformat() == "2024-01-31"
    assert month_end(2).isoformat() == "2024-02-29"
    assert month_end(24).isoformat() == "2025-12-31"
