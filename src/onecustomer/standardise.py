"""Turn raw source fields into comparable ones.

Standardisation is applied once per source-record *version*, so a record that has not changed is
never re-standardised. Each function is pure and handles ``None``.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from .reference import NICKNAMES
from .sa_id import dob_from_id, is_valid_id

_NON_ALPHA = re.compile(r"[^A-Z \-]")
_SPACES = re.compile(r"\s+")
_ADDRESS_WORDS = {"ST": "STREET", "RD": "ROAD", "AVE": "AVENUE", "DR": "DRIVE", "LN": "LANE"}


def _clean(text: str | None) -> str | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().upper()
    text = _SPACES.sub(" ", _NON_ALPHA.sub("", text)).strip()
    return text or None


def first_name(raw: str | None) -> str | None:
    return _clean(raw)


def first_name_canonical(raw: str | None) -> str | None:
    """Fold a formal name and its short form together: BOITUMELO and TUMI both become TUMI."""
    name = _clean(raw)
    return NICKNAMES.get(name, name) if name else None


def surname(raw: str | None) -> str | None:
    """VAN DER MERWE, van der Merwe, VANDERMERWE and VD MERWE all become VANDERMERWE."""
    name = _clean(raw)
    if not name:
        return None
    if name.startswith("VD "):
        name = "VANDER" + name[3:]
    return name.replace(" ", "")


def surname_tokens(std_surname: str | None) -> frozenset[str]:
    """Parts of a double-barrelled surname, so DLAMINI-NKOSI overlaps with DLAMINI."""
    return frozenset(t for t in (std_surname or "").split("-") if t)


def phone(raw: str | None) -> str | None:
    """South African numbers in national format: +27 82 123 4567 -> 0821234567."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    digits = re.sub(r"\D", "", str(raw))
    if digits.startswith("27") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits if len(digits) == 10 and digits.startswith("0") else None


def email(raw: str | None) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    value = str(raw).strip().lower()
    return value if "@" in value else None


def national_id(raw: str | None) -> str | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits or None


def address_line(raw: str | None) -> str | None:
    """12 Church St and 12 CHURCH STREET both become 12 CHURCH STREET."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    tokens = re.findall(r"[A-Z]+|\d+", str(raw).upper())
    return " ".join(_ADDRESS_WORDS.get(t, t) for t in tokens) or None


def _map(series: pd.Series, fn) -> pd.Series:
    """Apply ``fn`` to plain Python values, passing None for missing, and keep None in the result."""
    values = [fn(None if pd.isna(x) else x) for x in series.to_numpy(dtype=object)]
    return pd.Series(values, index=series.index, dtype=object)


def _id_dob(nid: str | None) -> str | None:
    dob = dob_from_id(nid) if nid else None
    return dob.isoformat() if dob else None


def standardise(versions: pd.DataFrame) -> pd.DataFrame:
    """Add ``std_*`` columns to a frame of source-record versions."""
    out = versions.copy()
    out["std_first"] = _map(out["first_name"], first_name)
    out["std_first_canon"] = _map(out["first_name"], first_name_canonical)
    out["std_middle"] = _map(out["middle_name"], first_name)
    out["std_surname"] = _map(out["surname"], surname)
    out["std_phone"] = _map(out["phone"], phone)
    out["std_email"] = _map(out["email"], email)
    out["std_nid"] = _map(out["national_id"], national_id)
    out["nid_valid"] = _map(out["std_nid"], is_valid_id).astype(bool)
    out["std_dob"] = _map(out["dob"], lambda x: x)
    # An ID is only trusted for constraints if it is valid *and* agrees with the captured birth date.
    id_dob = _map(out["std_nid"], _id_dob)
    out["nid_trusted"] = (out["nid_valid"] & (id_dob == out["std_dob"])).astype(bool)
    out["std_address"] = _map(out["address_line"], address_line)
    out["std_postal"] = _map(out["postal_code"], lambda x: x)
    return out
