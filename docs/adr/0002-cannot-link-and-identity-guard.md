# ADR 0002: Prefer a split customer to a merged one

**Status:** accepted

## Context

The two matching errors do not cost the same.

- A **split** customer appears as two parties. Their total exposure is understated, so an
  affordability check or a single-obligor limit sees part of their debt. This is a real risk, and
  the National Credit Act's affordability assessment depends on the full picture.
- A **false merge** puts two people in one party. One person's arrears can decline the other's
  application, collections can call the wrong person, and one customer's personal information is
  shown to another (a POPIA problem). It is also much harder to notice: nothing looks missing.

Fellegi-Sunter weights alone merge twins and household members, because shared surname, address
and phone are correlated evidence the model counts as independent.

## Decision

Two rules sit on top of the weights:

1. **Trusted-ID cannot-link.** An ID is trusted when it passes the Luhn check and its encoded birth
   date matches the captured one. Clustering joins the strongest links first and never joins two
   groups holding different trusted IDs. This blocks chaining (A links to B, B to C, so A and C
   merge) as well as direct links.
2. **Identity guard.** A link must rest on the person's own identity: either the ID agrees (exactly
   or within one keystroke), or the first name *and* the date of birth agree at least partly (a
   birth date missing on one side does not count against it). Shared surname, address, phone and
   email are what household members have in common, so on their own they never justify a link.

The first version of the guard asked only for the first name or the ID. That still merged a father
and son with the same name at the same address when the father's record had no ID: their birth
dates, decades apart, cost about 5 bits, and the shared phone and address added about 27. The birth
date requirement closed that gap.

## Consequences

On the 10,000-person run (December 2025 load):

| | Customers split | Customers falsely merged | Twin pairs merged |
|---|---|---|---|
| Weights only | 1 | 332 | 55 of 77 |
| + cannot-link | 2 | 46 | 5 of 77 |
| + identity guard | 10 | 0 | 0 of 77 |

The guard trades 8 more split customers for 46 fewer false merges. That is the intended trade. At
every posterior threshold from 0.5 to 0.999 the false merges stay at zero; only the number of split
customers moves (9 to 23).

The guard also costs recall on FEBRL4, where some duplicates had both the given name and the ID
replaced and are still counted as the same person (ADR 0005).

The 10 customers left split all have one record without a trusted ID, and most have a mistyped first
name on one side ("Kat" and "KATLEEGO"). `onecustomer review-queue` lists them, together with the
pairs the guard vetoed despite a confident score, for a data steward to label.
