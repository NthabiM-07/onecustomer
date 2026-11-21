"""The golden record and its SCD Type 2 history.

Survivorship decides, attribute by attribute, which source record supplies the party's value, and
records that choice as column-level lineage:

- ``national_id``: the trusted ID (valid checksum and consistent with the captured birth date),
  else any valid ID; loans (branch KYC) before cards.
- ``date_of_birth``: the birth date on the record that supplied the trusted ID, else the most
  common one.
- ``first_name``, ``middle_name``: the KYC-ranked record (trusted ID first, then loans, since app
  sign-ups often carry nicknames).
- ``surname``: the record whose surname was most recently *updated* after onboarding (a marriage
  reaches one system before the other); with no updates, the KYC-ranked record.
- ``phone``, ``email``, address: the record where that value changed most recently, ties to cards
  (customers maintain their own app profile).
- ``total_exposure``: the sum over all member records.

Golden values are copied from the winning record and shown in one canonical format (title case,
street types spelled out), so a formatting difference between systems never opens a version.

A new version is opened when any golden attribute or the set of member records changes. Rows are
never rewritten: closing a version only sets its ``valid_to``.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .generate import month_end, snapshot

ATTRIBUTE_GROUPS = {
    "name": ["first_name", "middle_name"],
    "surname": ["surname"],
    "phone": ["phone"],
    "email": ["email"],
    "address": ["address_line", "city", "postal_code"],
}
TRACKED = ["national_id", "date_of_birth", "first_name", "middle_name", "surname", "phone", "email",
           "address_line", "city", "postal_code", "total_exposure", "record_keys"]
HISTORY_COLUMNS = ["party_id", "version", "valid_from", "valid_to", "valid_from_date", "valid_to_date",
                   "is_current", "change_reason", "closed_reason", *TRACKED, "systems", "lineage"]


def with_change_months(versions: pd.DataFrame) -> pd.DataFrame:
    """Add ``chg_<group>``: the load month at which each attribute group took its current value.

    For ``surname`` the onboarding capture counts as month 0, so only later updates win on recency.
    """
    v = versions.sort_values(["record_key", "load_month"]).reset_index(drop=True)
    for group, cols in ATTRIBUTE_GROUPS.items():
        sig = pd.Series(["|".join("" if pd.isna(x) else str(x) for x in row)
                         for row in v[cols].to_numpy(dtype=object)], index=v.index)
        prev = sig.groupby(v["record_key"]).shift()
        changed = prev.isna() | (sig != prev)
        when = v["load_month"].where(changed)
        if group == "surname":
            # Only an update after onboarding counts. Otherwise every newly onboarded duplicate,
            # typos included, would count as the latest surname and override the KYC record.
            when = when.mask(prev.isna(), 0)
        v[f"chg_{group}"] = when.groupby(v["record_key"]).ffill().astype(int)
    return v


def _title(value) -> str | None:
    """One canonical presentation (title case per word and hyphenated part), whatever the source case.

    Without it, "VAN WYK" on one system and "van Wyk" on the other would open a new version.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return " ".join("-".join(p.capitalize() for p in w.split("-")) for w in str(value).split())


