import json

import pandas as pd

from onecustomer import history, pipeline


def row(key, system, **kw):
    base = {"record_key": key, "load_month": 1, "system": system, "nid_trusted": False, "nid_valid": False,
            "std_nid": None, "std_dob": "1990-01-01", "first_name": "THABO", "middle_name": None,
            "surname": "ZWANE", "std_phone": None, "std_email": None, "address_line": "1 MAIN ROAD",
            "city": "DURBAN", "postal_code": "4001", "balance": 100.0, "chg_name": 1, "chg_surname": 1,
            "chg_phone": 1, "chg_email": 1, "chg_address": 1}
    base.update(kw)
    return base


def test_survivorship_and_lineage():
    loans = row("LN1", "loans", nid_trusted=True, nid_valid=True, std_nid="9001015009087",
                std_phone="0820000001", chg_phone=2, address_line="1 MAIN ROAD", chg_address=1)
    cards = row("CD1", "cards", first_name="Tumi", surname="Zwane-Nkosi", chg_surname=9,
                std_phone="0820000002", chg_phone=7, address_line="9 Long St", city="Cape Town",
                postal_code="8001", chg_address=5, balance=50.0)
    gold = history.golden([cards, loans])
    lineage = json.loads(gold["lineage"])
    assert gold["national_id"] == "9001015009087" and lineage["national_id"] == "LN1"
    assert gold["first_name"] == "Thabo" and lineage["first_name"] == "LN1"  # KYC record, title-cased
    assert gold["surname"] == "Zwane-Nkosi" and lineage["surname"] == "CD1"  # most recent change
    assert gold["phone"] == "0820000002" and lineage["phone"] == "CD1"
    assert gold["address_line"] == "9 Long St" and lineage["address"] == "CD1"
    assert gold["total_exposure"] == 150.0
    assert gold["record_keys"] == "CD1|LN1" and gold["systems"] == "cards+loans"


def test_contact_ties_go_to_cards():
    loans = row("LN1", "loans", std_phone="0820000001", chg_phone=3)
    cards = row("CD1", "cards", std_phone="0820000002", chg_phone=3)
    assert history.golden([loans, cards])["phone"] == "0820000002"


def test_change_months_track_attribute_groups():
    v = pd.DataFrame([
        {"record_key": "LN1", "load_month": 1, "first_name": "A", "middle_name": None, "surname": "X",
         "phone": "1", "email": None, "address_line": "a", "city": "c", "postal_code": "1"},
        {"record_key": "LN1", "load_month": 4, "first_name": "A", "middle_name": None, "surname": "X",
         "phone": "2", "email": None, "address_line": "a", "city": "c", "postal_code": "1"},
        {"record_key": "LN1", "load_month": 9, "first_name": "A", "middle_name": None, "surname": "X",
         "phone": "2", "email": None, "address_line": "b", "city": "c", "postal_code": "1"},
    ])
    out = history.with_change_months(v)
    assert list(out["chg_phone"]) == [1, 4, 4]
    assert list(out["chg_address"]) == [1, 1, 9]
    assert list(out["chg_surname"]) == [1, 1, 1]


def test_history_passes_audit(small_run):
    assert history.audit(small_run.history, small_run.crosswalk) == []


def test_one_current_row_per_live_party_and_every_record_covered(small_run):
    h = small_run.history
    current = h[h["is_current"].astype(bool)]
    assert current["party_id"].is_unique
    last = small_run.assignments[small_run.assignments["month"] == 12]
    assert set(current["party_id"]) == set(last["party_id"])
    covered = set(current["record_keys"].str.split("|").explode())
    assert covered == set(last["record_key"])


def test_as_of_matches_a_replay(small_world, small_run):
    """History is append-only: rebuilding through month 7 reproduces the final table read at month 7."""
    replay = pipeline.run(small_world, months=7).history
    cols = [*history.TRACKED, "party_id", "version", "valid_from", "lineage"]
    a = history.as_of(replay, 7)[cols].sort_values("party_id").reset_index(drop=True)
    b = history.as_of(small_run.history, 7)[cols].sort_values("party_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(a.astype(object).where(a.notna(), None),
                                  b.astype(object).where(b.notna(), None))


def test_audit_catches_a_gap():
    h = pd.DataFrame([
        {"party_id": "P1", "version": 1, "valid_from": 1, "valid_to": 3, "is_current": False,
         "record_keys": "LN1"},
        {"party_id": "P1", "version": 2, "valid_from": 4, "valid_to": None, "is_current": True,
         "record_keys": "LN1"},
    ])
    h["valid_to"] = h["valid_to"].astype("Int64")
    assert any("does not end where" in p for p in history.audit(h))
