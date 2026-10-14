# Data Conversion Plan

## Scope

| Object | Source | Workday target | Method |
|---|---|---|---|
| Opening balances (trial balance) | NetSuite | Accounting journal, one per company | Load file from `workday_journal_load.csv` |
| Suppliers | Concur | Supplier records | Load file from `workday_supplier_load.csv` |
| Fixed assets, open AP/AR | NetSuite | — | Out of scope for this demo |

Legal entities: NetSuite subsidiary US-01 → Workday company COMP_US, UK-01 → COMP_UK.

## Approach

1. **Extract**: finance provides the NetSuite closing trial balance and chart of accounts; AP provides the Concur supplier export.
2. **Map**: the conversion lead maintains the three mapping tables in `data/mapping/`. Each is reviewed and signed off by the account owner (GL: Controller; cost centers: FP&A; companies: Controller).
3. **Transform**: `scripts/run_conversion.py` applies the mappings, standardizes values (country ISO codes, payment terms) and removes duplicates.
4. **Hold back, don't guess**: any record that can't be mapped or fails a required-field check is written to `reports/conversion_errors.csv` with a reason, never loaded with a default value.
5. **Validate and reconcile**: every run checks that both the legacy trial balance and each company's load file balance, and reconciles legacy against converted totals by company and account type. Any difference must equal the held-back amount.
6. **Sign-off**: a mock passes when every check in `reports/conversion_summary.csv` passes and the Controller signs the reconciliation.

## Mock schedule

| Mock | Purpose | Exit criteria |
|---|---|---|
| Mock 1 | First end-to-end run; find mapping gaps and data quality issues | Issue list agreed with owners |
| Mock 2 | Re-run with corrected mappings and cleansed supplier data | All checks pass on a test tenant |
| Dress rehearsal | Full run on production-like data with cutover timings | Signed reconciliation, timings within the cutover window |
| Cutover | Final load as of the cutover date | Controller sign-off |

## Roles

- **Conversion lead**: owns the mapping tables, runs each mock, publishes the validation log and status report
- **Controller**: signs off on the GL mapping and the reconciliation
- **AP lead**: resolves supplier exceptions in Concur before the next extract
- **FP&A**: owns the department-to-cost-center mapping
