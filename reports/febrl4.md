# FEBRL4 benchmark

10,000 records in two files, 5,000 true links. onecustomer blocking produced 5,085 candidate pairs and kept 99.56% of true pairs (pair completeness).

| System | Threshold | Precision | Recall | F1 | B-cubed F1 | Entities recovered exactly |
|---|---|---|---|---|---|---|
| onecustomer | 0.5 | 100.00% | 98.72% | 99.36% | 99.68% | 98.72% |
| onecustomer | 0.9 | 100.00% | 98.56% | 99.27% | 99.64% | 98.56% |
| onecustomer | 0.99 | 100.00% | 97.76% | 98.87% | 99.44% | 97.76% |
| onecustomer without identity guard | 0.9 | 100.00% | 99.04% | 99.52% | 99.76% | 99.04% |
| onecustomer without term-frequency adjustment | 0.9 | 100.00% | 98.52% | 99.25% | 99.63% | 98.52% |
| onecustomer exact ID only |  | 100.00% | 91.22% | 95.41% | 97.76% | 91.22% |
| onecustomer deterministic rules |  | 100.00% | 95.42% | 97.66% | 98.84% | 95.42% |
| Splink 5 | 0.5 | 100.00% | 99.50% | 99.75% | 99.87% | 99.50% |
| Splink 5 | 0.9 | 100.00% | 99.22% | 99.61% | 99.80% | 99.22% |
| Splink 5 | 0.99 | 100.00% | 98.66% | 99.33% | 99.66% | 98.66% |

onecustomer run time: 1.7 s. Splink run time: 4.5 s.
