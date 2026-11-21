# ADR 0003: Carry party keys forward and publish a crosswalk

**Status:** accepted

## Context

The matcher re-clusters the whole book after every load. Clusters have no identity of their own.
Everything downstream (a feature store, collections, regulatory returns, model monitoring) joins on
`party_id`. If the ID changes when nothing about the customer changed, those systems lose the
customer's history as surely as if the match were wrong.

Two common approaches both churn:

- **Renumber every load** (truncate and reload into a table with an identity column). Any new or
  merged cluster that sorts earlier shifts every ID after it.
- **Use the smallest source key as the ID.** Stable until a record with a smaller key joins, which
  happens on every cross-sell from the system whose keys sort first.

## Decision

Carry IDs forward by overlap. Each new cluster takes the ID of the previous party it shares most
records with. Ties go to the older party. Clusters that inherit nothing get a new ID.

Every ID that stops being used gets a crosswalk row:

- `merged_into`: all its records went to one surviving party.
- `split_into`: its records went to several parties; the row points at the one that took most.
- `split_from`: a new ID created from part of an existing party points back to it.

## Consequences

Over 24 loads, no record's party ID changed unless its links changed. All 22 key changes came from
a real merge or split, and every retired ID has a crosswalk row that leads to a live party (both
checked by `onecustomer audit`). Renumbering changed 74,879 keys with no change in links; the
smallest-key approach changed 1,080.

Splink's own clusters take the smallest record ID as the cluster ID, so they behave like the
smallest-key approach here, and its maintainers note that incremental clustering is left to the
user ([discussion #869](https://github.com/moj-analytical-services/splink/discussions/869)). The UK
Ministry of Justice describes building a separate stable-ID step around Splink in production
([blog, January 2026](https://moj-analytical-services.github.io/splink/blog/2026/01/29/running-splink-in-production.html)).
Zingg offers persistent IDs only in its Enterprise edition. This ADR is that layer, in the open.

Consumers that stored an old ID resolve it through the crosswalk. Following `merged_into` and
`split_into` rows always ends at a live party.
