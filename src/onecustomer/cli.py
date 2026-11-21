"""Command line: ``onecustomer generate | run | experiment | lookup | audit | replay``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import history, pipeline
from .generate import N_MONTHS, generate, load

DATA = Path("data")


def _month(value: str) -> int:
    """Accept a month number (1-24) or YYYY-MM between 2024-01 and 2025-12."""
    if "-" in value:
        year, month = (int(x) for x in value.split("-")[:2])
        m = (year - 2024) * 12 + month
    else:
        m = int(value)
    if not 1 <= m <= N_MONTHS:
        raise argparse.ArgumentTypeError(f"month must be 1..{N_MONTHS} or 2024-01..2025-12, got {value}")
    return m


def _save_run(result: pipeline.Run, root: Path) -> None:
    result.history.to_parquet(root / "party_history.parquet", index=False)
    result.crosswalk.to_parquet(root / "crosswalk.parquet", index=False)
    result.assignments.to_parquet(root / "assignments.parquet", index=False)


def cmd_generate(args) -> int:
    world = generate(args.people, args.seed)
    world.save(args.data)
    print(f"{len(world.people):,} people, {world.links['record_key'].nunique():,} source records, "
          f"{len(world.versions):,} versions -> {args.data}/")
    return 0


def cmd_run(args) -> int:
    result = pipeline.run(load(args.data), months=args.months)
    _save_run(result, args.data)
    h = result.history
    print(f"{int(h['is_current'].sum()):,} current parties, {len(h):,} history rows, "
          f"{len(result.crosswalk):,} crosswalk rows -> {args.data}/party_history.parquet")
    return 0


def cmd_experiment(args) -> int:
    from .experiment import experiment

    results = experiment(load(args.data), args.out, tuple(args.replay))
    print((args.out / "report.md").read_text())
    failed = [r for r in results["replay"] if not r["identical"]] or results["history"]["audit_violations"]
    return 1 if failed else 0


def cmd_lookup(args) -> int:
    h = pd.read_parquet(args.data / "party_history.parquet")
    xref = pd.read_parquet(args.data / "crosswalk.parquet")
    key = args.key
    if not key.startswith("PTY"):
        hits = h[h["record_keys"].str.split("|").apply(lambda ks: key in ks)]
        if hits.empty:
            print(f"{key}: no party has ever held this record")
            return 1
        key = hits.sort_values("valid_from")["party_id"].iloc[-1]
    rows = h[h["party_id"] == key]
    if rows.empty:
        print(f"{key}: unknown party")
        return 1
    if args.as_of:
        rows = history.as_of(rows, args.as_of)
    cols = ["party_id", "version", "valid_from_date", "valid_to_date", "change_reason", "first_name",
            "surname", "national_id", "phone", "address_line", "city", "systems", "total_exposure"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(rows[cols].to_string(index=False))
    current = rows[rows["is_current"].astype(bool)]
    if not current.empty:
        print("\nlineage:", json.dumps(json.loads(current["lineage"].iloc[0]), indent=2))
    moves = xref[(xref["from_party"] == key) | (xref["to_party"] == key)]
    if not moves.empty:
        print("\ncrosswalk:\n" + moves.to_string(index=False))
    return 0


def cmd_audit(args) -> int:
    h = pd.read_parquet(args.data / "party_history.parquet")
    xref = pd.read_parquet(args.data / "crosswalk.parquet")
    problems = history.audit(h, xref)
    for p in problems:
        print("FAIL", p)
    if not problems:
        print(f"OK: {len(h):,} rows, {h['party_id'].nunique():,} parties, SCD2 invariants hold")
    return 1 if problems else 0


def cmd_replay(args) -> int:
    """Rebuild from scratch through one month and compare with the saved table read as of that month."""
    saved = pd.read_parquet(args.data / "party_history.parquet")
    replayed = pipeline.run(load(args.data), months=args.month).history
    cols = [*history.TRACKED, "party_id", "version", "valid_from", "lineage"]
    a = history.as_of(replayed, args.month)[cols].sort_values("party_id").reset_index(drop=True)
    b = history.as_of(saved, args.month)[cols].sort_values("party_id").reset_index(drop=True)
    a, b = a.astype(object).where(a.notna(), None), b.astype(object).where(b.notna(), None)
    same = a.shape == b.shape and bool((a.to_numpy() == b.to_numpy()).all())
    print(f"month {args.month}: {len(a):,} parties replayed, {'identical' if same else 'DIFFERENT'}")
    return 0 if same else 1


def _snapshot_and_model(data: Path, month: int):
    from .generate import snapshot
    from .match import train
    from .standardise import standardise

    snap = snapshot(standardise(load(data).versions), month)
    return snap, train(snap)


def cmd_explain(args) -> int:
    from .explain import explain_pair, render

    snap, model = _snapshot_and_model(args.data, args.month)
    print(render(explain_pair(snap, model, args.record_a, args.record_b)))
    return 0


def cmd_review(args) -> int:
    from .explain import review_queue

    snap, model = _snapshot_and_model(args.data, args.month)
    queue = review_queue(snap, model)
    queue.to_csv(args.out, index=False)
    print(f"{len(queue):,} pairs for review -> {args.out}")
    print(queue["reason"].value_counts().to_string())
    return 0


def cmd_benchmark(args) -> int:
    from . import febrl

    result = febrl.benchmark(with_splink=not args.no_splink)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "febrl4.json").write_text(json.dumps(result, indent=2))
    text = febrl.render(result)
    (args.out / "febrl4.md").write_text(text)
    print(text)
    return 0


def cmd_scale(args) -> int:
    from . import scale

    args.out.mkdir(parents=True, exist_ok=True)
    results = scale.benchmark(tuple(args.people), tuple(args.engines), save_to=args.out / "scale.json")
    scale.chart(results, args.out / "scaling.png")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="onecustomer", description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="build the synthetic world")
    g.add_argument("--people", type=int, default=10_000)
    g.add_argument("--seed", type=int, default=7)
    g.set_defaults(func=cmd_generate)
    r = sub.add_parser("run", help="match, key and historise every monthly load")
    r.add_argument("--months", type=_month, default=N_MONTHS)
    r.set_defaults(func=cmd_run)
    e = sub.add_parser("experiment", help="write reports/results.json, report.md and charts")
    e.add_argument("--out", type=Path, default=Path("reports"))
    e.add_argument("--replay", type=_month, nargs="*", default=[8, 16])
    e.set_defaults(func=cmd_experiment)
    lk = sub.add_parser("lookup", help="history of one party (party ID or source record key)")
    lk.add_argument("key")
    lk.add_argument("--as-of", type=_month)
    lk.set_defaults(func=cmd_lookup)
    a = sub.add_parser("audit", help="check SCD2 invariants and crosswalk coverage")
    a.set_defaults(func=cmd_audit)
    rp = sub.add_parser("replay", help="rebuild through one month and compare with the saved history")
    rp.add_argument("--month", type=_month, required=True)
    rp.set_defaults(func=cmd_replay)
    ex = sub.add_parser("explain", help="match-weight waterfall for two source records")
    ex.add_argument("record_a")
    ex.add_argument("record_b")
    ex.add_argument("--month", type=_month, default=N_MONTHS)
    ex.set_defaults(func=cmd_explain)
    rq = sub.add_parser("review-queue", help="pairs a data steward should label, as CSV")
    rq.add_argument("--month", type=_month, default=N_MONTHS)
    rq.add_argument("--out", type=Path, default=Path("review_queue.csv"))
    rq.set_defaults(func=cmd_review)
    bm = sub.add_parser("benchmark", help="FEBRL4 public benchmark, with Splink as a baseline")
    bm.add_argument("--out", type=Path, default=Path("reports"))
    bm.add_argument("--no-splink", action="store_true", help="skip the Splink baseline")
    bm.set_defaults(func=cmd_benchmark)
    sc = sub.add_parser("scale", help="time one load at several sizes with both engines")
    sc.add_argument("--people", type=int, nargs="+", default=[10_000, 100_000, 700_000])
    sc.add_argument("--engines", nargs="+", default=["python", "duckdb"], choices=["python", "duckdb"])
    sc.add_argument("--out", type=Path, default=Path("reports"))
    sc.set_defaults(func=cmd_scale)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
