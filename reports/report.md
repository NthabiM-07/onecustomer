# onecustomer experiment report

Synthetic world: 10,000 people, seed 7, 24 monthly loads, 14,946 source records (7,691 loans, 7,255 cards), 20,384 record versions. 77 twin pairs and 82 father-and-son pairs with the same name.

## Matching on the final load

| Strategy | Precision | Recall | F1 | Customers split | Customers falsely merged | Twin pairs merged | Exposure wrong (multi-record customers) | Exposure missing |
|---|---|---|---|---|---|---|---|---|
| Exact ID only | 100.00% | 79.77% | 88.74% | 961 | 0 | 0 of 77 | 20.3% | R17.2m |
| Deterministic rules | 91.32% | 99.43% | 95.20% | 29 | 361 | 3 of 77 | 5.2% | R0.5m |
| Fellegi-Sunter weights only | 92.15% | 99.98% | 95.91% | 1 | 332 | 55 of 77 | 4.2% | R0.1m |
| + trusted-ID cannot-link | 99.33% | 99.96% | 99.65% | 2 | 46 | 5 of 77 | 0.3% | R0.1m |
| + identity guard (onecustomer) | 100.00% | 99.79% | 99.89% | 10 | 0 | 0 of 77 | 0.2% | R0.2m |

### Threshold sweep (full model)

| Posterior threshold | Precision | Recall | Customers split | Customers falsely merged |
|---|---|---|---|---|
| 0.5 | 100.00% | 99.81% | 9 | 0 |
| 0.8 | 100.00% | 99.81% | 9 | 0 |
| 0.9 | 100.00% | 99.79% | 10 | 0 |
| 0.95 | 100.00% | 99.71% | 14 | 0 |
| 0.99 | 100.00% | 99.60% | 20 | 0 |
| 0.999 | 100.00% | 99.54% | 23 | 0 |

### Learnt match weights (log2 Bayes factor per comparison level, low to high)

- `nid`: -4.9, +9.8, +13.7
- `dob`: -4.8, +2.2, +12.9
- `first`: -4.1, +2.7, +6.5
- `surname`: -6.3, +3.3, +4.5
- `phone`: -3.3, +14.2
- `email`: -3.8, +13.6
- `address`: -4.2, +0.0, +12.8

Estimated probability that two random records match: 5.00e-05

## Party keys over 24 loads

| Keying | Key changes | Explained by a real regrouping | Unexplained | Records ever re-keyed with no regrouping | Party IDs issued | Crosswalk rows |
|---|---|---|---|---|---|---|
| rebuild | 74,901 | 22 | 74,879 | 4,128 of 14,946 | 10,010 | 0 |
| anchor | 1,102 | 22 | 1,080 | 1,080 of 14,946 | 11,093 | 0 |
| stable | 22 | 22 | 0 | 0 of 14,946 | 10,022 | 22 |

## History

16,431 SCD2 rows for 10,022 parties (10,010 current). Audit violations: 0.

Why versions were opened: created 10,012, records 2,295, address 2,270, phone 1,597, email 1,056, national_id 398, middle_name 353, surname 99, first_name 97, date_of_birth 24, split_from 10

Why versions were closed without a successor: merged_into 12

Point-in-time lookups (206,536 party-months): an SCD1 table returns the wrong address for 12.7%, surname for 0.6%, phone for 8.6%.

## Replay

- Rebuilt from scratch through month 8 (8,630 parties): identical to the final table read as of that month.
- Rebuilt from scratch through month 16 (9,340 parties): identical to the final table read as of that month.

Run time: 78.2 s
