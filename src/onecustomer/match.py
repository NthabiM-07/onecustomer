"""Record linkage: blocking, comparison vectors, Fellegi-Sunter weights by EM, constrained clustering.

Three strategies share the same blocking and clustering code:

- ``id_exact``: link two records only when they carry the same valid national ID.
- ``rules``: a typical deterministic cascade (same ID, or same name and birth date, or same phone and
  surname, or same email), chained with no constraints.
- ``fellegi_sunter``: probabilistic weights learnt without labels by expectation-maximisation, links
  above a posterior threshold, then clustering that refuses to put two different trusted IDs in one
  party (a cannot-link constraint).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler

from .standardise import surname_tokens

FIELDS = ("nid", "dob", "first", "surname", "phone", "email", "address")
# Number of non-missing levels per field (level 0 always means "missing on one side").
LEVELS = {"nid": 3, "dob": 3, "first": 3, "surname": 3, "phone": 2, "email": 2, "address": 3}

BLOCKING_RULES: dict[str, tuple[str, ...]] = {
    "national_id": ("std_nid",),
    "phone": ("std_phone",),
    "email": ("std_email",),
    "dob_surname_initial": ("std_dob", "_surname_initial"),
    "dob_first": ("std_dob", "std_first_canon"),
    "name_birth_year": ("std_first_canon", "std_surname", "_birth_year"),
    "dob_postal": ("std_dob", "std_postal"),
    "address": ("std_postal", "std_address"),
}
MAX_BLOCK = 50  # larger blocks (a call-centre number, a placeholder email) carry no information

COMPARE_COLUMNS = ["std_nid", "std_dob", "std_first", "std_first_canon", "std_middle", "std_surname",
                   "std_phone", "std_email", "std_address", "std_postal"]


# ------------------------------------------------------------------------------------- blocking


def candidate_pairs(df: pd.DataFrame, max_block: int = MAX_BLOCK,
                    rules: dict[str, tuple[str, ...]] | None = None) -> pd.DataFrame:
    """Unique pairs of row positions ``(a, b)`` with ``a < b`` that share at least one blocking key."""
    rules = BLOCKING_RULES if rules is None else rules
    work = pd.DataFrame({
        "_pos": np.arange(len(df)),
        "_surname_initial": df["std_surname"].str[:1],
        "_birth_year": df["std_dob"].str[:4],
    })
    for col in {c for cols in rules.values() for c in cols if not c.startswith("_")}:
        work[col] = df[col].to_numpy()
    found = []
    for cols in rules.values():
        sub = work.dropna(subset=list(cols))
        if sub.empty:
            continue
        key = sub.groupby(list(cols), sort=False).ngroup()
        sizes = key.map(key.value_counts())
        sub = pd.DataFrame({"k": key, "_pos": sub["_pos"]})[(sizes >= 2) & (sizes <= max_block)]
        joined = sub.merge(sub, on="k", suffixes=("_a", "_b"))
        joined = joined[joined["_pos_a"] < joined["_pos_b"]]
        found.append(joined[["_pos_a", "_pos_b"]].to_numpy())
    if not found:
        return pd.DataFrame({"a": [], "b": []}, dtype=int)
    pairs = np.unique(np.vstack(found), axis=0)
    return pd.DataFrame({"a": pairs[:, 0], "b": pairs[:, 1]})


# ------------------------------------------------------------------------------------ comparing


def _dob_level(a: str, b: str) -> int:
    if a == b:
        return 3
    ya, ma, da = a.split("-")
    yb, mb, db = b.split("-")
    if ya == yb and ma == db and da == mb:
        return 2  # day and month swapped
    return 2 if (ya != yb) + (ma != mb) + (da != db) == 1 else 1


def _first_level(row_a: tuple, row_b: tuple) -> int:
    first_a, canon_a, middle_a = row_a[2], row_a[3], row_a[4]
    first_b, canon_b, middle_b = row_b[2], row_b[3], row_b[4]
    if canon_a is None or canon_b is None:
        return 0
    if canon_a == canon_b:
        return 3
    if first_a == middle_b or first_b == middle_a:
        return 2
    if _swapped(row_a, row_b):
        return 2
    if JaroWinkler.normalized_similarity(first_a, first_b) >= 0.92:
        return 2
    return 1


def _swapped(row_a: tuple, row_b: tuple) -> bool:
    """First name and surname captured the wrong way round on one side."""
    return (row_a[2] is not None and row_a[2] == row_b[5]
            and row_b[2] is not None and row_b[2] == row_a[5])


def _surname_level(row_a: tuple, row_b: tuple) -> int:
    a, b = row_a[5], row_b[5]
    if a is None or b is None:
        return 0
    if a == b:
        return 3
    if surname_tokens(a) & surname_tokens(b) or _swapped(row_a, row_b):
        return 2
    return 2 if JaroWinkler.normalized_similarity(a, b) >= 0.92 else 1


def compare_rows(ra: tuple, rb: tuple) -> tuple[int, ...]:
    """Comparison vector for two rows laid out as ``COMPARE_COLUMNS``."""
    nid_a, nid_b = ra[0], rb[0]
    if nid_a is None or nid_b is None:
        nid = 0
    elif nid_a == nid_b:
        nid = 3
    else:
        nid = 2 if DamerauLevenshtein.distance(nid_a, nid_b) <= 1 else 1
    dob = 0 if ra[1] is None or rb[1] is None else _dob_level(ra[1], rb[1])
    first = _first_level(ra, rb)
    surname = _surname_level(ra, rb)
    phone = 0 if ra[6] is None or rb[6] is None else (2 if ra[6] == rb[6] else 1)
    email = 0 if ra[7] is None or rb[7] is None else (2 if ra[7] == rb[7] else 1)
    if ra[8] is None or rb[8] is None:
        address = 0
    elif ra[8] == rb[8]:
        address = 3 if ra[9] == rb[9] else 2
    else:
        address = 2 if ra[9] == rb[9] and JaroWinkler.normalized_similarity(ra[8], rb[8]) >= 0.9 else 1
    return nid, dob, first, surname, phone, email, address


@dataclass
class ComparisonCache:
    """Comparison vectors keyed by the two record versions, so unchanged pairs are compared once."""

    store: dict[tuple, tuple[int, ...]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def pairs(self, df: pd.DataFrame, rules: dict[str, tuple[str, ...]] | None = None) -> pd.DataFrame:
        return candidate_pairs(df, rules=rules)

    def compare(self, df: pd.DataFrame, pairs: pd.DataFrame) -> np.ndarray:
        rows = list(df[COMPARE_COLUMNS].astype(object).where(df[COMPARE_COLUMNS].notna(), None)
                    .itertuples(index=False, name=None))
        ids = list(zip(df["record_key"], df["load_month"], strict=True))
        out = np.empty((len(pairs), len(FIELDS)), dtype=np.int8)
        for n, (a, b) in enumerate(zip(pairs["a"].to_numpy(), pairs["b"].to_numpy(), strict=True)):
            key = (ids[a], ids[b])
            gamma = self.store.get(key)
            if gamma is None:
                gamma = compare_rows(rows[a], rows[b])
                self.store[key] = gamma
                self.misses += 1
            else:
                self.hits += 1
            out[n] = gamma
        return out


# ---------------------------------------------------------------------------- Fellegi-Sunter EM


@dataclass
class FSModel:
    m: dict[str, np.ndarray]  # index 1..L used; index 0 (missing) unused
    u: dict[str, np.ndarray]
    prior: float
    iterations: int
    # Term frequencies for exact agreement: field -> {standardised value: share of records}
    tf: dict[str, dict[str, float]] = field(default_factory=dict)

    def level_weights(self) -> dict[str, np.ndarray]:
        """log2(m/u) per field and level; level 0 (missing) carries no evidence."""
        out = {}
        for f in FIELDS:
            w = np.zeros(LEVELS[f] + 1)
            w[1:] = np.log2(self.m[f][1:] / self.u[f][1:])
            out[f] = w
        return out

    def tf_adjustment(self, gamma: np.ndarray, values: dict[str, np.ndarray] | None) -> dict[str, np.ndarray]:
        """Extra weight for exact agreement on a rare value, less for a common one.

        Following Splink, the u of exact agreement is replaced by the share of records holding that
        value: agreeing on DLAMINI is weaker evidence than agreeing on a surname held by 1 in 5,000.
        """
        out: dict[str, np.ndarray] = {}
        if not values:
            return out
        for f, freq in self.tf.items():
            if f not in values:
                continue
            k = FIELDS.index(f)
            exact = gamma[:, k] == LEVELS[f]
            share = np.array([freq.get(v, np.nan) if e else np.nan for v, e in zip(values[f], exact,
                                                                                    strict=True)])
            ratio = self.u[f][LEVELS[f]] / np.nan_to_num(share, nan=1.0)
            out[f] = np.where(np.isnan(share), 0.0, np.log2(ratio))
        return out

    def match_weight(self, gamma: np.ndarray, values: dict[str, np.ndarray] | None = None) -> np.ndarray:
        lw = self.level_weights()
        total = np.full(len(gamma), np.log2(self.prior / (1 - self.prior)))
        for k, f in enumerate(FIELDS):
            total += lw[f][gamma[:, k]]
        for adj in self.tf_adjustment(gamma, values).values():
            total += adj
        return total

    def posterior(self, gamma: np.ndarray, values: dict[str, np.ndarray] | None = None) -> np.ndarray:
        return 1.0 / (1.0 + np.exp2(-self.match_weight(gamma, values)))

    def as_dict(self) -> dict:
        return {
            "prior": round(float(self.prior), 6),
            "iterations": self.iterations,
            "fields": {f: {"m": [round(float(x), 5) for x in self.m[f][1:]],
                           "u": [round(float(x), 5) for x in self.u[f][1:]]} for f in FIELDS},
            "tf_fields": sorted(self.tf),
        }


TF_COLUMNS = {"surname": "std_surname", "first": "std_first_canon"}


def term_frequencies(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    out = {}
    for f, col in TF_COLUMNS.items():
        counts = df[col].dropna().value_counts()
        out[f] = (counts / counts.sum()).to_dict()
    return out


def pair_values(df: pd.DataFrame, pairs: pd.DataFrame) -> dict[str, np.ndarray]:
    """Side-a values of the term-frequency fields for each pair (equal to side b when they agree)."""
    a = pairs["a"].to_numpy()
    return {f: df[col].to_numpy(dtype=object)[a] for f, col in TF_COLUMNS.items()}


def estimate_u(df: pd.DataFrame, n_pairs: int = 100_000, seed: int = 0, engine=None) -> dict[str, np.ndarray]:
    """u-probabilities from random record pairs, which are almost all non-matches.

    Estimating u this way (rather than letting EM find it) is what keeps EM honest: blocked pairs are
    mostly matches, and without a fixed u, EM tends to relabel "IDs differ" as the non-match class.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    a = rng.integers(0, n, size=n_pairs)
    b = rng.integers(0, n, size=n_pairs)
    keep = a != b
    engine = engine if engine is not None else ComparisonCache()
    gamma = engine.compare(df, pd.DataFrame({"a": a[keep], "b": b[keep]}))
    u = {}
    for k, f in enumerate(FIELDS):
        g = gamma[:, k]
        counts = np.array([(g == level).sum() for level in range(1, LEVELS[f] + 1)], dtype=float)
        u[f] = np.r_[0.0, (counts + 1.0) / (counts.sum() + LEVELS[f])]  # add-one smoothing
    return u