def golden(rows: list[dict]) -> dict:
    """Survivorship over one party's member records (snapshot rows as dicts)."""
    kyc = sorted(rows, key=lambda r: (not r["nid_trusted"], r["system"] != "loans", r["record_key"]))
    lineage: dict[str, str | None] = {}

    id_row = (next((r for r in kyc if r["nid_trusted"]), None)
              or next((r for r in kyc if r["nid_valid"]), None))
    national_id = id_row["std_nid"] if id_row else None
    lineage["national_id"] = id_row["record_key"] if id_row else None

    if id_row is not None and id_row["nid_trusted"]:
        dob, lineage["date_of_birth"] = id_row["std_dob"], id_row["record_key"]
    else:
        counts = Counter(r["std_dob"] for r in kyc if r["std_dob"])
        dob = None
        for r in kyc:  # most common date; ties go to the KYC-ranked record
            if r["std_dob"] and (dob is None or counts[r["std_dob"]] > counts[dob]):
                dob = r["std_dob"]
        lineage["date_of_birth"] = next((r["record_key"] for r in kyc if r["std_dob"] == dob), None)

    name_row = kyc[0]
    lineage["first_name"] = lineage["middle_name"] = name_row["record_key"]
    surname_row = sorted(kyc, key=lambda r: -r["chg_surname"])[0]
    lineage["surname"] = surname_row["record_key"]

    def latest(field: str, group: str):
        candidates = [r for r in rows if r[field] is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda r: (-r[f"chg_{group}"], r["system"] != "cards", r["record_key"]))

    phone_row, email_row = latest("std_phone", "phone"), latest("std_email", "email")
    address_row = latest("address_line", "address")
    lineage["phone"] = phone_row["record_key"] if phone_row else None
    lineage["email"] = email_row["record_key"] if email_row else None
    lineage["address"] = address_row["record_key"] if address_row else None
    return {
        "national_id": national_id,
        "date_of_birth": dob,
        "first_name": _title(name_row["first_name"]),
        "middle_name": _title(name_row["middle_name"]),
        "surname": _title(surname_row["surname"]),
        "phone": phone_row["std_phone"] if phone_row else None,
        "email": email_row["std_email"] if email_row else None,
        "address_line": _title(address_row["std_address"]) if address_row else None,
        "city": _title(address_row["city"]) if address_row else None,
        "postal_code": address_row["postal_code"] if address_row else None,
        "total_exposure": round(sum(float(r["balance"]) for r in rows), 2),
        "record_keys": "|".join(sorted(r["record_key"] for r in rows)),
        "systems": "+".join(sorted({r["system"] for r in rows})),
        "lineage": json.dumps(lineage, sort_keys=True),
    }


_ROW_FIELDS = ["record_key", "load_month", "system", "nid_trusted", "nid_valid", "std_nid", "std_dob",
               "first_name", "middle_name", "surname", "std_phone", "std_email", "address_line",
               "std_address", "city",
               "postal_code", "balance", *(f"chg_{g}" for g in ATTRIBUTE_GROUPS)]


def _describe_change(prev: dict, gold: dict) -> str:
    """Comma-separated list of what changed, with address columns reported as one change."""
    changed = [c for c in TRACKED if prev[c] != gold[c]]
    labels = []
    for c in changed:
        label = "address" if c in ("address_line", "city", "postal_code") else c
        label = "records" if c == "record_keys" else label
        if label == "total_exposure" and "record_keys" in changed:
            continue  # exposure moves with membership
        if label not in labels:
            labels.append(label)
    return ",".join(sorted(labels, key=lambda x: x != "records"))


