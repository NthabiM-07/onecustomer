"""Month-by-month runs: match every load, key the clusters, build the history."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from . import history, keys
from .generate import N_MONTHS, World, snapshot
from .match import ComparisonCache, link
from .standardise import standardise


@dataclass
class Run:
    clusters: dict[int, pd.DataFrame]  # month -> record_key, cluster
    models: dict[int, dict] = field(default_factory=dict)
    seconds: dict[int, float] = field(default_factory=dict)
    assignments: pd.DataFrame | None = None
    crosswalk: pd.DataFrame | None = None
    history: pd.DataFrame | None = None


def match_months(std: pd.DataFrame, months: int = N_MONTHS, strategy: str = "fellegi_sunter",
                 **link_kwargs) -> Run:
    """Re-match the whole book after every monthly load, using only data loaded so far.

    The Fellegi-Sunter model is re-trained each month on that month's snapshot, so no month ever
    uses parameters learnt from later data.
    """
    cache = ComparisonCache()
    run = Run(clusters={})
    for month in range(1, months + 1):
        start = time.perf_counter()
        snap = snapshot(std, month)
        result = link(snap, strategy, cache=cache, **link_kwargs)
        run.clusters[month] = pd.DataFrame({"record_key": snap["record_key"].to_numpy(),
                                            "cluster": result.labels})
        if result.model is not None:
            run.models[month] = result.model.as_dict()
        run.seconds[month] = time.perf_counter() - start
    return run


def run(world: World, months: int = N_MONTHS, keying: str = "stable", **link_kwargs) -> Run:
    """Match, key and historise ``months`` loads of ``world``."""
    std = standardise(world.versions)
    result = match_months(std, months, **link_kwargs)
    result.assignments, result.crosswalk = keys.assign(result.clusters, keying)
    result.history = history.build(std[std["load_month"] <= months], result.assignments, result.crosswalk)
    return result
