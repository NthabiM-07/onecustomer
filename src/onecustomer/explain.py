"""Why two records were (or were not) linked, and which pairs a data steward should look at.

``explain_pair`` is a match-weight waterfall: the prior, then each field's comparison level and its
log2 Bayes factor, the term-frequency adjustment, the total and the posterior, then the two rules
that can veto a link. It answers the question a credit reviewer, an auditor or a customer
correcting their record under POPIA section 24 would ask: why is this record attached to that one?

``review_queue`` lists the pairs the model is least sure of, plus pairs the rules vetoed despite a
high score, so a steward can label them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .match import (
    COMPARE_COLUMNS,
    FIELDS,
    FSModel,
    candidate_pairs,
    compare_rows,
    identity_ok,
    pair_values,
)

LEVEL_NAMES = {
    "nid": ["missing", "different", "one keystroke apart", "same"],
    "dob": ["missing", "different", "day/month swapped or one part different", "same"],
    "first": ["missing", "different", "similar, middle name, or swapped with surname",
              "same (nicknames folded)"],
    "surname": ["missing", "different", "similar or shares a barrel", "same"],
    "phone": ["missing", "different", "same"],
    "email": ["missing", "different", "same"],
    "address": ["missing", "different", "same street or similar street in the same postal code",
                "same street and postal code"],
}


def _row(df: pd.DataFrame, i: int) -> tuple:
    values = df.iloc[i][COMPARE_COLUMNS]
    return tuple(None if pd.isna(v) else v for v in values)


def explain_pair(df: pd.DataFrame, model: FSModel, key_a: str, key_b: str, threshold: float = 0.9) -> dict:
    """Waterfall for two source records in one standardised snapshot."""
    pos = {k: i for i, k in enumerate(df["record_key"])}
    if key_a not in pos or key_b not in pos:
        missing = [k for k in (key_a, key_b) if k not in pos]
        raise KeyError(f"not in this snapshot: {', '.join(missing)}")
    i, j = pos[key_a], pos[key_b]
    gamma = np.array([compare_rows(_row(df, i), _row(df, j))], dtype=np.int8)
    pairs = pd.DataFrame({"a": [i], "b": [j]})
    values = pair_values(df, pairs)
    level_weights = model.level_weights()
    tf = model.tf_adjustment(gamma, values)
    prior = float(np.log2(model.prior / (1 - model.prior)))
    steps = []
    for k, f in enumerate(FIELDS):
        level = int(gamma[0, k])
        col = COMPARE_COLUMNS[{"nid": 0, "dob": 1, "first": 2, "surname": 5, "phone": 6, "email": 7,
                               "address": 8}[f]]
        steps.append({
            "field": f,
            "a": df.iloc[i][col],
            "b": df.iloc[j][col],
            "level": LEVEL_NAMES[f][level],
            "m": None if level == 0 else float(model.m[f][level]),
            "u": None if level == 0 else float(model.u[f][level]),
            "weight": float(level_weights[f][level]),
            "tf_adjustment": float(tf[f][0]) if f in tf else 0.0,
        })
    total = prior + sum(s["weight"] + s["tf_adjustment"] for s in steps)
    posterior = float(1.0 / (1.0 + 2.0 ** (-total)))
    trusted_a = df.iloc[i]["std_nid"] if bool(df.iloc[i]["nid_trusted"]) else None
    trusted_b = df.iloc[j]["std_nid"] if bool(df.iloc[j]["nid_trusted"]) else None
    return {
        "record_a": key_a,
        "record_b": key_b,
        "prior_weight": prior,
        "steps": steps,
        "total_weight": total,
        "posterior": posterior,
        "above_threshold": posterior >= threshold,
        "identity_guard_passes": bool(identity_ok(gamma)[0]),
        "different_trusted_ids": trusted_a is not None and trusted_b is not None and trusted_a != trusted_b,
    }


def render(e: dict) -> str:
    lines = [f"{e['record_a']} vs {e['record_b']}", "",
             f"{'field':<9}{'record A':<26}{'record B':<26}{'level':<34}{'weight':>8}{'tf':>7}",
             f"{'prior':<95}{e['prior_weight']:>8.2f}"]
    for s in e["steps"]:
        a = "" if s["a"] is None or (isinstance(s["a"], float) and np.isnan(s["a"])) else str(s["a"])
        b = "" if s["b"] is None or (isinstance(s["b"], float) and np.isnan(s["b"])) else str(s["b"])
        tf = f"{s['tf_adjustment']:+.2f}" if s["tf_adjustment"] else ""
        lines.append(f"{s['field']:<9}{a[:25]:<26}{b[:25]:<26}{s['level'][:33]:<34}{s['weight']:>+8.2f}{tf:>7}")
    linked = e["above_threshold"] and e["identity_guard_passes"] and not e["different_trusted_ids"]
    verdict = "LINK" if linked else "NO LINK"
    lines += [f"{'total':<95}{e['total_weight']:>+8.2f}", "",
              f"posterior {e['posterior']:.4f} ({'above' if e['above_threshold'] else 'below'} threshold)",
              f"identity guard: {'passes' if e['identity_guard_passes'] else 'blocks this link'}",
              f"trusted IDs: {'DIFFERENT, cannot link' if e['different_trusted_ids'] else 'no conflict'}",
              f"verdict: {verdict}"]
    return "\n".join(lines)


def review_queue(df: pd.DataFrame, model: FSModel, low: float = 0.5, high: float = 0.99,
                 threshold: float = 0.9, limit: int = 500) -> pd.DataFrame:
    """Pairs a steward should label: uncertain scores, and confident scores that a rule vetoed."""
    from .match import ComparisonCache

    pairs = candidate_pairs(df)
    gamma = ComparisonCache().compare(df, pairs)
    values = pair_values(df, pairs)
    post = model.posterior(gamma, values)
    guard = identity_ok(gamma)
    uncertain = (post >= low) & (post < high)
    vetoed = (post >= threshold) & ~guard
    keep = uncertain | vetoed
    a, b = pairs["a"].to_numpy()[keep], pairs["b"].to_numpy()[keep]
    cols = ["record_key", "first_name", "surname", "dob", "national_id", "phone", "address_line"]
    left = df.iloc[a][cols].reset_index(drop=True).add_suffix("_a")
    right = df.iloc[b][cols].reset_index(drop=True).add_suffix("_b")
    out = pd.concat([left, right], axis=1)
    out["posterior"] = post[keep].round(4)
    out["reason"] = np.where(vetoed[keep], "identity guard vetoed a confident link", "uncertain score")
    out["decision"] = ""  # for the steward: match / non-match
    out = out.sort_values("posterior", ascending=False).head(limit).reset_index(drop=True)
    return out