def build(versions: pd.DataFrame, assignments: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """SCD2 party history from standardised versions, monthly party assignments and the crosswalk."""
    v = with_change_months(versions)
    cache: dict[tuple, dict] = {}
    open_rows: dict[str, dict] = {}
    closed: list[dict] = []
    events = {(int(r.month), r.from_party): f"{r.reason}:{r.to_party}" for r in crosswalk.itertuples()}
    months = sorted(assignments["month"].unique())
    for month in months:
        parties = dict(zip(*(assignments.loc[assignments["month"] == month, c] for c in
                             ("record_key", "party_id")), strict=True))
        snap = snapshot(v, month)[_ROW_FIELDS]
        snap = snap[snap["record_key"].isin(parties)]
        members: dict[str, list[dict]] = defaultdict(list)
        for row in snap.astype(object).where(snap.notna(), None).to_dict("records"):
            members[parties[row["record_key"]]].append(row)
        for party in sorted(members):
            records = members[party]
            sig = tuple(sorted((r["record_key"], r["load_month"]) for r in records))
            gold = cache.get(sig)
            if gold is None:
                gold = cache[sig] = golden(records)
            prev = open_rows.get(party)
            if prev is not None and all(prev[c] == gold[c] for c in TRACKED):
                continue
            if prev is None:
                reason = events.get((month, party), "created")
            else:
                reason = _describe_change(prev, gold)
                prev.update(valid_to=month, is_current=False)
                closed.append(prev)
            open_rows[party] = {
                "party_id": party, "version": (prev["version"] + 1) if prev else 1,
                "valid_from": month, "valid_to": None, "is_current": True,
                "change_reason": reason, "closed_reason": None, **gold,
            }
        for party in sorted(set(open_rows) - set(members)):
            row = open_rows.pop(party)
            row.update(valid_to=month, is_current=False, closed_reason=events.get((month, party), "retired"))
            closed.append(row)
    history = pd.DataFrame(closed + list(open_rows.values()))
    history["valid_from_date"] = history["valid_from"].map(lambda m: month_end(int(m)).isoformat())
    history["valid_to_date"] = history["valid_to"].map(
        lambda m: None if pd.isna(m) else month_end(int(m)).isoformat())
    history["valid_to"] = history["valid_to"].astype("Int64")
    return history[HISTORY_COLUMNS].sort_values(["party_id", "version"]).reset_index(drop=True)


def as_of(history: pd.DataFrame, month: int) -> pd.DataFrame:
    """The party table as the master held it after the load at the end of ``month``."""
    mask = (history["valid_from"] <= month) & (history["valid_to"].isna() | (history["valid_to"] > month))
    return history[mask.fillna(False).astype(bool)].reset_index(drop=True)


def audit(history: pd.DataFrame, crosswalk: pd.DataFrame | None = None) -> list[str]:
    """SCD2 invariants. Returns a list of violations (empty means the table is sound)."""
    problems = []
    for party, grp in history.sort_values(["party_id", "valid_from"]).groupby("party_id"):
        frm = grp["valid_from"].to_numpy()
        to = grp["valid_to"].to_numpy(dtype=object)
        if list(grp["version"]) != list(range(1, len(grp) + 1)):
            problems.append(f"{party}: versions are not 1..n")
        for i in range(len(grp) - 1):
            if to[i] is None or pd.isna(to[i]) or int(to[i]) != int(frm[i + 1]):
                problems.append(f"{party}: version {i + 1} does not end where version {i + 2} starts")
        for f, t in zip(frm, to, strict=True):
            if t is not None and not pd.isna(t) and int(t) <= int(f):
                problems.append(f"{party}: empty or negative validity interval")
        current = grp["is_current"].to_numpy(dtype=bool)
        if current.sum() > 1:
            problems.append(f"{party}: more than one current row")
        if any(c != (t is None or pd.isna(t)) for c, t in zip(current, to, strict=True)):
            problems.append(f"{party}: is_current disagrees with valid_to")
    cur = history[history["is_current"].astype(bool)]
    keys = cur["record_keys"].str.split("|").explode()
    dupes = keys[keys.duplicated()]
    if len(dupes):
        problems.append(f"{len(dupes)} source records belong to more than one current party")
    if crosswalk is not None:
        retired = set(history["party_id"]) - set(cur["party_id"])
        explained = set(crosswalk.loc[crosswalk["reason"] != "split_from", "from_party"])
        missing = retired - explained
        if missing:
            example = sorted(missing)[:3]
            problems.append(f"{len(missing)} retired parties have no crosswalk row, e.g. {example}")
        # Following merged_into / split_into rows from any retired ID must end at a live party.
        forward = crosswalk[crosswalk["reason"] != "split_from"].sort_values("month")
        step = dict(zip(forward["from_party"], forward["to_party"], strict=True))
        live = set(cur["party_id"])
        for start in sorted(retired & set(step)):
            party, hops = start, 0
            while party not in live and party in step and hops < 100:
                party, hops = step[party], hops + 1
            if party not in live:
                problems.append(f"{start}: crosswalk chain does not reach a live party")
    return problems
