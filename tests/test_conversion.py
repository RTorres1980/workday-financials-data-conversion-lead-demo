import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_legacy_data  # noqa: E402
import run_conversion as conv  # noqa: E402


@pytest.fixture(scope="module")
def data():
    generate_legacy_data.main()
    return conv.extract()


def test_legacy_trial_balance_balances(data):
    for _, part in data["tb"].groupby("Subsidiary"):
        assert round(part["Debit"].sum() - part["Credit"].sum(), 2) == 0


def test_unmapped_lines_held_back_with_reason(data):
    load, errors, _ = conv.transform_journal(data, "2025-12-31")
    assert set(errors.loc[errors["Account_Number"] == "6900", "Reason"]) == {
        "No ledger account mapping for NetSuite account"}
    assert (errors.loc[errors["Department"] == "900", "Reason"]
            .str.contains("No cost center mapping").all())
    assert len(load) + len(errors) == len(data["tb"])
    assert load[["Company", "Ledger_Account", "Cost_Center"]].notna().all().all()


def test_reconciliation_differences_equal_held_back_amounts(data):
    load, errors, enriched = conv.transform_journal(data, "2025-12-31")
    recon = conv.reconcile(enriched, load)
    held_net = round((errors["Debit"] - errors["Credit"]).sum(), 2)
    assert round(recon["Difference"].sum(), 2) == held_net


def test_full_mapping_produces_balanced_load(data):
    d = dict(data)
    extra_acct = pd.DataFrame([{"Account_Number": "6900", "Workday_Ledger_Account": "6900"}])
    extra_dept = pd.DataFrame([{"Department": "900", "Department_Name": "Legacy", "Workday_Cost_Center": "CC9000"}])
    d["acct_map"] = pd.concat([d["acct_map"], extra_acct])
    d["dept_map"] = pd.concat([d["dept_map"], extra_dept])
    load, errors, enriched = conv.transform_journal(d, "2025-12-31")
    assert errors.empty
    for _, part in load.groupby("Company"):
        assert round(part["Debit"].sum() - part["Credit"].sum(), 2) == 0
    assert (conv.reconcile(enriched, load)["Difference"] == 0).all()


def test_supplier_cleanup(data):
    load, errors = conv.transform_suppliers(data["suppliers"])
    assert set(load["Country_ISO_Code"]) <= {"USA", "GBR"}
    assert load["Supplier_Reference_ID"].is_unique
    keys = load["Supplier_Name"].map(conv.normalize_name) + load["Tax_ID"]
    assert keys.is_unique
    assert errors["Reason"].str.startswith("Duplicate of").sum() == 2
    assert (load["Tax_ID"] != "").all()
    assert len(load) + len(errors) == len(data["suppliers"])