def _patterns(gamma: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distinct comparison vectors and how often each occurs.

    Each vector is packed into one integer (base 4, one digit per field), which is far faster than
    sorting rows. At most 4**7 = 16,384 patterns exist, so EM runs over patterns, not pairs.
    """
    if len(gamma) == 0:
        return np.empty((0, len(FIELDS)), dtype=np.int8), np.empty(0)
    base = 4 ** np.arange(gamma.shape[1] - 1, -1, -1, dtype=np.int64)  # first field most significant
    codes, counts = np.unique(gamma.astype(np.int64) @ base, return_counts=True)
    patterns = ((codes[:, None] // base) % 4).astype(np.int8)
    return patterns, counts.astype(float)


def fit_em(gamma: np.ndarray, u: dict[str, np.ndarray], max_iter: int = 500, tol: float = 1e-8,
           prior: float = 0.5, eps: float = 1e-6) -> FSModel:
    """Estimate m and the match prior on blocked pairs by EM, holding u fixed.

    Fields are assumed conditionally independent given match status (the Fellegi-Sunter model).
    """
    patterns, counts = _patterns(gamma)
    m = {}
    for f in FIELDS:
        m[f] = np.r_[0.0, np.linspace(0.05, 1.0, LEVELS[f]) ** 3]  # start: agreement is likely
        m[f][1:] /= m[f][1:].sum()
    u = {f: v.copy() for f, v in u.items()}
    it = 0
    for it in range(1, max_iter + 1):  # noqa: B007
        log_m = np.full(len(patterns), np.log(prior))
        log_u = np.full(len(patterns), np.log(1 - prior))
        for k, f in enumerate(FIELDS):
            g = patterns[:, k]
            present = g > 0
            log_m[present] += np.log(m[f][g[present]])
            log_u[present] += np.log(u[f][g[present]])
        w = 1.0 / (1.0 + np.exp(np.clip(log_u - log_m, -700, 700)))
        new_prior = min(max(float((counts * w).sum() / counts.sum()), eps), 1 - eps)
        delta = abs(new_prior - prior)
        prior = new_prior
        for k, f in enumerate(FIELDS):
            g = patterns[:, k]
            present = g > 0
            denom = (counts * w)[present].sum()
            for level in range(1, LEVELS[f] + 1):
                # Add-one smoothing: a level never seen among matches is strong evidence, not proof.
                new_m = ((counts * w)[g == level].sum() + 1.0) / (denom + LEVELS[f])
                delta = max(delta, abs(new_m - m[f][level]))
                m[f][level] = new_m
        if delta < tol:
            break
    return FSModel(m, u, prior, it)


# A training session blocks on one rule and estimates m for every field *except* the ones the rule
# forces to agree. Each session's blocked pairs therefore behave like random pairs on the fields it
# does estimate, which is what holding u fixed assumes.
MIN_SESSION_PAIRS = 50
TRAINING_SESSIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "dob": (("std_dob",), ("dob",)),
    "phone": (("std_phone",), ("phone",)),
    "name": (("std_first_canon", "std_surname"), ("first", "surname")),
}


def train(df: pd.DataFrame, cache: ComparisonCache | None = None, seed: int = 0,
          tf_adjust: bool = True) -> FSModel:
    """Fit a Fellegi-Sunter model without labels.

    1. u from random record pairs.
    2. m by EM, once per training session, with u fixed and the session's blocking fields excluded.
       Each field's m is the average over the sessions that estimated it.
    3. The prior (probability that two random records match) from each session's EM prior, scaled by
       how many pairs that session blocked and by the share of matches its rule can catch (that
       recall is measured in the *other* sessions). The median across sessions is used.
    """
    cache = cache or ComparisonCache()
    u = estimate_u(df, seed=seed, engine=cache)
    index = {f: k for k, f in enumerate(FIELDS)}
    m_estimates: dict[str, list[np.ndarray]] = {f: [] for f in FIELDS}
    sessions = {}
    for name, (cols, excluded) in TRAINING_SESSIONS.items():
        pairs = cache.pairs(df, rules={name: cols})
        if len(pairs) < MIN_SESSION_PAIRS:
            continue  # e.g. no phone numbers in this source: nothing to learn from this session
        gamma = cache.compare(df, pairs)
        masked = gamma.copy()
        for f in excluded:
            masked[:, index[f]] = 0
        fitted = fit_em(masked, u)
        for f in FIELDS:
            if f not in excluded:
                m_estimates[f].append(fitted.m[f])
        sessions[name] = (len(pairs), fitted, gamma, fitted.posterior(masked))
    # A field no session could estimate (absent from the data) keeps a neutral m equal to u.
    m = {f: np.mean(m_estimates[f], axis=0) if m_estimates[f] else u[f].copy() for f in FIELDS}
    match_counts = []
    for name, (n_pairs, fitted, _, _) in sessions.items():
        excluded = TRAINING_SESSIONS[name][1]
        rates = []
        for other, (_, _, gamma, w) in sessions.items():
            if other == name or set(excluded) & set(TRAINING_SESSIONS[other][1]):
                continue
            agree = np.all([gamma[:, index[f]] == LEVELS[f] for f in excluded], axis=0)
            rates.append(float((w * agree).sum() / w.sum()))
        if rates and np.mean(rates) > 0:
            match_counts.append(fitted.prior * n_pairs / np.mean(rates))
    n = len(df)
    prior = float(np.median(match_counts)) / (n * (n - 1) / 2)
    tf = term_frequencies(df) if tf_adjust else {}
    return FSModel(m, u, prior, sum(s[1].iterations for s in sessions.values()), tf)


# ------------------------------------------------------------------------------------ clustering


def cluster(n: int, a: np.ndarray, b: np.ndarray, weight: np.ndarray,
            trusted_id: np.ndarray | None = None) -> np.ndarray:
    """Union-find over accepted links, strongest first.

    With ``trusted_id`` (one value or None per row), two groups are never joined if they hold
    different trusted IDs. Returns a label per row (the root's row position).
    """
    parent = np.arange(n)
    ids = list(trusted_id) if trusted_id is not None else [None] * n

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for k in np.argsort(-weight, kind="stable"):
        ra, rb = find(int(a[k])), find(int(b[k]))
        if ra == rb:
            continue
        ia, ib = ids[ra], ids[rb]
        if trusted_id is not None and ia is not None and ib is not None and ia != ib:
            continue
        keep, drop = (ra, rb) if ra < rb else (rb, ra)
        parent[drop] = keep
        ids[keep] = ia if ia is not None else ib
    return np.array([find(i) for i in range(n)])


# ------------------------------------------------------------------------------------ strategies

STRATEGIES = ("id_exact", "rules", "fellegi_sunter")


@dataclass
class MatchResult:
    labels: np.ndarray  # cluster label per row of the snapshot
    pairs: pd.DataFrame
    gamma: np.ndarray
    model: FSModel | None


def identity_ok(gamma: np.ndarray) -> np.ndarray:
    """The identity guard: a link needs the person's own identity to agree, not just their household's.

    Either the ID agrees (exactly or within one keystroke), or both the first name and the date of
    birth agree at least partly. Shared surname, address, phone or email are what household members
    have in common, so on their own they never justify a link.
    """
    col = {f: k for k, f in enumerate(FIELDS)}
    id_agrees = gamma[:, col["nid"]] >= 2
    name_agrees = gamma[:, col["first"]] >= 2
    dob_agrees_or_missing = (gamma[:, col["dob"]] >= 2) | (gamma[:, col["dob"]] == 0)
    return id_agrees | (name_agrees & dob_agrees_or_missing)


def link(df: pd.DataFrame, strategy: str, cache: ComparisonCache | None = None,
         threshold: float = 0.9, model: FSModel | None = None, constrained: bool = True,
         identity_guard: bool = True) -> MatchResult:
    """Cluster the rows of one standardised snapshot.

    ``cache`` is the comparison engine: ``ComparisonCache`` (pure Python, the reference) or
    ``duck.DuckDBEngine`` (the same comparisons as SQL). Both give identical results.

    For ``fellegi_sunter``, ``constrained`` turns on the cannot-link rule for trusted IDs, and
    ``identity_guard`` refuses any link where neither the first name nor the ID agrees, however much
    contact detail the two records share. Household members share phones and addresses; that is
    evidence of a household, not of one person.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {STRATEGIES}")
    cache = cache or ComparisonCache()
    pairs = cache.pairs(df)
    gamma = cache.compare(df, pairs) if len(pairs) else np.empty((0, len(FIELDS)), dtype=np.int8)
    a, b = pairs["a"].to_numpy(), pairs["b"].to_numpy()
    col = {f: k for k, f in enumerate(FIELDS)}
    valid = df["nid_valid"].to_numpy()
    same_valid_id = (gamma[:, col["nid"]] == 3) & valid[a] & valid[b]
    if strategy == "id_exact":
        labels = cluster(len(df), a[same_valid_id], b[same_valid_id], np.ones(same_valid_id.sum()))
        return MatchResult(labels, pairs, gamma, None)
    if strategy == "rules":
        same_name_dob = ((gamma[:, col["first"]] == 3) & (gamma[:, col["surname"]] == 3)
                         & (gamma[:, col["dob"]] == 3))
        accept = (same_valid_id | same_name_dob
                  | ((gamma[:, col["phone"]] == 2) & (gamma[:, col["surname"]] == 3))
                  | (gamma[:, col["email"]] == 2))
        labels = cluster(len(df), a[accept], b[accept], np.ones(accept.sum()))
        return MatchResult(labels, pairs, gamma, None)
    model = model or train(df, cache)
    values = pair_values(df, pairs)
    accept = model.posterior(gamma, values) >= threshold
    if identity_guard:
        accept &= identity_ok(gamma)
    trusted = np.where(df["nid_trusted"].to_numpy(), df["std_nid"].to_numpy(), None) if constrained else None
    weights = model.match_weight(gamma, values)
    labels = cluster(len(df), a[accept], b[accept], weights[accept], trusted)
    return MatchResult(labels, pairs, gamma, model)
