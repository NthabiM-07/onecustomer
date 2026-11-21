"""Scaling benchmark: one monthly load matched at 15 thousand, 150 thousand and a million records.

Each size runs in two fresh processes, one to generate the world and one to match it, so the peak
memory reported belongs to matching alone. Both engines run the same pipeline: blocking, comparison,
training (u from 100,000 random pairs plus three EM sessions), scoring and constrained clustering.
"""

from __future__ import annotations

import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

GENERATE = """
import sys
from pathlib import Path
from onecustomer.generate import generate
generate(int(sys.argv[1]), seed=int(sys.argv[2])).save(Path(sys.argv[3]))
"""

MATCH = """
import json, sys
from onecustomer.scale import match_one
print(json.dumps(match_one(sys.argv[1], sys.argv[2])))
"""


def match_one(root: str, engine_name: str) -> dict:
    """Time every stage of matching the final load of a saved world with one engine."""
    from .evaluate import pairwise
    from .generate import load, snapshot
    from .match import ComparisonCache, cluster, identity_ok, pair_values, train
    from .standardise import standardise

    world = load(Path(root))
    raw = snapshot(world.versions, 24)
    truth = raw["record_key"].map(world.links.set_index("record_key")["person_id"]).to_numpy()
    timings = {}

    def timed(name, fn, *args, **kwargs):
        start = time.perf_counter()
        out = fn(*args, **kwargs)
        timings[name] = round(time.perf_counter() - start, 2)
        return out

    std = timed("standardise", standardise, raw)
    if engine_name == "duckdb":
        from .duck import DuckDBEngine

        engine = DuckDBEngine()
    else:
        engine = ComparisonCache()
    pairs = timed("blocking", engine.pairs, std)
    gamma = timed("comparison", engine.compare, std, pairs)
    model = timed("training", train, std, engine)

    def score_and_cluster():
        values = pair_values(std, pairs)
        weights = model.match_weight(gamma, values)
        accept = (1.0 / (1.0 + np.exp2(-weights)) >= 0.9) & identity_ok(gamma)
        trusted = np.where(std["nid_trusted"].to_numpy(), std["std_nid"].to_numpy(), None)
        a, b = pairs["a"].to_numpy(), pairs["b"].to_numpy()
        return cluster(len(std), a[accept], b[accept], weights[accept], trusted)

    labels = timed("scoring_and_clustering", score_and_cluster)
    scores = pairwise(labels, truth)
    return {
        "engine": engine_name,
        "people": len(world.people),
        "records": len(std),
        "candidate_pairs": len(pairs),
        "seconds": timings,
        "total_seconds": round(sum(timings.values()), 2),
        "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
        "precision": scores["precision"],
        "recall": scores["recall"],
    }


def benchmark(sizes: tuple[int, ...] = (10_000, 100_000, 700_000),
              engines: tuple[str, ...] = ("python", "duckdb"), seed: int = 7,
              save_to: Path | None = None) -> list[dict]:
    """Run every size with every engine. With ``save_to``, results are written after each run."""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for people in sizes:
            root = Path(tmp) / f"world_{people}"
            subprocess.run([sys.executable, "-c", GENERATE, str(people), str(seed), str(root)], check=True)
            for engine in engines:
                out = subprocess.run([sys.executable, "-c", MATCH, str(root), engine], check=True,
                                     capture_output=True, text=True)
                line = next(x for x in reversed(out.stdout.splitlines()) if x.startswith("{"))
                row = json.loads(line)
                results.append(row)
                if save_to is not None:
                    save_to.write_text(json.dumps(results, indent=2))
                print(f"{engine:>6} {row['records']:>9,} records {row['candidate_pairs']:>9,} pairs "
                      f"{row['total_seconds']:>7.1f} s {row['peak_memory_mb']:>6,} MB", flush=True)
    return results


def chart(results: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, ink_2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    colors = {"python": "#2a78d6", "duckdb": "#eb6834"}
    names = {"python": "Pure Python (reference)", "duckdb": "DuckDB SQL"}
    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor=surface)
    ax.set_facecolor(surface)
    for engine in ("python", "duckdb"):
        rows = sorted((r for r in results if r["engine"] == engine), key=lambda r: r["records"])
        if not rows:
            continue
        x = [r["records"] for r in rows]
        y = [r["total_seconds"] for r in rows]
        ax.plot(x, y, color=colors[engine], linewidth=2, marker="o", markersize=6, label=names[engine])
        ax.annotate(f"{y[-1]:.0f} s", (x[-1], y[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=ink_2)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Source records in one monthly load", color=ink_2, fontsize=9)
    ax.set_ylabel("Seconds to match", color=ink_2, fontsize=9)
    ax.tick_params(colors=ink_2, labelsize=9)
    ax.grid(color=grid, linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(grid)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=ink)
    ax.set_title("Matching one load end to end, 2 CPU cores", loc="left", color=ink, fontsize=11)
    fig.tight_layout(rect=(0, 0, 0.96, 1))
    fig.savefig(path, dpi=160, facecolor=surface)
    plt.close(fig)
