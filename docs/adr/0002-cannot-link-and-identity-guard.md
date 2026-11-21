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
2. **Identity guard.** A link is rejected unless the first name or the ID agrees at least partly.
   Contact details show that people share a household, not that they are the same person.

## Consequences

On the 10,000-person run (December 2025 load):

| | Customers split | Customers falsely merged | Twin pairs merged |
|---|---|---|---|
| Weights only | 4 | 423 | 66 of 77 |
| + cannot-link | 4 | 40 | 5 of 77 |
| + identity guard | 13 | 4 | 0 of 77 |

The guard trades 9 more split customers for 36 fewer false merges. That is the intended trade.

What is left:

- **4 customers in 2 false merges.** Both are a parent and child with the same first name, surname,
  address and phone number, where the parent's record has no ID. A different date of birth costs
  about 5 bits; a shared phone and address add about 27. A rule that refuses links when birth dates
  differ by decades would catch these. It is not added here because it would also refuse real
  matches whose date of birth was captured wrongly.
- **13 split customers.** In every case one record has no trusted ID, and in most the first name is
  also mistyped (GERAHRD, LUDKY, YUUSUF). These are the cases a data steward queue should review.
