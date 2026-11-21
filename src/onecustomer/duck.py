"""DuckDB engine: the same blocking and comparison levels, expressed as SQL.

The pure-Python comparator (``match.ComparisonCache``) is the reference. This engine must produce
exactly the same candidate pairs and comparison vectors, which ``tests/test_duck.py`` checks, so the
match weights, links and clusters are identical whichever engine runs. Only the speed differs:
blocking becomes self-joins and comparisons become ``CASE`` expressions, both executed in parallel
by DuckDB, as Splink does.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from .match import BLOCKING_RULES, COMPARE_COLUMNS, MAX_BLOCK

_COLUMNS = sorted({*COMPARE_COLUMNS, *(c for cols in BLOCKING_RULES.values() for c in cols
                                       if not c.startswith("_"))})

_GAMMA_SQL = """
SELECT
  CASE WHEN l.std_nid IS NULL OR r.std_nid IS NULL THEN 0
       WHEN l.std_nid = r.std_nid THEN 3
       WHEN damerau_levenshtein(l.std_nid, r.std_nid) <= 1 THEN 2
       ELSE 1 END AS nid,
  CASE WHEN l.std_dob IS NULL OR r.std_dob IS NULL THEN 0
       WHEN l.std_dob = r.std_dob THEN 3
       WHEN split_part(l.std_dob, '-', 1) = split_part(r.std_dob, '-', 1)
        AND split_part(l.std_dob, '-', 2) = split_part(r.std_dob, '-', 3)
        AND split_part(l.std_dob, '-', 3) = split_part(r.std_dob, '-', 2) THEN 2
       WHEN (split_part(l.std_dob, '-', 1) <> split_part(r.std_dob, '-', 1))::INT
          + (split_part(l.std_dob, '-', 2) <> split_part(r.std_dob, '-', 2))::INT
          + (split_part(l.std_dob, '-', 3) <> split_part(r.std_dob, '-', 3))::INT = 1 THEN 2
       ELSE 1 END AS dob,
  CASE WHEN l.std_first_canon IS NULL OR r.std_first_canon IS NULL THEN 0
       WHEN l.std_first_canon = r.std_first_canon THEN 3
       WHEN coalesce(l.std_first = r.std_middle, FALSE) OR coalesce(r.std_first = l.std_middle, FALSE) THEN 2
       WHEN coalesce(l.std_first = r.std_surname AND r.std_first = l.std_surname, FALSE) THEN 2
       WHEN jaro_winkler_similarity(l.std_first, r.std_first) >= 0.92 THEN 2
       ELSE 1 END AS first,
  CASE WHEN l.std_surname IS NULL OR r.std_surname IS NULL THEN 0
       WHEN l.std_surname = r.std_surname THEN 3
       WHEN list_has_any(list_filter(string_split(l.std_surname, '-'), lambda x: x <> ''),
                         list_filter(string_split(r.std_surname, '-'), lambda x: x <> '')) THEN 2
       WHEN coalesce(l.std_first = r.std_surname AND r.std_first = l.std_surname, FALSE) THEN 2
       WHEN jaro_winkler_similarity(l.std_surname, r.std_surname) >= 0.92 THEN 2
       ELSE 1 END AS surname,
  CASE WHEN l.std_phone IS NULL OR r.std_phone IS NULL THEN 0
       WHEN l.std_phone = r.std_phone THEN 2 ELSE 1 END AS phone,
  CASE WHEN l.std_email IS NULL OR r.std_email IS NULL THEN 0
       WHEN l.std_email = r.std_email THEN 2 ELSE 1 END AS email,
  CASE WHEN l.std_address IS NULL OR r.std_address IS NULL THEN 0
       WHEN l.std_address = r.std_address THEN
            CASE WHEN l.std_postal IS NOT DISTINCT FROM r.std_postal THEN 3 ELSE 2 END
       WHEN l.std_postal IS NOT DISTINCT FROM r.std_postal
        AND jaro_winkler_similarity(l.std_address, r.std_address) >= 0.9 THEN 2
       ELSE 1 END AS address
FROM pairs p
JOIN recs l ON l._pos = p.a
JOIN recs r ON r._pos = p.b
ORDER BY p._k
"""


class DuckDBEngine:
    """Drop-in replacement for ``ComparisonCache``: ``pairs(df, rules)`` and ``compare(df, pairs)``."""

    def __init__(self, threads: int | None = None):
        self.con = duckdb.connect()
        self.con.execute("SET enable_progress_bar = false")
        if threads:
            self.con.execute(f"SET threads = {int(threads)}")
        self._registered: int | None = None

    def _register(self, df: pd.DataFrame) -> None:
        if self._registered == id(df):
            return
        recs = pd.DataFrame({"_pos": np.arange(len(df), dtype=np.int64)})
        for col in _COLUMNS:
            recs[col] = df[col].astype(object).where(df[col].notna(), None).astype("string")
        recs["_surname_initial"] = recs["std_surname"].str[:1]
        recs["_birth_year"] = recs["std_dob"].str[:4]
        self.con.register("recs_df", recs)
        self.con.execute("CREATE OR REPLACE TABLE recs AS SELECT * FROM recs_df")
        self.con.unregister("recs_df")
        self._registered = id(df)

    def pairs(self, df: pd.DataFrame, rules: dict[str, tuple[str, ...]] | None = None,
              max_block: int = MAX_BLOCK) -> pd.DataFrame:
        self._register(df)
        rules = BLOCKING_RULES if rules is None else rules
        selects = []
        for cols in rules.values():
            cols_sql = ", ".join(cols)
            not_null = " AND ".join(f"{c} IS NOT NULL" for c in cols)
            join = " AND ".join(f"l.{c} = r.{c}" for c in cols)
            selects.append(f"""
                SELECT l._pos AS a, r._pos AS b
                FROM (SELECT _pos, {cols_sql}, count(*) OVER (PARTITION BY {cols_sql}) AS n
                      FROM recs WHERE {not_null}) l
                JOIN (SELECT _pos, {cols_sql}, count(*) OVER (PARTITION BY {cols_sql}) AS n
                      FROM recs WHERE {not_null}) r
                  ON {join} AND l._pos < r._pos
                WHERE l.n BETWEEN 2 AND {int(max_block)}""")
        sql = " UNION ".join(selects) + " ORDER BY a, b"
        return self.con.execute(sql).df().astype({"a": np.int64, "b": np.int64})

    def compare(self, df: pd.DataFrame, pairs: pd.DataFrame) -> np.ndarray:
        self._register(df)
        frame = pd.DataFrame({"_k": np.arange(len(pairs), dtype=np.int64),
                              "a": pairs["a"].to_numpy(dtype=np.int64),
                              "b": pairs["b"].to_numpy(dtype=np.int64)})
        self.con.register("pairs", frame)
        try:
            out = self.con.execute(_GAMMA_SQL).fetchnumpy()
        finally:
            self.con.unregister("pairs")
        return np.column_stack([out[c] for c in ("nid", "dob", "first", "surname", "phone", "email",
                                                 "address")]).astype(np.int8)
