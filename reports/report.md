# onecustomer experiment report

Synthetic world: 10,000 people, seed 7, 24 monthly loads, 14,946 source records (7,691 loans, 7,255 cards), 20,537 record versions. 77 twin pairs and 82 father-and-son pairs with the same name.

## Matching on the final load

| Strategy | Precision | Recall | F1 | Customers split | Customers falsely merged | Twin pairs merged | Exposure wrong (multi-record customers) | Exposure missing |
|---|---|---|---|---|---|---|---|---|
| Exact ID only | 100.00% | 80.05% | 88.92% | 950 | 0 | 0 of 77 | 20.1% | R15.8m |
| Deterministic rules | 89.00% | 99.31% | 93.87% | 35 | 465 | 2 of 77 | 6.5% | R0.4m |
| Fellegi-Sunter weights only | 95.36% | 99.98% | 97.62% | 1 | 207 | 60 of 77 | 2.5% | R0.0m |
| + trusted-ID cannot-link | 99.50% | 99.96% | 99.73% | 2 | 34 | 5 of 77 | 0.2% | R0.0m |
| + identity guard (onecustomer) | 99.98% | 99.87% | 99.92% | 7 | 2 | 0 of 77 | 0.1% | R0.1m |

### Threshold sweep (full model)

| Posterior threshold | Precision | Recall | Customers split | Customers falsely merged |
|---|---|---|---|---|
| 0.5 | 99.92% | 99.89% | 6 | 6 |
| 0.8 | 99.98% | 99.89% | 6 | 2 |
| 0.9 | 99.98% | 99.87% | 7 | 2 |
| 0.95 | 99.98% | 99.87% | 7 | 2 |
| 0.99 | 99.98% | 99.85% | 8 | 2 |
| 0.999 | 99.98% | 99.83% | 9 | 2 |

### Learnt match weights (log2 Bayes factor per comparison level, low to high)

- `nid`: -5.0, +10.1, +14.3
- `dob`: -4.9, +2.1, +13.2
- `first`: -4.2, +2.8, +6.6
- `surname`: -6.2, +3.1, +4.5
- `phone`: -3.2, +14.6
- `email`: -4.1, +13.6
- `address`: -4.3, +0.5, +12.4

Estimated probability that two random records match: 5.00e-05

## Party keys over 24 loads

| Keying | Key changes | Explained by a real regrouping | Unexplained | Records ever re-keyed with no regrouping | Party IDs issued | Crosswalk rows |
|---|---|---|---|---|---|---|
| rebuild | 77,835 | 22 | 77,813 | 6,642 of 14,946 | 10,006 | 0 |
| anchor | 1,103 | 22 | 1,081 | 1,081 of 14,946 | 11,086 | 0 |
| stable | 22 | 22 | 0 | 0 of 14,946 | 10,016 | 22 |

## History

16,666 SCD2 rows for 10,016 parties (10,006 current). Audit violations: 0.

Why versions were opened: created 10,004, address 3,586, records 2,296, phone 1,643, email 1,045, national_id 408, middle_name 358, surname 168, first_name 104, date_of_birth 21, split_from 12

Why versions were closed without a successor: merged_into 10

Point-in-time lookups (206,488 party-months): an SCD1 table returns the wrong address for 17.7%, surname for 0.9%, phone for 8.9%.

## Replay

- Rebuilt from scratch through month 8 (8,627 parties): identical to the final table read as of that month.
- Rebuilt from scratch through month 16 (9,340 parties): identical to the final table read as of that month.

Run time: 140.6 s
