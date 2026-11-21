from datetime import date

import numpy as np
import pytest

from onecustomer.sa_id import dob_from_id, is_valid_id, luhn_valid, make_id


def test_known_luhn_examples():
    assert luhn_valid("79927398713")
    assert not luhn_valid("79927398710")


def test_make_id_round_trips_birth_date_and_gender():
    nid = make_id(date(1990, 7, 1), female=False, sequence=1234)
    assert len(nid) == 13 and is_valid_id(nid)
    assert dob_from_id(nid) == date(1990, 7, 1)
    assert int(nid[6:10]) >= 5000  # male
    assert int(make_id(date(2001, 2, 15), female=True, sequence=42)[6:10]) < 5000


def test_two_digit_years_pivot():
    assert dob_from_id(make_id(date(2003, 1, 9), True, 1)).year == 2003
    assert dob_from_id(make_id(date(1953, 6, 1), True, 1)).year == 1953


@pytest.mark.parametrize("bad", ["", "123", "9902205312083x", "9913325312083", "9902205312093"])
def test_invalid_ids(bad):
    assert not is_valid_id(bad)


def test_every_single_digit_substitution_is_caught():
    """Luhn catches all single-digit errors, which is why a mistyped ID is never 'trusted'."""
    rng = np.random.default_rng(0)
    for _ in range(200):
        dob = date(1960 + int(rng.integers(40)), 1 + int(rng.integers(12)), 1 + int(rng.integers(28)))
        nid = make_id(dob, bool(rng.integers(2)), int(rng.integers(5000)))
        for pos in range(13):
            for d in "0123456789":
                if d != nid[pos]:
                    assert not luhn_valid(nid[:pos] + d + nid[pos + 1 :])


def test_sequence_range_is_enforced():
    with pytest.raises(ValueError):
        make_id(date(1990, 1, 1), True, 5000)
