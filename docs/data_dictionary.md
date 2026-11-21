# Data dictionary

## Inputs (`data/`, written by `onecustomer generate`)

### `versions.parquet`: one row per source-record version

| Column | Meaning |
|---|---|
| `system` | `loans` (branch-captured lending platform) or `cards` (app-onboarded card platform) |
| `record_key` | Source key, `LN0000001` or `CD0000001`, issued in order of onboarding |
| `load_month` | Monthly load (1 = January 2024, 24 = December 2025) in which this version first appeared |
| `first_name`, `middle_name`, `surname` | As captured: upper case on loans, mixed case and nicknames on cards |
| `national_id` | 13-digit SA ID as captured; may be missing or mistyped |
| `dob` | Captured date of birth (ISO); may carry a typo or a day/month swap |
| `phone`, `email` | As captured, in each system's own format |
| `address_line`, `city`, `postal_code` | As captured; cards abbreviates street types |
| `balance` | Outstanding balance on the account, in rand |

### `links.parquet`: ground truth, never read by the matcher

`record_key`, `person_id`, `system`, `open_month`.

### `people.parquet`: the true population

`person_id`, `household_id`, `gender`, `dob`, `national_id`, `twin_of`, `junior_of` (a son with
his father's first name).

## Outputs (`data/`, written by `onecustomer run`)

### `party_history.parquet`: the customer master, SCD Type 2

| Column | Meaning |
|---|---|
| `party_id` | Stable party key, `PTY00000001` |
| `version` | 1, 2, ... per party |
| `valid_from`, `valid_to` | Load months; a version is in force for `valid_from <= m < valid_to`. `valid_to` is null on the current row |
| `valid_from_date`, `valid_to_date` | The same, as month-end dates |
| `is_current` | True on the open row |
| `change_reason` | Why this version opened: `created`, `split_from:<party>`, or a list such as `records,address` |
| `closed_reason` | Set when a party is retired: `merged_into:<party>` or `split_into:<party>` |
| `national_id`, `date_of_birth`, `first_name`, `middle_name`, `surname` | Golden identity attributes |
| `phone`, `email`, `address_line`, `city`, `postal_code` | Golden contact attributes |
| `total_exposure` | Sum of member-record balances |
| `record_keys` | Member source records, `\|`-separated |
| `systems` | `loans`, `cards` or `cards+loans` |
| `lineage` | JSON: for each golden attribute, the source record that supplied it |

### `crosswalk.parquet`

| Column | Meaning |
|---|---|
| `month` | Load month of the event |
| `from_party` | The retired ID (`merged_into`, `split_into`) or the new ID (`split_from`) |
| `to_party` | The surviving party, or the party a new ID was split from |
| `reason` | `merged_into`, `split_into` or `split_from` |

### `assignments.parquet`

`month`, `record_key`, `party_id`: which party held each source record after each load.
