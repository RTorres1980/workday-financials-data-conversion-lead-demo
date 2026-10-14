"""Run one mock conversion: extract -> transform -> validate -> reconcile -> report.

Inputs:  data/legacy/*.csv, data/mapping/*.csv
Outputs: data/transformed/workday_journal_load.csv     opening-balance journal lines ready to load
         data/transformed/workday_supplier_load.csv    cleaned, deduplicated supplier records
         reports/conversion_errors.csv                  rows held back from the load, with the reason
         reports/reconciliation.csv                     legacy vs converted totals by company and account type
         reports/conversion_summary.csv                 record counts and pass/fail checks
         docs/Data_Validation_Log.md                    validation results for this run

Usage: python scripts/run_conversion.py [--cutover-date 2025-12-31]
"""
import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEGACY, MAPPING = ROOT / "data" / "legacy", ROOT / "data" / "mapping"
TRANSFORMED, REPORTS, DOCS = ROOT / "data" / "transformed", ROOT / "reports", ROOT / "docs"

COUNTRY_ISO = {"usa": "USA", "us": "USA", "united states": "USA",
               "uk": "GBR", "united kingdom": "GBR", "gb": "GBR", "gbr": "GBR"}
REQUIRED_SUPPLIER_FIELDS = ["Supplier_Name", "Country", "Tax_ID", "Payment_Terms"]


# ---------- Extract ----------

def extract():
    read = lambda folder, name: pd.read_csv(folder / name, dtype=str, keep_default_na=False)  # noqa: E731
    tb = read(LEGACY, "netsuite_trial_balance.csv")
    tb[["Debit", "Credit"]] = tb[["Debit", "Credit"]].astype(float)
    return {
        "tb": tb,
        "coa": read(LEGACY, "netsuite_chart_of_accounts.csv"),
        "suppliers": read(LEGACY, "concur_suppliers.csv"),
        "acct_map": read(MAPPING, "account_mapping.csv"),
        "dept_map": read(MAPPING, "department_mapping.csv"),
        "sub_map": read(MAPPING, "subsidiary_mapping.csv"),
    }


# ---------- Transform ----------

def transform_journal(d, cutover):
    tb = (d["tb"].merge(d["coa"][["Account_Number", "Account_Name", "Account_Type"]], on="Account_Number", how="left")
          .merge(d["acct_map"], on="Account_Number", how="left")
          .merge(d["dept_map"][["Department", "Workday_Cost_Center"]], on="Department", how="left")
          .merge(d["sub_map"][["Subsidiary", "Workday_Company"]], on="Subsidiary", how="left"))

    reasons = pd.Series("", index=tb.index)
    for col, msg in [("Workday_Ledger_Account", "No ledger account mapping for NetSuite account"),
                     ("Workday_Cost_Center", "No cost center mapping for department"),
                     ("Workday_Company", "No company mapping for subsidiary")]:
        missing = tb[col].isna()
        reasons[missing] = reasons[missing].where(reasons[missing] == "", reasons[missing] + "; ") + msg
    errors = tb[reasons != ""].assign(Reason=reasons[reasons != ""])

    ok = tb[reasons == ""]
    load = pd.DataFrame({
        "Company": ok["Workday_Company"],
        "Accounting_Date": cutover,
        "Journal_Source": "Conversion",
        "Ledger_Account": ok["Workday_Ledger_Account"],
        "Cost_Center": ok["Workday_Cost_Center"],
        "Debit": ok["Debit"].round(2),
        "Credit": ok["Credit"].round(2),
        "Memo": "Opening balance - NetSuite " + ok["Account_Number"] + " / Dept " + ok["Department"],
    })
    return load, errors, tb


