# Answer-quality evaluation report

- **Date:** 2026-10-08 23:53
- **Commit:** `84fa80c`
- **Pinecone namespace:** `azure-demo`
- **Duration:** 51 s
- **Result:** 18/18 cases passed (100%); threshold 85% → **PASS**

| Check | Passed |
|---|---|
| facts | 15/15 |
| source | 15/15 |
| path | 18/18 |
| grounded | 15/15 |
| no_invention | 1/1 |

| Case | Facts | Source | Path | Grounded | No invention | Agent path |
|---|---|---|---|---|---|---|
| advisor-session-timeout | PASS | PASS | PASS | PASS |   -  | private_kb |
| advisor-four-eyes | PASS | PASS | PASS | PASS |   -  | private_kb |
| advisor-risk-review | PASS | PASS | PASS | PASS |   -  | private_kb |
| advisor-overdue-escalation | PASS | PASS | PASS | PASS |   -  | private_kb |
| channels-activation-link | PASS | PASS | PASS | PASS |   -  | private_kb |
| channels-locked-account | PASS | PASS | PASS | PASS |   -  | private_kb |
| channels-tax-reports | PASS | PASS | PASS | PASS |   -  | private_kb |
| channels-message-reply | PASS | PASS | PASS | PASS |   -  | private_kb |
| token-registration-expiry | PASS | PASS | PASS | PASS |   -  | private_kb |
| token-lost-phone | PASS | PASS | PASS | PASS |   -  | private_kb |
| token-locked | PASS | PASS | PASS | PASS |   -  | private_kb |
| scanned-custody-fee | PASS | PASS | PASS | PASS |   -  | private_kb |
| scanned-account-closure | PASS | PASS | PASS | PASS |   -  | private_kb |
| scanned-transfer-fee | PASS | PASS | PASS | PASS |   -  | private_kb |
| scanned-fee-waiver | PASS | PASS | PASS | PASS |   -  | private_kb |
| route-greeting |   -  |   -  | PASS |   -  |   -  | direct |
| route-web |   -  |   -  | PASS |   -  |   -  | web_search |
| trap-crypto-custody |   -  |   -  | PASS |   -  | PASS | web_search |
