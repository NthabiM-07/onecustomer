"""Party keys that survive re-matching.

Every month the matcher re-clusters the whole book. Clusters are anonymous, so something has to
decide which ``party_id`` each one carries. Downstream tables (a feature store, a collections
queue, a regulatory return) are keyed on that ID, so a key that changes for no reason breaks their
history just as surely as a bad match.

Three keyings over the same clusters:

- ``rebuild``: number the clusters afresh each month, in record-key order. This is what a truncate
  and reload into a table with an identity column does.
- ``anchor``: use the smallest source record key in the cluster as the party ID. Deterministic, but
  the ID changes whenever a record with a smaller key joins, or the anchor record leaves.
- ``stable``: carry last month's IDs forward by overlap. A cluster keeps the ID of the previous
  party it shares most records with (ties go to the older party). A party that loses that contest
  is retired with a crosswalk row pointing at the party that absorbed its records; a split-off
  part gets a new ID with a crosswalk row back to the party it came from.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import pairwise

import pandas as pd

KEYINGS = ("rebuild", "anchor", "stable")


def _format(n: int) -> str:
    return f"PTY{n:08d}"


def assign(clusters: dict[int, pd.DataFrame], keying: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Party IDs for every month.

    ``clusters`` maps month -> frame with ``record_key`` and ``cluster`` (any hashable label).
    Returns ``(assignments, crosswalk)``: assignments has ``month, record_key, party_id``; the
    crosswalk has ``month, from_party, to_party, reason`` and is only filled by ``stable``.
    """
    if keying not in KEYINGS:
        raise ValueError(f"unknown keying {keying!r}; choose from {KEYINGS}")
    rows, xref = [], []
    previous: dict[str, str] = {}
    counter = 0
    for month in sorted(clusters):
        frame = clusters[month]
        members: dict[object, list[str]] = defaultdict(list)
        for key, label in zip(frame["record_key"], frame["cluster"], strict=True):
            members[label].append(key)
        groups = sorted((sorted(keys) for keys in members.values()), key=lambda ks: ks[0])
        if keying == "rebuild":
            current = {k: _format(i + 1) for i, keys in enumerate(groups) for k in keys}
        elif keying == "anchor":
            current = {k: keys[0] for keys in groups for k in keys}
        else:
            current, counter, events = _carry_forward(groups, previous, counter)
            xref += [{"month": month, **e} for e in events]
        rows += [{"month": month, "record_key": k, "party_id": p} for k, p in current.items()]
        previous = current
    assignments = pd.DataFrame(rows, columns=["month", "record_key", "party_id"])
    crosswalk = pd.DataFrame(xref, columns=["month", "from_party", "to_party", "reason"])
    return assignments, crosswalk


def _carry_forward(groups: list[list[str]], previous: dict[str, str], counter: int):
    overlaps = []  # (-overlap, previous party, group index)
    for g, keys in enumerate(groups):
        for party, n in Counter(previous[k] for k in keys if k in previous).items():
            overlaps.append((-n, party, g))
    overlaps.sort()  # most overlap first; ties go to the lower (older) party ID
    owner: dict[int, str] = {}
    taken: set[str] = set()
    for _, party, g in overlaps:
        if g not in owner and party not in taken:
            owner[g] = party
            taken.add(party)
    events = []
    for g in range(len(groups)):
        if g not in owner:
            counter += 1
            owner[g] = _format(counter)
    current = {k: owner[g] for g, keys in enumerate(groups) for k in keys}

    # Explain every previous party whose records moved.
    existing = set(previous.values())
    moved: dict[str, Counter] = defaultdict(Counter)
    for k, old in previous.items():
        moved[old][current[k]] += 1
    for old, targets in sorted(moved.items()):
        if old in taken:
            for new in sorted(t for t in targets if t != old):
                if new not in existing:  # a fresh ID took some of this party's records
                    events.append({"from_party": new, "to_party": old, "reason": "split_from"})
        else:
            to_party = max(sorted(targets), key=lambda t: targets[t])
            reason = "merged_into" if len(targets) == 1 else "split_into"
            events.append({"from_party": old, "to_party": to_party, "reason": reason})
    return current, counter, events


def churn(assignments: pd.DataFrame, clusters: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Month-on-month key changes for records that existed in both months.

    ``explained`` means the record's group really changed: among records that existed last month,
    the set it is grouped with is different. Anything else is a key change with no matching reason.
    """
    out = []
    months = sorted(clusters)
    by_month = {m: assignments[assignments["month"] == m].set_index("record_key")["party_id"]
                for m in months}
    for prev, cur in pairwise(months):
        before, after = by_month[prev], by_month[cur]
        common = before.index.intersection(after.index)
        changed = before[common] != after[common]
        # group signature restricted to the records that existed last month
        old_groups = before[common].groupby(before[common]).groups
        new_groups = after[common].groupby(after[common]).groups
        old_sig = {k: frozenset(v) for v in old_groups.values() for k in v}
        new_sig = {k: frozenset(v) for v in new_groups.values() for k in v}
        regrouped = pd.Series({k: old_sig[k] != new_sig[k] for k in common})
        out.append({
            "month": cur,
            "records": len(common),
            "changed": int(changed.sum()),
            "explained": int((changed & regrouped[common]).sum()),
            "unexplained": int((changed & ~regrouped[common]).sum()),
        })
    return pd.DataFrame(out)
