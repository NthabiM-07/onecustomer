"""The experiment behind the README: matching quality, key stability, and history you can audit.

Every number in the README comes from ``reports/results.json``, written by this module.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import history, keys
from .evaluate import pair_completeness, pairwise, party_errors, scorecard
from .explain import review_queue
from .generate import N_MONTHS, World, month_end, snapshot
from .match import ComparisonCache, candidate_pairs, link, train
from .pipeline import match_months, run
from .standardise import standardise

STRATEGY_CONFIGS = [
    ("Exact ID only", "id_exact", {}),
    ("Deterministic rules", "rules", {}),
    ("Fellegi-Sunter weights only", "fellegi_sunter", {"constrained": False, "identity_guard": False}),
    ("+ trusted-ID cannot-link", "fellegi_sunter", {"identity_guard": False}),
    ("+ identity guard (onecustomer)", "fellegi_sunter", {}),
]
ABLATIONS = [
    ("onecustomer without term-frequency adjustment", {"tf_adjust": False}),
]
THRESHOLDS = [0.5, 0.8, 0.9, 0.95, 0.99, 0.999]

# Reference palette (validated: first three categorical slots, all pairs, light surface)
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


def _hard_negative_merges(labels: np.ndarray, truth: np.ndarray, people: pd.DataFrame) -> dict[str, int]:
    """Pairs of related-but-different people placed in one party."""
    party_of = pd.DataFrame({"party": labels, "person": truth}).groupby("person")["party"].agg(set)
    def together(a: str, b: str) -> bool:
        return a in party_of.index and b in party_of.index and bool(party_of[a] & party_of[b])
    twins = people.dropna(subset=["twin_of"])
    juniors = people.dropna(subset=["junior_of"])
    merged_people = pd.DataFrame({"party": labels, "person": truth})
    per_party = merged_people.groupby("party")["person"].nunique()
    merged = merged_people[merged_people["party"].isin(per_party[per_party > 1].index)]
    hh = people.set_index("person_id")["household_id"]
    same_household = merged.groupby("party")["person"].agg(lambda p: hh[list(p)].nunique() == 1)
    same_household = same_household.astype(bool)
    return {
        "twin_pairs_merged": int(sum(together(r.person_id, r.twin_of) for r in twins.itertuples())),
        "twin_pairs": len(twins),
        "father_son_pairs_merged": int(sum(together(r.person_id, r.junior_of) for r in juniors.itertuples())),
        "father_son_pairs": len(juniors),
        "false_merges_within_household": int(same_household.sum()),
        "false_merges_across_households": int((~same_household).sum()),
    }


def _score(label: str, labels: np.ndarray, final: pd.DataFrame, truth: np.ndarray,
           people: pd.DataFrame) -> dict:
    return {
        "strategy": label,
        **scorecard(labels, truth),
        **party_errors(labels, truth, final["balance"].to_numpy(dtype=float)),
        **_hard_negative_merges(labels, truth, people),
    }


def _matching(final: pd.DataFrame, truth: np.ndarray, people: pd.DataFrame,
              month12: pd.DataFrame | None = None) -> dict:
    cache = ComparisonCache()
    model = train(final, cache)
    rows = []
    for label, strategy, kwargs in STRATEGY_CONFIGS:
        result = link(final, strategy, cache=cache, model=model, **kwargs)
        rows.append(_score(label, result.labels, final, truth, people))
    ablations = []
    for label, train_kwargs in ABLATIONS:
        variant = train(final, cache, **train_kwargs)
        result = link(final, "fellegi_sunter", cache=cache, model=variant)
        ablations.append(_score(label, result.labels, final, truth, people))
    holdout = None
    if month12 is not None:
        # Temporal holdout: parameters learnt on the June 2024 load, frozen, applied to December 2025.
        frozen = train(month12, ComparisonCache())
        result = link(final, "fellegi_sunter", cache=cache, model=frozen)
        holdout = _score("model trained on month 12, applied to month 24", result.labels, final, truth,
                         people)
    pairs = candidate_pairs(final)
    queue = review_queue(final, model)
    sweep = []
    for threshold in THRESHOLDS:
        result = link(final, "fellegi_sunter", cache=cache, model=model, threshold=threshold)
        errors = party_errors(result.labels, truth, final["balance"].to_numpy(dtype=float))
        sweep.append({"threshold": threshold, **pairwise(result.labels, truth),
                      "people_split": errors["people_split"],
                      "people_in_false_merges": errors["people_in_false_merges"]})
    return {"strategies": rows, "ablations": ablations, "temporal_holdout": holdout,
            "candidate_pairs": len(pairs),
            "pair_completeness": pair_completeness(pairs["a"].to_numpy(), pairs["b"].to_numpy(), truth),
            "review_queue": {"pairs": len(queue), **queue["reason"].value_counts().to_dict()},
            "threshold_sweep": sweep, "model": model.as_dict(),
            "level_weights": {f: [round(float(x), 2) for x in w[1:]]
                              for f, w in model.level_weights().items()}}


def _scd1_vs_scd2(hist: pd.DataFrame, crosswalk: pd.DataFrame, months: int) -> dict:
    """How often a point-in-time lookup returns what the master actually held that month.

    SCD2 answers from ``as_of``. SCD1 keeps only the latest row per party, so every lookup returns
    today's value (following the crosswalk for parties that were merged away).
    """
    current = hist[hist["is_current"].astype(bool)].set_index("party_id")
    forward = dict(zip(crosswalk.loc[crosswalk["reason"] != "split_from", "from_party"],
                       crosswalk.loc[crosswalk["reason"] != "split_from", "to_party"], strict=True))
    def survivor(p: str) -> str | None:
        seen = set()
        while p not in current.index and p in forward and p not in seen:
            seen.add(p)
            p = forward[p]
        return p if p in current.index else None
    attrs = {"address": ["address_line", "city", "postal_code"], "surname": ["surname"], "phone": ["phone"]}
    wrong = dict.fromkeys(attrs, 0)
    lookups = 0
    for m in range(1, months):
        snap = history.as_of(hist, m)
        lookups += len(snap)
        for name, cols in attrs.items():
            today = snap["party_id"].map(survivor)
            ok = today.notna()
            then = snap.loc[ok, cols].astype(object).where(snap.loc[ok, cols].notna(), None)
            now = current.loc[today[ok], cols].astype(object)
            now = now.where(now.notna(), None)
            differs = [tuple(a) != tuple(b) for a, b in zip(then.to_numpy(), now.to_numpy(), strict=True)]
            wrong[name] += int(sum(differs)) + int((~ok).sum())
    return {"lookups": lookups, "scd1_wrong": wrong,
            "scd1_wrong_rate": {k: v / lookups for k, v in wrong.items()}}


def _replay(world: World, hist: pd.DataFrame, month: int) -> dict:
    """Rebuild from scratch through ``month`` and compare with the final table read as of that month."""
    replayed = run(world, months=month).history
    fresh = history.as_of(replayed, month)
    later = history.as_of(hist, month)
    cols = [c for c in history.TRACKED if c != "record_keys"] + ["party_id", "record_keys", "version",
                                                                  "valid_from", "lineage"]
    a = fresh[cols].sort_values("party_id").reset_index(drop=True).astype(object)
    b = later[cols].sort_values("party_id").reset_index(drop=True).astype(object)
    a, b = a.where(a.notna(), None), b.where(b.notna(), None)
    equal = a.shape == b.shape and bool((a.to_numpy() == b.to_numpy()).all())
    return {"month": month, "parties": len(a), "identical": equal}


def _chart_matching(rows: list[dict], path: Path) -> None:
    labels = [r["strategy"] for r in rows]
    split = [r["people_split"] for r in rows]
    merged = [r["people_in_false_merges"] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 3.8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    y = np.arange(len(rows))[::-1]
    h = 0.36
    ax.barh(y + h / 2 + 0.01, split, height=h, color=SERIES[0], label="Customers split over several parties")
    ax.barh(y - h / 2 - 0.01, merged, height=h, color=SERIES[1], label="Customers merged with someone else")
    top = max(split + merged)
    for yy, s, m in zip(y, split, merged, strict=True):
        ax.text(s + top * 0.01, yy + h / 2, f"{s:,}", va="center", fontsize=9, color=INK_2)
        ax.text(m + top * 0.01, yy - h / 2, f"{m:,}", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(y, labels, fontsize=10, color=INK)
    ax.set_xlim(0, top * 1.12)
    ax.tick_params(axis="x", colors=INK_2, labelsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_xlabel("Real customers affected (of 10,000)", color=INK_2, fontsize=9)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    ax.set_title("Who ends up in the wrong party, December 2025 load", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _chart_keys(series: dict[str, list[float]], months: list[int], path: Path) -> None:
    import matplotlib.dates as mdates

    fig, ax = plt.subplots(figsize=(9, 3.8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    x = [month_end(m) for m in months]
    names = {"rebuild": "Renumber every load", "anchor": "Smallest record key",
             "stable": "Carry forward (onecustomer)"}
    for color, (k, values) in zip(SERIES, series.items(), strict=True):
        ax.plot(x, values, color=color, linewidth=2, label=names[k])
        ax.annotate(f"{values[-1]:.1f}%", (x[-1], values[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=INK_2)
    top = max(max(v) for v in series.values())
    ax.set_ylim(-1, max(10, top * 1.25))
    ax.set_ylabel("% of records", color=INK_2, fontsize=9)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK, ncol=3)
    ax.set_title("Records whose party ID has changed at least once with no change to their links",
                 loc="left", color=INK, fontsize=11)
    fig.tight_layout(rect=(0, 0, 0.96, 1))
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def experiment(world: World, out: Path = Path("reports"), replay_months: tuple[int, ...] = (8, 16)) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    std = standardise(world.versions)
    truth_map = world.links.set_index("record_key")["person_id"]
    final = snapshot(std, N_MONTHS)
    truth = final["record_key"].map(truth_map).to_numpy()
    results: dict = {
        "world": {"seed": world.seed, "people": len(world.people), "months": N_MONTHS,
                  "records": len(final), "versions": len(world.versions),
                  "records_by_system": final["system"].value_counts().to_dict(),
                  "twin_pairs": int(world.people["twin_of"].notna().sum()),
                  "father_son_pairs": int(world.people["junior_of"].notna().sum())},
    }
    results["matching"] = _matching(final, truth, world.people, snapshot(std, 12))

    monthly = match_months(std, N_MONTHS)
    quality = []
    for m, frame in monthly.clusters.items():
        t = frame["record_key"].map(truth_map).to_numpy()
        quality.append({"month": m, "records": len(frame), **pairwise(frame["cluster"].to_numpy(), t)})
    results["monthly_quality"] = quality

    churn_summary, cumulative = {}, {}
    for keying in keys.KEYINGS:
        assignments, crosswalk = keys.assign(monthly.clusters, keying)
        c = keys.churn(assignments, monthly.clusters)
        wide = assignments.pivot(index="record_key", columns="month", values="party_id")
        changed_any, unexplained_any = set(), set()
        series = [0.0]
        for m in range(2, N_MONTHS + 1):
            prev, cur = wide[m - 1], wide[m]
            both = prev.notna() & cur.notna()
            moved = both & (prev != cur)
            changed_any |= set(moved[moved].index)
            regroup = _regrouped(monthly.clusters[m - 1], monthly.clusters[m])
            unexplained_any |= {k for k in moved[moved].index if k not in regroup}
            series.append(100 * len(unexplained_any) / int(cur.notna().sum()))
        cumulative[keying] = series
        churn_summary[keying] = {
            "key_changes": int(c["changed"].sum()),
            "explained_by_regrouping": int(c["explained"].sum()),
            "unexplained": int(c["unexplained"].sum()),
            "records_ever_rekeyed": len(changed_any),
            "records_ever_rekeyed_unexplained": len(unexplained_any),
            "records_at_end": int(wide[N_MONTHS].notna().sum()),
            "distinct_party_ids_issued": int(assignments["party_id"].nunique()),
            "crosswalk_rows": len(crosswalk),
        }
    results["keys"] = churn_summary

    assignments, crosswalk = keys.assign(monthly.clusters, "stable")
    hist = history.build(std, assignments, crosswalk)
    problems = history.audit(hist, crosswalk)
    results["history"] = {
        "rows": len(hist),
        "parties_ever": int(hist["party_id"].nunique()),
        "current_parties": int(hist["is_current"].sum()),
        "audit_violations": problems,
        "change_reasons": hist["change_reason"].str.split(",").explode()
        .str.replace(r":.*", "", regex=True).value_counts().to_dict(),
        "closed_reasons": hist["closed_reason"].dropna().str.replace(r":.*", "", regex=True)
        .value_counts().to_dict(),
        "crosswalk": crosswalk["reason"].value_counts().to_dict(),
        **_scd1_vs_scd2(hist, crosswalk, N_MONTHS),
    }
    results["replay"] = [_replay(world, hist, m) for m in replay_months]
    results["seconds"] = round(time.perf_counter() - started, 1)

    _chart_matching(results["matching"]["strategies"], out / "who_ends_up_in_the_wrong_party.png")
    _chart_keys(cumulative, list(range(1, N_MONTHS + 1)), out / "party_id_churn.png")
    (out / "results.json").write_text(json.dumps(results, indent=2, default=_json_default))
    (out / "report.md").write_text(render_report(results))
    return results


def _regrouped(before: pd.DataFrame, after: pd.DataFrame) -> set[str]:
    """Records whose group, restricted to records present in both months, changed."""
    common = set(before["record_key"]) & set(after["record_key"])
    def signatures(frame: pd.DataFrame) -> dict[str, frozenset]:
        f = frame[frame["record_key"].isin(common)]
        groups = f.groupby("cluster")["record_key"].agg(frozenset)
        return {k: g for g in groups for k in g}
    a, b = signatures(before), signatures(after)
    return {k for k in common if a[k] != b[k]}


def _json_default(x):
    if isinstance(x, np.integer | np.floating):
        return x.item()
    if isinstance(x, np.bool_):
        return bool(x)
    raise TypeError(type(x))


def _pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def render_report(r: dict) -> str:
    w = r["world"]
    lines = [
        "# onecustomer experiment report",
        "",
        f"Synthetic world: {w['people']:,} people, seed {w['seed']}, {w['months']} monthly loads, "
        f"{w['records']:,} source records ({w['records_by_system'].get('loans', 0):,} loans, "
        f"{w['records_by_system'].get('cards', 0):,} cards), {w['versions']:,} record versions. "
        f"{w['twin_pairs']} twin pairs and {w['father_son_pairs']} father-and-son pairs with the same name.",
        "",
        "## Matching on the final load",
        "",
        "| Strategy | Precision | Recall | F1 | Customers split | Customers falsely merged | "
        "Twin pairs merged | Exposure wrong (multi-record customers) | Exposure missing |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in r["matching"]["strategies"]:
        lines.append(
            f"| {s['strategy']} | {_pct(s['precision'], 2)} | {_pct(s['recall'], 2)} | {_pct(s['f1'], 2)} | "
            f"{s['people_split']:,} | {s['people_in_false_merges']:,} | "
            f"{s['twin_pairs_merged']} of {s['twin_pairs']} | {_pct(s['exposure_wrong_multi'])} | "
            f"R{s['exposure_understated_rand'] / 1e6:,.1f}m |")
    lines += ["", "### Threshold sweep (full model)", "",
              "| Posterior threshold | Precision | Recall | Customers split | Customers falsely merged |",
              "|---|---|---|---|---|"]
    for s in r["matching"]["threshold_sweep"]:
        lines.append(f"| {s['threshold']} | {_pct(s['precision'], 2)} | {_pct(s['recall'], 2)} | "
                     f"{s['people_split']:,} | {s['people_in_false_merges']:,} |")
    lines += ["", "### Learnt match weights (log2 Bayes factor per comparison level, low to high)", ""]
    for f, ws in r["matching"]["level_weights"].items():
        lines.append(f"- `{f}`: {', '.join(f'{x:+.1f}' for x in ws)}")
    lines += ["", f"Estimated probability that two random records match: "
              f"{r['matching']['model']['prior']:.2e}", "", "## Party keys over 24 loads", "",
              "| Keying | Key changes | Explained by a real regrouping | Unexplained | Records ever re-keyed "
              "with no regrouping | Party IDs issued | Crosswalk rows |", "|---|---|---|---|---|---|---|"]
    for k, s in r["keys"].items():
        lines.append(f"| {k} | {s['key_changes']:,} | {s['explained_by_regrouping']:,} | "
                     f"{s['unexplained']:,} | "
                     f"{s['records_ever_rekeyed_unexplained']:,} of {s['records_at_end']:,} | "
                     f"{s['distinct_party_ids_issued']:,} | {s['crosswalk_rows']:,} |")
    h = r["history"]
    lines += ["", "## History", "",
              f"{h['rows']:,} SCD2 rows for {h['parties_ever']:,} parties "
              f"({h['current_parties']:,} current). "
              f"Audit violations: {len(h['audit_violations'])}.", "",
              "Why versions were opened: " + ", ".join(f"{k} {v:,}" for k, v in h["change_reasons"].items()),
              "", "Why versions were closed without a successor: "
              + (", ".join(f"{k} {v:,}" for k, v in h["closed_reasons"].items()) or "none"), "",
              f"Point-in-time lookups ({h['lookups']:,} party-months): an SCD1 table returns the wrong "
              + ", ".join(f"{k} for {_pct(v)}" for k, v in h["scd1_wrong_rate"].items()) + ".", "",
              "## Replay", ""]
    for rp in r["replay"]:
        lines.append(f"- Rebuilt from scratch through month {rp['month']} ({rp['parties']:,} parties): "
                     f"{'identical' if rp['identical'] else 'DIFFERENT'} to the final table read as of "
                     "that month.")
    lines += ["", f"Run time: {r['seconds']} s", ""]
    return "\n".join(lines)
