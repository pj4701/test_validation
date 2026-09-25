from __future__ import annotations

from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

from .base import ValidationResult, clean_columns, log, require_files, write_frames


REQUIRED = ["Sales File", "Item File", "UOM File", "Target File"]


def determine_uom(segment):
    if pd.isna(segment):
        return np.nan
    segment = str(segment).upper().strip()
    if segment == "CORRUGATED PACKAGING":
        return "MSF"
    if segment == "CONSUMER PACKAGING":
        return "EA"
    if segment in ("CORRUGATED MILL GROUP", "CONSUMER PACKAGING MILLS"):
        return "TONS"
    return np.nan


def run_validation(files: dict, output_dir: str | Path = "outputs",
                   log_callback=None) -> ValidationResult:
    require_files(files, REQUIRED)
    output_dir = Path(output_dir)

    log(log_callback, "========== ACTUALS VALIDATION ==========")
    log(log_callback, "Reading source files...")

    sales = clean_columns(pd.read_csv(files["Sales File"], sep="^", dtype=str, low_memory=False))
    items = clean_columns(pd.read_csv(files["Item File"], sep="^", dtype=str, low_memory=False))
    uom = clean_columns(pd.read_csv(files["UOM File"], sep="^", dtype=str, low_memory=False))
    target = clean_columns(pd.read_csv(files["Target File"], dtype=str, low_memory=False))

    log(log_callback, f"Sales Rows  : {len(sales):,}")
    log(log_callback, f"Target Rows : {len(target):,}")

    # Item master
    item_lookup = items[["Item", "W_BusinessSegmentName"]].drop_duplicates()
    sales = sales.merge(item_lookup, on="Item", how="left")
    missing_item = sales[sales["W_BusinessSegmentName"].isna()].copy()

    # Expected UOM
    sales["Expected_UOM"] = sales["W_BusinessSegmentName"].apply(determine_uom)

    # UOM lookup -- deliberately created before use (fixes original ordering bug).
    uom["UOMConversion"] = pd.to_numeric(uom["UOMConversion"], errors="coerce")
    uom_lookup = uom[["ProductID", "UOM", "UOMConversion"]].drop_duplicates()

    sales = sales.merge(
        uom_lookup,
        left_on=["Item", "Expected_UOM"],
        right_on=["ProductID", "UOM"],
        how="left",
    )

    missing_uom = sales[sales["UOMConversion"].isna()].copy()
    zero_uom = sales[sales["UOMConversion"] == 0].copy()

    # Original logic excludes null/zero conversion rows from expected aggregation.
    sales = sales[sales["UOMConversion"].notna()].copy()
    sales = sales[sales["UOMConversion"] != 0].copy()

    # Numeric quantities
    sales["SORequestedQuantity"] = pd.to_numeric(
        sales["SORequestedQuantity"], errors="coerce"
    )
    sales["SOReturnedQuantity"] = pd.to_numeric(
        sales["SOReturnedQuantity"], errors="coerce"
    )

    negative_qty = sales[sales["SORequestedQuantity"] < 0].copy()
    zero_qty = sales[sales["SORequestedQuantity"] == 0].copy()

    sales["Expected_ActualRaw"] = (
        sales["SORequestedQuantity"] * sales["UOMConversion"]
    )
    sales["Expected_SWActualReturns"] = (
        sales["SOReturnedQuantity"] * sales["UOMConversion"]
    )

    sales["SORequestedDeliveryDate"] = pd.to_datetime(
        sales["SORequestedDeliveryDate"], errors="coerce"
    )
    sales["StartDay"] = (
        sales["SORequestedDeliveryDate"]
        .dt.to_period("M")
        .dt.to_timestamp()
        .dt.strftime("%Y-%m-%d")
    )

    sales["Location"] = sales["ShipFrom"]
    sales["Region"] = sales["ShipToID"]
    sales["DemandDomain"] = sales["W_EndMarketChild"]
    sales["Account"] = sales["SoldToID"]
    sales["Channel"] = "All"
    sales["PnL"] = "All"

    keys = [
        "Item", "Location", "Region", "StartDay",
        "DemandDomain", "Account", "Channel", "PnL"
    ]

    for col in keys:
        sales[col] = sales[col].fillna("").astype(str).str.strip()

    expected = (
        sales.groupby(keys, dropna=False)
        .agg({
            "Expected_ActualRaw": "sum",
            "Expected_SWActualReturns": "sum",
        })
        .reset_index()
    )

    # Target standardization
    target = target.rename(columns={
        "Item.[Item]": "Item",
        "Region.[Region]": "Region",
        "Demand Domain.[Demand Domain]": "DemandDomain",
        "Time.[Day]": "StartDay",
        "Account.[Account]": "Account",
        "Location.[Location]": "Location",
        "Channel.[Channel]": "Channel",
        "PnL.[PnL]": "PnL",
        "Actual Raw": "ActualRaw",
    })

    target["SWActualReturns"] = 0
    target["ActualRaw"] = pd.to_numeric(target["ActualRaw"], errors="coerce")
    target["StartDay"] = pd.to_datetime(target["StartDay"], errors="coerce").dt.strftime("%Y-%m-%d")

    for col in keys:
        target[col] = target[col].fillna("").astype(str).str.strip()

    source_duplicates = expected[
        expected.duplicated(subset=keys, keep=False)
    ].copy()
    target_duplicates = target[
        target.duplicated(subset=keys, keep=False)
    ].copy()

    merged = pd.merge(
        expected,
        target[keys + ["ActualRaw", "SWActualReturns"]],
        on=keys,
        how="outer",
        indicator=True,
    )

    merged["ActualRawVariance"] = (
        merged["Expected_ActualRaw"].fillna(0)
        - merged["ActualRaw"].fillna(0)
    )
    merged["ReturnVariance"] = (
        merged["Expected_SWActualReturns"].fillna(0)
        - merged["SWActualReturns"].fillna(0)
    )

    matched = merged[
        (merged["_merge"] == "both")
        & (merged["ActualRawVariance"].round(5) == 0)
    ].copy()

    actualraw_mismatch = merged[
        (merged["_merge"] == "both")
        & (merged["ActualRawVariance"].round(5) != 0)
    ].copy()

    source_only = merged[merged["_merge"] == "left_only"].copy()
    target_only = merged[merged["_merge"] == "right_only"].copy()

    source_total = expected["Expected_ActualRaw"].fillna(0).sum()
    target_total = target["ActualRaw"].fillna(0).sum()
    variance = source_total - target_total
    variance_pct = (variance / target_total * 100) if target_total != 0 else np.nan
    match_pct = (len(matched) / len(expected) * 100) if len(expected) else 0

    summary = pd.DataFrame({
        "Metric": [
            "Sales Rows", "Target Rows", "Expected Rows", "Matched",
            "ActualRaw Mismatch", "Source Only", "Target Only",
            "Missing Item", "Missing UOM", "Zero UOM",
            "Negative Quantity", "Zero Quantity", "Source Duplicates",
            "Target Duplicates", "Expected Actual Raw Total",
            "Target Actual Raw Total", "Actual Raw Variance",
            "Actual Raw Variance %", "Match %",
        ],
        "Value": [
            len(sales), len(target), len(expected), len(matched),
            len(actualraw_mismatch), len(source_only), len(target_only),
            len(missing_item), len(missing_uom), len(zero_uom),
            len(negative_qty), len(zero_qty), len(source_duplicates),
            len(target_duplicates), source_total, target_total, variance,
            variance_pct, match_pct,
        ],
    })

    actual_raw_recon = pd.DataFrame({
        "Metric": [
            "Expected Actual Raw Total", "Target Actual Raw Total",
            "Actual Raw Variance", "Actual Raw Variance %",
            "Matched Records", "Expected Records", "Match %",
        ],
        "Value": [
            source_total, target_total, variance, variance_pct,
            len(matched), len(expected), match_pct,
        ],
    })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"ActualData_Validation_Report_{timestamp}.xlsx"

    write_frames(output_file, {
        "01_Summary": summary,
        "02_ActualRaw_Mismatch": actualraw_mismatch,
        "03_Source_Only": source_only,
        "04_Target_Only": target_only,
        "05_Missing_Item": missing_item,
        "06_Missing_UOM": missing_uom,
        "07_Matched": matched,
        "08_Source_Duplicates": source_duplicates,
        "09_Target_Duplicates": target_duplicates,
        "10_ActualRaw_Recon": actual_raw_recon,
    })

    details = {
        "Sales Rows": len(sales),
        "Target Rows": len(target),
        "Expected Rows": len(expected),
        "Matched": len(matched),
        "ActualRaw Mismatch": len(actualraw_mismatch),
        "Source Only": len(source_only),
        "Target Only": len(target_only),
        "Missing Item": len(missing_item),
        "Missing UOM": len(missing_uom),
        "Zero UOM": len(zero_uom),
        "Negative Quantity": len(negative_qty),
        "Zero Quantity": len(zero_qty),
        "Variance": variance,
        "Match %": round(match_pct, 2),
    }

    for key, value in details.items():
        log(log_callback, f"{key:<25}: {value}")

    log(log_callback, f"Excel Report Generated: {output_file}")

    return ValidationResult(
        name="Actuals Validation",
        output_file=str(output_file),
        records=len(expected),
        passed=len(matched),
        failed=len(actualraw_mismatch),
        match_pct=match_pct,
        details=details,
    )