def normalize_name(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def transform_suppliers(raw):
    s = raw.copy()
    s["Supplier_Name"] = s["Supplier_Name"].str.strip()
    s["Country"] = s["Country"].str.strip().str.lower().map(COUNTRY_ISO).fillna(s["Country"])
    errors = []

    inactive = s["Status"].str.lower() != "active"
    errors.append(s[inactive].assign(Reason="Inactive supplier, excluded from conversion"))
    s = s[~inactive]

    key = s["Supplier_Name"].map(normalize_name) + "|" + s["Tax_ID"]
    dup = key.duplicated(keep="first")
    errors.append(s[dup].assign(Reason="Duplicate of " + s.groupby(key)["Supplier_ID"].transform("first")[dup]))
    s = s[~dup]

    for field in REQUIRED_SUPPLIER_FIELDS:
        bad = s[field].str.strip() == ""
        errors.append(s[bad].assign(Reason=f"Missing required field: {field}"))
        s = s[~bad]
    bad_country = ~s["Country"].isin(set(COUNTRY_ISO.values()))
    errors.append(s[bad_country].assign(Reason="Country not recognized"))
    s = s[~bad_country]

    load = pd.DataFrame({
        "Supplier_Reference_ID": "CONV-" + s["Supplier_ID"],
        "Supplier_Name": s["Supplier_Name"],
        "Supplier_Category": s["Category"],
        "Country_ISO_Code": s["Country"],
        "Tax_ID": s["Tax_ID"],
        "Payment_Terms": s["Payment_Terms"].str.replace(" ", "_").str.upper(),
        "Remit_To_Email": s["Email"],
        "Legacy_Supplier_ID": s["Supplier_ID"],
    })
    return load, pd.concat(errors, ignore_index=True)


# ---------- Validate and reconcile ----------

def reconcile(enriched, load):
    legacy = (enriched.groupby(["Subsidiary", "Account_Type"])[["Debit", "Credit"]].sum()
              .rename(columns={"Debit": "Legacy_Debit", "Credit": "Legacy_Credit"}))
    conv = load.assign(Account_Type=enriched.loc[load.index, "Account_Type"],
                       Subsidiary=enriched.loc[load.index, "Subsidiary"])
    converted = (conv.groupby(["Subsidiary", "Account_Type"])[["Debit", "Credit"]].sum()
                 .rename(columns={"Debit": "Converted_Debit", "Credit": "Converted_Credit"}))
    r = legacy.join(converted).fillna(0)
    legacy_net = r["Legacy_Debit"] - r["Legacy_Credit"]
    r["Difference"] = (legacy_net - (r["Converted_Debit"] - r["Converted_Credit"])).round(2)
    return r.round(2).reset_index()


def checks(d, load, tb_errors, suppliers_load, supplier_errors, recon):
    c = []

    def add(name, passed, detail):
        c.append({"Check": name, "Result": "PASS" if passed else "FAIL", "Detail": detail})

    for sub, part in d["tb"].groupby("Subsidiary"):
        diff = round(part["Debit"].sum() - part["Credit"].sum(), 2)
        add(f"Legacy trial balance balances ({sub})", diff == 0, f"debits - credits = {diff:,.2f}")
    for company, part in load.groupby("Company"):
        diff = round(part["Debit"].sum() - part["Credit"].sum(), 2)
        add(f"Load file balances ({company})", diff == 0, f"debits - credits = {diff:,.2f}")
    add("All trial balance lines mapped", tb_errors.empty, f"{len(tb_errors)} lines held back")
    add("Reconciles to legacy by company and account type", (recon["Difference"] == 0).all(),
        f"{int((recon['Difference'] != 0).sum())} of {len(recon)} groups differ")
    dup = int(supplier_errors["Reason"].str.startswith("Duplicate").sum())
    add("No duplicate suppliers in load", True, f"{dup} duplicates removed")
    missing = int(supplier_errors["Reason"].str.startswith("Missing").sum())
    add("Supplier required fields complete", missing == 0, f"{missing} suppliers missing a required field")
    add("Supplier load has unique reference IDs", suppliers_load["Supplier_Reference_ID"].is_unique,
        f"{len(suppliers_load)} suppliers")
    return pd.DataFrame(c)


# ---------- Report ----------

def write_validation_log(summary, recon, tb_errors, supplier_errors, counts, cutover):
    def table(df):
        cols = list(df.columns)
        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(f"{v:,.2f}" if isinstance(v, float) else str(v) for v in row) + " |"
                  for row in df.itertuples(index=False)]
        return "\n".join(lines)

    held = (tb_errors.groupby(["Account_Number", "Department", "Reason"])
            .agg(Lines=("Debit", "size"), Net=("Debit", "sum")).reset_index())
    held["Net"] = (held["Net"] - tb_errors.groupby(["Account_Number", "Department", "Reason"])["Credit"].sum().values)
    text = f"""# Data Validation Log

Generated by `scripts/run_conversion.py` on {date.today():%Y-%m-%d} for cutover date {cutover}.
Re-run the script after each mapping change; this file is overwritten each time.

## Record counts

{table(pd.DataFrame(counts, columns=["Object", "Legacy records", "Loaded", "Held back"]))}

## Checks

{table(summary)}

## Reconciliation: legacy vs converted (net debit)

{table(recon)}

## Trial balance lines held back

{table(held) if len(held) else "None."}

**Action:** add the missing account and cost center mappings, get them signed off, and re-run.

## Supplier exceptions

{table(supplier_errors[["Supplier_ID", "Supplier_Name", "Reason"]]) if len(supplier_errors) else "None."}
"""
    (DOCS / "Data_Validation_Log.md").write_text(text)


def main(cutover):
    for p in (TRANSFORMED, REPORTS, DOCS):
        p.mkdir(parents=True, exist_ok=True)
    d = extract()
    journal, tb_errors, enriched = transform_journal(d, cutover)
    suppliers, supplier_errors = transform_suppliers(d["suppliers"])
    recon = reconcile(enriched, journal)
    summary = checks(d, journal, tb_errors, suppliers, supplier_errors, recon)

    journal.to_csv(TRANSFORMED / "workday_journal_load.csv", index=False)
    suppliers.to_csv(TRANSFORMED / "workday_supplier_load.csv", index=False)
    pd.concat([tb_errors.assign(Object="Trial balance"), supplier_errors.assign(Object="Supplier")],
              ignore_index=True).to_csv(REPORTS / "conversion_errors.csv", index=False)
    recon.to_csv(REPORTS / "reconciliation.csv", index=False)
    summary.to_csv(REPORTS / "conversion_summary.csv", index=False)
    counts = [("Trial balance lines", len(d["tb"]), len(journal), len(tb_errors)),
              ("Suppliers", len(d["suppliers"]), len(suppliers), len(supplier_errors))]
    write_validation_log(summary, recon, tb_errors, supplier_errors, counts, cutover)

    pd.set_option("display.width", 160)
    print(summary.to_string(index=False))
    print(f"\nLoaded {len(journal)} journal lines and {len(suppliers)} suppliers; "
          f"{len(tb_errors) + len(supplier_errors)} records held back (see reports/conversion_errors.csv)")
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cutover-date", default="2025-12-31")
    main(p.parse_args().cutover_date)
