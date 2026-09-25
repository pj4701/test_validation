from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd

from .base import ValidationResult, clean_columns, log, require_files, write_frames


REQUIRED = ["ASP Source File", "ASP Past Target File"]


def run_validation(files: dict, output_dir: str | Path = "outputs",
                   log_callback=None) -> ValidationResult:
    require_files(files, REQUIRED)
    output_dir = Path(output_dir)

    log(log_callback, "========== O9 ASP PAST-MONTH COMPARISON ==========")

    src = clean_columns(pd.read_csv(files["ASP Source File"], sep="^", low_memory=False))
    tgt = clean_columns(pd.read_csv(files["ASP Past Target File"], low_memory=False))

    src["Month"] = pd.to_datetime(src["Month"], errors="coerce")
    src["Month"] = "M" + src["Month"].dt.strftime("%m-%b-%Y")

    src.rename(columns={
        "Item": "Planning Item",
        "ShipToId": "Planning Region",
        "SoldToId": "Planning Account",
        "W_EndMarketChild": "Planning Demand Domain",
        "ShipFrom": "Planning Location",
        "AvgSalesPrice": "UnitPriceInput",
    }, inplace=True)

    tgt.rename(columns={
        "Time.[Month]": "Month",
        "Item.[Planning Item]": "Planning Item",
        "Region.[Planning Region]": "Planning Region",
        "Demand Domain.[Planning Demand Domain]": "Planning Demand Domain",
        "Account.[Planning Account]": "Planning Account",
        "Location.[Planning Location]": "Planning Location",
    }, inplace=True)

    keys = [
        "Month", "Planning Item", "Planning Region",
        "Planning Demand Domain", "Planning Account", "Planning Location"
    ]
    for col in keys:
        src[col] = src[col].astype(str).str.strip()
        tgt[col] = tgt[col].astype(str).str.strip()

    src["UnitPriceInput"] = pd.to_numeric(src["UnitPriceInput"], errors="coerce")
    src["TotalOrderPrice"] = pd.to_numeric(src["TotalOrderPrice"], errors="coerce")
    tgt["Unit Price WRK"] = pd.to_numeric(tgt["Unit Price WRK"], errors="coerce")
    tgt["Cons_Revenue"] = pd.to_numeric(tgt["Cons_Revenue"], errors="coerce")

    source_raw_count = len(src)

    source_agg = (
        src.groupby(keys, dropna=False)
        .agg({"UnitPriceInput": "max", "TotalOrderPrice": "sum"})
        .reset_index()
    )
    source_agg_count = len(source_agg)
    collapsed_count = source_raw_count - source_agg_count

    source_agg["BusinessKey"] = source_agg[keys].astype(str).agg("|".join, axis=1)
    tgt["BusinessKey"] = tgt[keys].astype(str).agg("|".join, axis=1)

    intersection = source_agg[source_agg["BusinessKey"].isin(tgt["BusinessKey"])]
    source_missing = source_agg[~source_agg["BusinessKey"].isin(tgt["BusinessKey"])]
    target_extra = tgt[~tgt["BusinessKey"].isin(source_agg["BusinessKey"])]

    matched = pd.merge(
        intersection, tgt, on="BusinessKey", suffixes=("_SRC", "_TGT")
    )

    matched["Price_SRC"] = matched["UnitPriceInput"].round(3)
    matched["Price_TGT"] = matched["Unit Price WRK"].round(3)
    price_match = matched[matched["Price_SRC"] == matched["Price_TGT"]].copy()
    price_mismatch = matched[matched["Price_SRC"] != matched["Price_TGT"]].copy()
    if len(price_mismatch):
        price_mismatch["Variance"] = (
            price_mismatch["UnitPriceInput"] - price_mismatch["Unit Price WRK"]
        )

    matched["Revenue_SRC"] = matched["TotalOrderPrice"].round(3)
    matched["Revenue_TGT"] = matched["Cons_Revenue"].round(3)
    revenue_match = matched[matched["Revenue_SRC"] == matched["Revenue_TGT"]].copy()
    revenue_mismatch = matched[matched["Revenue_SRC"] != matched["Revenue_TGT"]].copy()
    if len(revenue_mismatch):
        revenue_mismatch["RevenueVariance"] = (
            revenue_mismatch["TotalOrderPrice"] - revenue_mismatch["Cons_Revenue"]
        )

    source_missing_pct = len(source_missing) / source_agg_count * 100 if source_agg_count else 0
    target_extra_pct = len(target_extra) / len(tgt) * 100 if len(tgt) else 0

    summary = pd.DataFrame({
        "Metric": [
            "Source Raw Count", "Source Aggregated Count", "Tenant Count",
            "Records Reduced By Aggregation", "Intersection Count",
            "Source Missing Count", "Target Extra Count",
            "Source Missing %", "Target Extra %",
        ],
        "Value": [
            source_raw_count, source_agg_count, len(tgt), collapsed_count,
            len(intersection), len(source_missing), len(target_extra),
            round(source_missing_pct, 2), round(target_extra_pct, 2),
        ],
    })
    asp_summary = pd.DataFrame({
        "Metric": ["Price Match Count", "Price Mismatch Count",
                   "Source ASP Total", "Tenant ASP Total", "ASP Variance"],
        "Value": [
            len(price_match), len(price_mismatch),
            round(source_agg["UnitPriceInput"].sum(), 2),
            round(tgt["Unit Price WRK"].sum(), 2),
            round(source_agg["UnitPriceInput"].sum() - tgt["Unit Price WRK"].sum(), 2),
        ],
    })
    revenue_summary = pd.DataFrame({
        "Metric": ["Revenue Match Count", "Revenue Mismatch Count",
                   "Source Revenue Total", "Tenant Revenue Total", "Revenue Variance"],
        "Value": [
            len(revenue_match), len(revenue_mismatch),
            round(source_agg["TotalOrderPrice"].sum(), 2),
            round(tgt["Cons_Revenue"].sum(), 2),
            round(source_agg["TotalOrderPrice"].sum() - tgt["Cons_Revenue"].sum(), 2),
        ],
    })

    records = len(intersection)
    # A record is passed only when both ASP and revenue reconcile.
    passed = len(matched[
        (matched["Price_SRC"] == matched["Price_TGT"])
        & (matched["Revenue_SRC"] == matched["Revenue_TGT"])
    ])
    failed = records - passed
    match_pct = passed / records * 100 if records else 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"ASP_Reconciliation_Output_{timestamp}.xlsx"

    write_frames(output_file, {
        "Summary": summary,
        "ASP_Summary": asp_summary,
        "Revenue_Summary": revenue_summary,
        "PriceMismatch": price_mismatch,
        "RevenueMismatch": revenue_mismatch,
        "SourceMissingSample": source_missing.head(5000),
        "TargetExtraSample": target_extra.head(5000),
    })

    details = {
        "Source Raw Count": source_raw_count,
        "Source Aggregated Count": source_agg_count,
        "Tenant Count": len(tgt),
        "Intersection": records,
        "Price Match": len(price_match),
        "Price Mismatch": len(price_mismatch),
        "Revenue Match": len(revenue_match),
        "Revenue Mismatch": len(revenue_mismatch),
        "Source Missing": len(source_missing),
        "Target Extra": len(target_extra),
        "Match %": round(match_pct, 2),
    }
    for key, value in details.items():
        log(log_callback, f"{key:<28}: {value}")
    log(log_callback, f"Excel Report Generated: {output_file}")

    return ValidationResult(
        name="o9 Compare Past ASP",
        output_file=str(output_file),
        records=records,
        passed=passed,
        failed=failed,
        match_pct=match_pct,
        details=details,
    )
