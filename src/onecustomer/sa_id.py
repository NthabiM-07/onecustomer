"""South African ID numbers: YYMMDD SSSS C A Z.

- YYMMDD: date of birth
- SSSS:   sequence; 0000-4999 female, 5000-9999 male
- C:      0 = citizen, 1 = permanent resident
- A:      historically a race digit, now always 8
- Z:      Luhn check digit over the first 12 digits

Every ID in this repository is generated here from a synthetic date of birth. None belongs to a real
person, but they are structurally valid, so the matcher can use the checksum the way a real bank does.
"""

from __future__ import annotations

from datetime import date


def luhn_check_digit(payload: str) -> str:
    """Luhn check digit for a string of digits (the rightmost payload digit is doubled)."""
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def luhn_valid(number: str) -> bool:
    return len(number) > 1 and number.isdigit() and luhn_check_digit(number[:-1]) == number[-1]


def make_id(dob: date, female: bool, sequence: int, citizen: int = 0) -> str:
    """Build a structurally valid ID. ``sequence`` is 0-4999; males are offset by 5000."""
    if not 0 <= sequence < 5000:
        raise ValueError("sequence must be in 0..4999")
    seq = sequence if female else sequence + 5000
    payload = f"{dob:%y%m%d}{seq:04d}{citizen}8"
    return payload + luhn_check_digit(payload)


def dob_from_id(national_id: str, pivot_year: int = 2026) -> date | None:
    """Date of birth encoded in an ID, or None if the first six digits are not a real date.

    Two-digit years above ``pivot_year % 100`` are read as 19YY.
    """
    if len(national_id) != 13 or not national_id.isdigit():
        return None
    yy, mm, dd = int(national_id[:2]), int(national_id[2:4]), int(national_id[4:6])
    century = 1900 if yy > pivot_year % 100 else 2000
    try:
        return date(century + yy, mm, dd)
    except ValueError:
        return None


def is_valid_id(national_id: str | None) -> bool:
    """13 digits, a real date of birth, citizenship digit 0/1, and a correct Luhn check digit."""
    if not national_id or len(national_id) != 13 or not national_id.isdigit():
        return False
    if national_id[10] not in "01":
        return False
    return dob_from_id(national_id) is not None and luhn_valid(national_id)
