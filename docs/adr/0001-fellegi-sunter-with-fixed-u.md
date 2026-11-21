# ADR 0001: Fellegi-Sunter weights, with u fixed from random pairs

**Status:** accepted

## Context

The two source systems share no key. The loans platform nearly always has a national ID; the cards
platform is missing it on about one record in six. Exact-ID matching is precise but leaves one
multi-product customer in five split across parties. Deterministic rules close that gap but merge
household members who share a phone number and surname.

We have no labelled pairs, which is the normal situation for a bank's customer master.

## Decision

Score candidate pairs with a Fellegi-Sunter model learnt without labels:

1. **u** (how often each comparison level occurs among non-matches) comes from 100,000 random
   record pairs. Almost all random pairs are non-matches, so this is a direct estimate.
2. **m** (how often each level occurs among matches) comes from expectation-maximisation with u
   held fixed. EM runs in three training sessions, each on pairs blocked by one rule (same date of
   birth, same phone, same first name and surname). Each session leaves out the fields its blocking
   rule forces to agree, so its non-matches look like random pairs on the fields it does estimate.
   Each field's m is the average over the sessions that estimated it.
3. **The prior** (probability that two random records match) is each session's EM prior, times the
   number of pairs it blocked, divided by its rule's recall. A rule's recall is measured in the
   *other* sessions (for example, how often matched pairs found by the phone session share a date
   of birth). The median over sessions is used.

The model is retrained on every monthly load, using only the data loaded so far.

## Consequences

- A first attempt ran EM on the union of all blocked pairs and estimated u and m together. Most
  blocked pairs are matches, so EM settled on "the IDs differ" as the definition of a non-match and
  pushed the prior to 0.7. A second attempt fixed u but trained on the same union, and EM labelled
  every blocked pair a match. Training sessions that exclude their own blocking fields fixed both.
- The weights are readable and auditable: each is log2(m/u) for one level of one field, listed in
  `reports/results.json`. A model risk reviewer can check them without running anything.
- Fellegi-Sunter assumes fields are independent given match status. They are not: household
  members agree on surname, address and sometimes phone *together*. Weights alone therefore merge
  66 of 77 twin pairs. ADR 0002 handles that with constraints rather than a more complex model.
