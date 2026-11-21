# ADR 0004: An SCD2 golden record with column-level lineage

**Status:** accepted

## Context

Credit decisions are reviewed long after they are made. A reviewer, an auditor or the regulator
asks what the bank knew about the customer *on the decision date*, and where each fact came from.
BCBS 239 expects risk data to be traceable to its source. An overwrite (SCD1) table can answer
neither question.

## Decision

- **Survivorship is per attribute.** Identity fields (ID, birth date, first and middle names) come
  from the KYC-ranked record: trusted ID first, then the branch-captured loans platform. Surname
  comes from the record where it was most recently *updated* after onboarding, because a marriage
  reaches one system before the other. The onboarding capture itself does not count: an early
  version used capture month as recency, and every newly onboarded duplicate (typos included)
  overrode the KYC surname. Contact details come from the record where they changed most recently, with
  ties going to the cards app, which customers maintain themselves. Exposure is summed.
- **Values are copied, not invented.** Every golden value is taken from one source record, and the
  `lineage` column records which one for each attribute. Values are shown in one canonical format
  (title case, street types spelled out). Without that, "69 Rivonia Rd" on cards and "69 RIVONIA
  ROAD" on loans opened a new version whenever the winning record changed, although nothing about
  the customer had.
- **Type 2 history.** A new version opens when any golden attribute or the member record set
  changes. `change_reason` says what changed. Closing a version only sets `valid_to`; earlier rows
  are never rewritten. `as_of(month)` returns the table as it stood after that month's load.

## Consequences

- An SCD1 table answers 12.7% of point-in-time address lookups wrongly, and 8.6% of phone lookups,
  over 206,508 party-months.
- `onecustomer replay --month M` rebuilds the history from scratch using only loads up to M and
  compares it with the saved table read as of M. They match exactly, which shows that later loads
  never rewrote earlier versions.
- History is kept at monthly load grain. Intra-month changes are not visible, which matches how
  the sources deliver data.
