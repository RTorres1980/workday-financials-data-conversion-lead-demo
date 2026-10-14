"""Create sample legacy extracts and mapping tables for the conversion.

Legacy extracts (data/legacy/):
  netsuite_trial_balance.csv  closing trial balance by subsidiary, account and department
  netsuite_chart_of_accounts.csv
  concur_suppliers.csv        supplier master from Concur, with the usual quality problems

Mapping tables (data/mapping/), the files a conversion lead owns and gets signed off:
  account_mapping.csv         NetSuite account -> Workday ledger account
  department_mapping.csv      NetSuite department -> Workday cost center
  subsidiary_mapping.csv      NetSuite subsidiary -> Workday company

Planted issues: one account and one department left out of the mappings, duplicate
suppliers, missing tax IDs, non-standard country values and an inactive supplier.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEGACY, MAPPING = ROOT / "data" / "legacy", ROOT / "data" / "mapping"

ACCOUNTS = [
    (1000, "Operating Cash", "Asset", 1010), (1100, "Payroll Cash", "Asset", 1010),
    (1200, "Accounts Receivable", "Asset", 1200), (1250, "Allowance for Doubtful Accounts", "Asset", 1210),
    (1300, "Prepaid Expenses", "Asset", 1400), (1500, "Fixed Assets", "Asset", 1600),
    (1550, "Accumulated Depreciation", "Asset", 1610), (2000, "Accounts Payable", "Liability", 2000),
    (2100, "Accrued Liabilities", "Liability", 2100), (2200, "Payroll Liabilities", "Liability", 2110),
    (2500, "Deferred Revenue", "Liability", 2300), (3000, "Common Stock", "Equity", 3000),
    (3100, "Retained Earnings", "Equity", 3100), (4000, "Product Revenue", "Revenue", 4000),
    (4100, "Services Revenue", "Revenue", 4010), (5000, "Cost of Goods Sold", "Expense", 5000),
    (6000, "Salaries and Wages", "Expense", 6000), (6100, "Employee Benefits", "Expense", 6010),
    (6200, "Rent", "Expense", 6200), (6300, "Software Subscriptions", "Expense", 6300),
    (6400, "Travel", "Expense", 6400), (6500, "Professional Fees", "Expense", 6500),
    (6600, "Depreciation Expense", "Expense", 6600), (6900, "Miscellaneous Expense", "Expense", None),
]
DEPARTMENTS = {"100": ("Finance", "CC1000"), "200": ("Sales", "CC2000"), "300": ("Engineering", "CC3000"),
               "400": ("Operations", "CC4000"), "500": ("Marketing", "CC5000"), "900": ("Legacy Projects", None)}
SUBSIDIARIES = {"US-01": ("Acme Holdings Inc.", "COMP_US"), "UK-01": ("Acme Ltd.", "COMP_UK")}
NORMAL_DEBIT = {"Asset": 1, "Expense": 1, "Liability": -1, "Equity": -1, "Revenue": -1}
CONTRA = {1250, 1550}


def trial_balance(rng):
    rows = []
    for sub in SUBSIDIARIES:
        scale = 1.0 if sub == "US-01" else 0.35
        for num, name, typ, _ in ACCOUNTS:
            if num in (3000, 3100):
                continue  # equity is the balancing figure, added below
            depts = ["100"] if typ in ("Asset", "Liability") else list(rng.choice(list(DEPARTMENTS), 3, replace=False))
            for d in depts:
                amt = round(float(rng.lognormal(11, 1)) * scale, 2)
                sign = NORMAL_DEBIT[typ] * (-1 if num in CONTRA else 1)
                rows.append([sub, num, d, amt if sign > 0 else 0.0, amt if sign < 0 else 0.0])
        tb = pd.DataFrame(rows, columns=["Subsidiary", "Account_Number", "Department", "Debit", "Credit"])
        part = tb[tb["Subsidiary"] == sub]
        gap = round(part["Debit"].sum() - part["Credit"].sum(), 2)
        stock = round(abs(gap) * 0.2, 2)
        rows.append([sub, 3000, "100", 0.0, stock])
        re = round(gap - stock, 2)
        rows.append([sub, 3100, "100", 0.0 if re > 0 else -re, re if re > 0 else 0.0])
    return pd.DataFrame(rows, columns=["Subsidiary", "Account_Number", "Department", "Debit", "Credit"])


def suppliers(rng, n=60):
    names = ["Apex", "Blue Ridge", "Cedar", "Delta", "Evergreen", "Frontier", "Granite", "Harbor", "Ironwood",
             "Juniper", "Keystone", "Lakeside", "Meridian", "Northstar", "Oakmont", "Pinnacle", "Quarry",
             "Redwood", "Summit", "Trident"]
    kinds = ["Consulting", "Supplies", "Logistics", "Software", "Facilities", "Staffing"]
    countries = {"USA": ["USA", "US", "United States"], "GBR": ["UK", "United Kingdom", "GB"]}
    rows = []
    for i in range(1, n + 1):
        iso = "USA" if rng.random() < 0.75 else "GBR"
        kind = str(rng.choice(kinds))
        rows.append({
            "Supplier_ID": f"S{i:04d}",
            "Supplier_Name": f"{rng.choice(names)} {kind} {rng.choice(['LLC', 'Inc.', 'Ltd.', 'Group'])}",
            "Country": str(rng.choice(countries[iso])),
            "Tax_ID": f"{rng.integers(10, 99)}-{rng.integers(1000000, 9999999)}" if rng.random() > 0.07 else "",
            "Category": kind,
            "Payment_Terms": str(rng.choice(["Net 30", "Net 45", "Net 60", "Due on receipt"])),
            "Status": "Active" if rng.random() > 0.05 else "Inactive",
            "Email": f"ap{i}@example.com",
        })
    df = pd.DataFrame(rows)
    # Duplicates: same supplier entered twice with different casing/spacing.
    for src in (4, 17):
        dup = df.iloc[src].copy()
        dup["Supplier_ID"] = f"S{len(df) + 1:04d}"
        dup["Supplier_Name"] = dup["Supplier_Name"].upper() + " "
        df = pd.concat([df, dup.to_frame().T], ignore_index=True)
    return df


def main(seed=21):
    rng = np.random.default_rng(seed)
    LEGACY.mkdir(parents=True, exist_ok=True)
    MAPPING.mkdir(parents=True, exist_ok=True)

    trial_balance(rng).to_csv(LEGACY / "netsuite_trial_balance.csv", index=False)
    pd.DataFrame([(a, n, t) for a, n, t, _ in ACCOUNTS], columns=["Account_Number", "Account_Name", "Account_Type"]) \
        .to_csv(LEGACY / "netsuite_chart_of_accounts.csv", index=False)
    suppliers(rng).to_csv(LEGACY / "concur_suppliers.csv", index=False)

    pd.DataFrame([(a, w) for a, _, _, w in ACCOUNTS if w is not None],
                 columns=["Account_Number", "Workday_Ledger_Account"]).to_csv(MAPPING / "account_mapping.csv",
                                                                              index=False)
    pd.DataFrame([(d, n, c) for d, (n, c) in DEPARTMENTS.items() if c is not None],
                 columns=["Department", "Department_Name", "Workday_Cost_Center"]) \
        .to_csv(MAPPING / "department_mapping.csv", index=False)
    pd.DataFrame([(s, n, c) for s, (n, c) in SUBSIDIARIES.items()],
                 columns=["Subsidiary", "Subsidiary_Name", "Workday_Company"]) \
        .to_csv(MAPPING / "subsidiary_mapping.csv", index=False)
    print(f"Legacy extracts written to {LEGACY}\nMappings written to {MAPPING}")


if __name__ == "__main__":
    main()
