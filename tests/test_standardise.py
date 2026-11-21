import pandas as pd

from onecustomer import standardise as s


def test_surname_particles_collapse():
    variants = ["van der Merwe", "VAN DER MERWE", "VANDERMERWE", "VD MERWE", "Van Der Merwe"]
    assert {s.surname(v) for v in variants} == {"VANDERMERWE"}


def test_double_barrelled_surname_tokens_overlap_with_maiden_name():
    assert s.surname_tokens(s.surname("Dlamini-Nkosi")) & s.surname_tokens(s.surname("DLAMINI"))


def test_nicknames_fold_to_one_form():
    assert s.first_name_canonical("Boitumelo") == s.first_name_canonical("TUMI") == "TUMI"
    assert s.first_name_canonical("Thabo") == "THABO"


def test_phone_formats():
    assert s.phone("+27 82 123 4567") == "0821234567"
    assert s.phone("+27821234567") == "0821234567"
    assert s.phone("082 123 4567") == "0821234567"
    assert s.phone("12345") is None
    assert s.phone(None) is None


def test_address_abbreviations():
    assert s.address_line("12 Church St") == s.address_line("12 CHURCH STREET") == "12 CHURCH STREET"
    assert s.address_line("5 Jacaranda Ave") == "5 JACARANDA AVENUE"


def test_email_and_missing_values():
    assert s.email("  Thabo.Zwane@Yahoo.com ") == "thabo.zwane@yahoo.com"
    assert s.email("not-an-email") is None
    assert s.first_name(float("nan")) is None


def test_trusted_id_requires_matching_birth_date():
    frame = pd.DataFrame({
        "first_name": ["A", "B"], "middle_name": [None, None], "surname": ["X", "Y"],
        "phone": [None, None], "email": [None, None], "national_id": ["9902205312083", "9902205312083"],
        "dob": ["1999-02-20", "1999-20-02"], "address_line": [None, None], "postal_code": [None, None],
    })
    out = s.standardise(frame)
    assert list(out["nid_valid"]) == [True, True]
    assert list(out["nid_trusted"]) == [True, False]
