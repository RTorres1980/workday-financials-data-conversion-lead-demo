# Workday Financials Data Conversion Demo

![CI](https://github.com/RTorres1980/workday-financials-data-conversion-lead-demo/actions/workflows/ci.yml/badge.svg)

A working mock conversion of financial data from legacy systems into Workday Financials. The opening trial balance comes from NetSuite and the supplier master from Concur. It covers the parts a data conversion lead is responsible for: mapping tables, transformation into load files, validation, reconciliation back to the source, and the project documents that go with them.

## What happens in a run

```
data/legacy/ (NetSuite TB, chart of accounts, Concur suppliers)
        │   + data/mapping/ (account → ledger account, department → cost center, subsidiary → company)
        ▼
scripts/run_conversion.py
        ├─► data/transformed/workday_journal_load.csv    opening-balance journal lines
        ├─► data/transformed/workday_supplier_load.csv   cleaned, deduplicated suppliers
        ├─► reports/conversion_errors.csv                records held back, with the reason
        ├─► reports/reconciliation.csv                   legacy vs converted, by company and account type
        ├─► reports/conversion_summary.csv               pass/fail checks
        └─► docs/Data_Validation_Log.md                  the above, written up for the project team
```

**Transformation rules**
- Trial balance lines get a Workday company, ledger account and cost center from the mapping tables. A line with any mapping missing is held back rather than defaulted.
- Supplier countries are converted to ISO codes, payment terms are standardized, inactive suppliers are excluded, and duplicates are removed using a normalized name plus tax ID.

**Checks**
- The legacy trial balance balances for each subsidiary
- Each company's load file balances
- Every trial balance line is mapped
- Legacy and converted totals reconcile by company and account type, and any difference equals the held-back amount
- Suppliers have required fields, no duplicates, and unique reference IDs

## Mock 1 results

The sample data includes the gaps a first mock usually finds: an inactive department (900) and a catch-all expense account (6900) with no Workday mapping, two duplicate suppliers, five suppliers missing tax IDs, and two inactive suppliers.

```
Legacy trial balance balances (US-01, UK-01)       PASS
Load file balances (COMP_US, COMP_UK)              FAIL   lines held back
All trial balance lines mapped                     FAIL   19 lines held back
Reconciles to legacy by company and account type   FAIL   4 of 10 groups differ
No duplicate suppliers in load                     PASS   2 duplicates removed
Supplier required fields complete                  FAIL   5 suppliers missing a required field
```

The failures are intended: they are the issue list for mock 2. [`docs/Data_Validation_Log.md`](docs/Data_Validation_Log.md) breaks down each held-back line and its amount. A test confirms that once the two missing mappings are added, every journal line loads, both companies balance, and the reconciliation difference is zero.

## Run it

```bash
pip install -r requirements.txt
python scripts/generate_legacy_data.py   # optional: rebuild the sample extracts and mappings
python scripts/run_conversion.py
pytest -q
```

## Project documents

| Document | Contents |
|---|---|
| [Data Conversion Plan](docs/Data_Conversion_Plan.md) | Scope, approach, mock schedule with exit criteria, roles and sign-offs |
| [Data Validation Log](docs/Data_Validation_Log.md) | Generated on each run: counts, checks, reconciliation, exceptions |
| [Weekly Status Template](docs/Weekly_Status_Template.md) | Status report format for the conversion workstream |
| [Lessons Learned](docs/Lessons_Learned.md) | Practices that carry over to real implementations |

The load files use column names modeled on Workday load templates. They are illustrative, not a copy of any specific Workday template.

## License

MIT
