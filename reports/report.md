# onecustomer experiment report

Synthetic world: 10,000 people, seed 7, 24 monthly loads, 14,946 source records (7,691 loans, 7,255 cards), 20,384 record versions. 77 twin pairs and 82 father-and-son pairs with the same name.

## Matching on the final load

| Strategy | Precision | Recall | F1 | Customers split | Customers falsely merged | Twin pairs merged | Exposure wrong (multi-record customers) | Exposure missing |
|---|---|---|---|---|---|---|---|---|
| Exact ID only | 100.00% | 79.77% | 88.74% | 961 | 0 | 0 of 77 | 20.3% | R17.2m |
| Deterministic rules | 91.32% | 99.43% | 95.20% | 29 | 361 | 3 of 77 | 5.2% | R0.5m |
| Fellegi-Sunter weights only | 90.12% | 99.92% | 94.77% | 4 | 423 | 66 of 77 | 5.4% | R0.1m |
| + trusted-ID cannot-link | 99.41% | 99.92% | 99.67% | 4 | 40 | 5 of 77 | 0.3% | R0.1m |
| + identity guard (onecustomer) | 99.96% | 99.73% | 99.85% | 13 | 4 | 0 of 77 | 0.3% | R0.3m |

### Threshold sweep (full model)

| Posterior threshold | Precision | Recall | Customers split | Customers falsely merged |
|---|---|---|---|---|
| 0.5 | 99.96% | 99.81% | 9 | 4 |
| 0.8 | 99.96% | 99.79% | 10 | 4 |
| 0.9 | 99.96% | 99.73% | 13 | 4 |
| 0.95 | 99.96% | 99.73% | 13 | 4 |
| 0.99 | 99.96% | 99.54% | 23 | 4 |
| 0.999 | 99.96% | 99.52% | 24 | 4 |

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
| rebuild | 77,332 | 45 | 77,287 | 6,237 of 14,946 | 10,011 | 0 |
| anchor | 1,126 | 45 | 1,081 | 1,081 of 14,946 | 11,095 | 0 |
| stable | 45 | 45 | 0 | 0 of 14,946 | 10,032 | 45 |

## History

16,451 SCD2 rows for 10,032 parties (10,011 current). Audit violations: 0.

Why versions were opened: created 10,008, records 2,308, address 2,270, phone 1,607, email 1,066, national_id 409, middle_name 368, surname 99, first_name 99, date_of_birth 35, split_from 24

Why versions were closed without a successor: merged_into 21

Point-in-time lookups (206,508 party-months): an SCD1 table returns the wrong address for 12.7%, surname for 0.6%, phone for 8.6%.

## Replay

- Rebuilt from scratch through month 8 (8,628 parties): identical to the final table read as of that month.
- Rebuilt from scratch through month 16 (9,340 parties): identical to the final table read as of that month.

Run time: 124.1 s
