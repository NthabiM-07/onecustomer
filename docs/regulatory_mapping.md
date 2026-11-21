# South African regulatory mapping

Why a bank needs each part of `onecustomer`, mapped to the obligation it supports. This is an
engineering mapping, not legal advice.

| Obligation | What it asks for | Feature that supports it | Evidence in this repository |
|---|---|---|---|
| **POPIA section 16**, quality of information | Reasonably practicable steps to keep personal information complete, accurate, not misleading and updated where necessary | Survivorship takes each attribute from the most recently *updated* source; SA ID numbers are checked (Luhn check digit and encoded birth date) before they are trusted | `history.golden`, `sa_id.is_valid_id`, ADR 0004 |
| **POPIA section 24**, correction of personal information | A data subject can ask for inaccurate or out-of-date information to be corrected | Column-level lineage says which source record supplied each value, so a correction goes to the right system; `explain` shows why two records were linked, so a wrongly merged customer can be shown the reason and separated | `lineage` column, `onecustomer explain`, `onecustomer lookup` |
| **National Credit Act section 81** and Regulation 23A, affordability | Before granting credit, assess the consumer's existing financial means, prospects and obligations | Linking every account a customer holds, across systems, into one party, so total exposure is complete | The matching results table: exact-ID matching leaves one multi-product customer in five with understated exposure |
| Reckless-lending risk from false merges | One person's obligations must not be attributed to another | A trusted-ID cannot-link rule and an identity guard, which put a split customer (visible, reviewable) ahead of a merged one (invisible) | ADR 0002; twins and fathers and sons in the synthetic data |
| Audit and supervisory review (e.g. BCBS 239 principles on accuracy and adaptability of risk data) | Show what the bank knew about a customer at the time of a decision, and where each fact came from | SCD Type 2 history with `as_of()`, a replay check proving history is never rewritten, and lineage | `onecustomer lookup --as-of`, `onecustomer replay`, ADR 0004 |
| Downstream systems keyed on the customer | A customer's identifier must not change without a reason that consumers can follow | Party IDs carried forward by overlap, with a crosswalk row for every merge and split | ADR 0003, `crosswalk.parquet` |

## What structural ID validation does not prove

A valid check digit and a consistent birth date show that an ID number is well formed. They do not
show that it belongs to the person who gave it. That needs verification against the Department of
Home Affairs, which is out of scope here.

## Sources

- Protection of Personal Information Act 4 of 2013, sections 16 and 24. A practitioner summary of
  section 16's "reasonably practicable" standard: [popia.co.za](https://popia.co.za/category/reasonably-practicable/).
- National Credit Act 34 of 2005, section 81, and the 2015 affordability assessment regulations:
  [Polity, "National Credit Act: new affordability assessment regulations"](https://www.polity.org.za/article/national-credit-act-new-affordability-assessment-regulations-2016-02-15).
- South African ID number structure: [Stellenbosch University HR guide](http://www.sun.ac.za/english/human-resources/Documents/HR%20WEB%20-%20MHB%20WEB/EMPLOYMENT%20EQUITY/New%20Documents/What%20your%20South%20African%20ID%20number%20reveals%20about%20you.pdf).
