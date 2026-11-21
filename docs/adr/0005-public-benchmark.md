# ADR 0005: Benchmark on public data, and keep the first run on record

**Status:** accepted

## Context

Every result in the first version came from data this repository generated. The generator and the
matcher share assumptions (which typos happen, which nicknames exist), so high scores partly measure
that agreement. A reviewer cannot tell a strong method from a friendly generator.

## Decision

Run the matcher with its default settings on **FEBRL4**: two files of 5,000 synthetic Australian
person records, each record in file B a corrupted copy of one in file A, built by Christen's FEBRL
data generator and shipped with the `recordlinkage` package. Run **Splink 5** on the same data as the
baseline, trained with the recipe of Splink's FEBRL4 tutorial (prior from deterministic rules with
recall 0.8, u by random sampling, EM sessions on given name and on street number). Its comparisons
and blocking rules are this repository's choice, fixed before looking at the results and not tuned
on the labels.

The only FEBRL-specific code is the column mapping and the ID scheme: FEBRL's social security number
has no check digit, so it is never *trusted* and the cannot-link rule never fires.

Keep every step on record, including the first run:

| Step | Change | Blocking pair completeness | Recall at 0.9 |
|---|---|---|---|
| First run | Defaults as first published | 98.70% | 97.96% |
| 2 | Name swaps (first name and surname captured the wrong way round) count as partial agreement; two address blocking rules added (birth date and postal code; postal code and street) | 99.56% | 98.66% |
| 3 | Identity guard also needs the birth date to agree unless the ID agrees (prompted by father-and-son merges in the South African data, not by FEBRL) | 99.56% | 98.52% |
| 4 | Term-frequency adjustments for first names and surnames | 99.56% | 98.56% |

Precision was 100.00% at every step. Splink scored 99.22% recall at the same threshold.

## Why steps 2 and 4 are not tuning to the test set

Both changes are general: forms are filled in with names the wrong way round everywhere, and address
blocking is ordinary practice. Both were also checked on the South African data. Step 2 made it
worse at first: address blocking newly compared a father and son with the same name at the same
address, and the old guard let them merge (false merges went from 4 to 6 customers). That led to
step 3, which removed all of them. Step 4 left 3 fewer customers split there and added no merges.
Step 3 costs FEBRL 0.14 points of recall.

## What was deliberately not changed

The identity guard explains 0.48 of the 0.66-point recall gap to Splink. FEBRL's corruption model
sometimes replaces a duplicate's given name *and* its social security number and still calls it the
same person. Without the guard, onecustomer reaches 99.04%. In a bank, a different first name and a
different ID at the same address and birth date is usually a twin or a sibling, so the guard stays
(ADR 0002).

## Consequences

- FEBRL4 is now a regression test in CI (`tests/test_benchmark.py`) and a CI job reruns the full
  comparison with Splink on every push.
- FEBRL4 is easy: well-tuned Fellegi-Sunter models reach F1 of about 0.99. It tests correctness more
  than it separates methods. Harder public sets (North Carolina voters, DBLP-ACM) need downloads that
  this offline build does not make, and are listed as future work.
