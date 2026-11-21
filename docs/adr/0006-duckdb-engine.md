# ADR 0006: A DuckDB engine checked against a pure-Python reference

**Status:** accepted

## Context

Blocking and comparison ran as Python loops. That is fine for 15,000 records, but a bank's book is
millions, and a reviewer for a data engineering role will ask how it scales. Splink answers this by
generating SQL for blocking and comparison and running it on DuckDB or Spark.

## Decision

Add `duck.DuckDBEngine`. Blocking rules become self-joins with a window count for the block-size cap,
and each comparison level becomes a `CASE` expression using DuckDB's `jaro_winkler_similarity` and
`damerau_levenshtein`. Training, scoring, clustering, keys and history are shared.

Keep the Python comparator as the reference. `tests/test_duck.py` requires both engines to produce
the same candidate pairs, the same comparison vector for every blocked pair and for random pairs, and
the same parties. Because the vectors are identical, the weights and clusters are too, so every
figure in the README holds whichever engine runs.

## Consequences

One monthly load, end to end, on 2 CPU cores (`onecustomer scale`, results in `reports/scale.json`):

| Records | Candidate pairs | Pure Python | DuckDB | Peak memory (Python / DuckDB) |
|---|---|---|---|---|
| 14,946 | 21,891 | 1.3 s | 1.1 s | 232 / 294 MB |
| 149,168 | 379,883 | 14.2 s | 7.0 s | 1,058 / 762 MB |
| 1,044,396 | 9,785,959 | 150.3 s | 50.3 s | 6,021 / 3,712 MB |

At a million records both engines give precision 99.996% and recall 99.65%, identical to each
other.

- Candidate pairs grow faster than records (about 9 per record at a million), because more blocks
  fill up towards the 50-record cap. Comparisons, not rows, drive run time, as Splink's authors note.
- Standardisation (9 s at a million) still runs in Python, and is now the largest share of the
  DuckDB run that does not parallelise.
- The synthetic generator is the practical limit on size in this repository, not the matcher.
