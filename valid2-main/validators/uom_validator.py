from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

from .base import ValidationResult, clean_columns, log, require_files, write_frames


REQUIRED = ["UOM Source File", "UOM Target File", "Item File"]


def get_reference_uom(segment):
    segment = str(segment).strip().upper()
    if segment == "CORRUGATED PACKAGING":
        return "MSF"
    if segment == "CONSUMER PACKAGING":
        return "EA"
    if segment in ("CORRUGATED MILL GROUP", "CONSUMER PACKAGING MILLS"):
        return "TONS"
    return None


def run_validation(files: dict, output_dir: str | Path = "outputs",
                   log_callback=None) -> ValidationResult:
    require_files(files, REQUIRED)
    output_dir = Path(output_dir)

    log(log_callback, "========== UOM CONVERSION VALIDATION ==========")

    src = clean_columns(pd.read_csv(
        files["UOM Source File"], sep="^", dtype=str, low_memory=False
    ))
    item = clean_columns(pd.read_csv(
        files["Item File"], sep="^", dtype=str, low_memory=False
    ))
    tgt = clean_columns(pd.read_csv(
        files["UOM Target File"], dtype=str, low_memory=False
    ))

    src["ProductID"] = src["ProductID"].astype(str).str.strip()
    src["UOM"] = src["UOM"].astype(str).str.strip()
    item["Item"] = item["Item"].astype(str).str.strip()
    tgt["Item.[Planning Item]"] = tgt["Item.[Planning Item]"].astype(str).str.strip()
    tgt["UOM.[UOM]"] = tgt["UOM.[UOM]"].astype(str).str.strip()

    src["UOMConversion"] = pd.to_numeric(src["UOMConversion"], errors="coerce")
    tgt["UOM Conversion"] = pd.to_numeric(tgt["UOM Conversion"], errors="coerce")

    source_raw_count = len(src)

    agg_details = (
        src.groupby(["ProductID", "UOM"], as_index=False)
        .agg(
            Record_Count=("UOMConversion", "count"),
            Sum_UOMConversion=("UOMConversion", "sum"),
        )
    )
    agg_details = agg_details[agg_details["Record_Count"] > 1].copy()
    agg_details["Records_Reduced"] = agg_details["Record_Count"] - 1
    aggregation_reduced_count = int(agg_details["Records_Reduced"].sum())

    src_agg = (
        src.groupby(["ProductID", "UOM"], as_index=False)["UOMConversion"]
        .sum()
    )
    source_agg_count = len(src_agg)

    item_lookup = item[["Item", "W_BusinessSegmentName"]].drop_duplicates()
    src_agg = src_agg.merge(
        item_lookup, left_on="ProductID", right_on="Item", how="left"
    )

    src_agg["Reference_UOM"] = src_agg["W_BusinessSegmentName"].apply(get_reference_uom)

    reference_df = src_agg[
        src_agg["UOM"] == src_agg["Reference_UOM"]
    ][["ProductID", "UOMConversion"]].copy()
    reference_df.rename(columns={"UOMConversion": "Reference_Value"}, inplace=True)

    src_agg = src_agg.merge(reference_df, on="ProductID", how="left")
    src_agg = src_agg[src_agg["Reference_Value"].fillna(0) != 0].copy()

    src_agg["Expected_Conversion"] = (
        src_agg["UOMConversion"] / src_agg["Reference_Value"]
    )

    src_agg["BusinessKey"] = src_agg["ProductID"] + "|" + src_agg["UOM"]
    tgt["BusinessKey"] = (
        tgt["Item.[Planning Item]"] + "|" + tgt["UOM.[UOM]"]
    )

    src_final = src_agg[[
        "BusinessKey", "ProductID", "UOM", "W_BusinessSegmentName",
        "Reference_UOM", "Reference_Value", "Expected_Conversion"
    ]]

    tgt_final = tgt[[
        "BusinessKey", "Item.[Planning Item]", "UOM.[UOM]", "UOM Conversion"
    ]]

    recon = pd.merge(src_final, tgt_final, on="BusinessKey", how="outer", indicator=True)
    source_missing = recon[recon["_merge"] == "left_only"].copy()
    target_extra = recon[recon["_merge"] == "right_only"].copy()
    common = recon[recon["_merge"] == "both"].copy()

    common["Expected_Rounded"] = common["Expected_Conversion"].round(3)
    common["Target_Rounded"] = common["UOM Conversion"].round(3)

    mismatch_records = common[
        common["Expected_Rounded"] != common["Target_Rounded"]
    ].copy()
    mismatch_records["Difference"] = (
        mismatch_records["Expected_Rounded"] - mismatch_records["Target_Rounded"]
    )

    source_missing_pct = (
        len(source_missing) / source_agg_count * 100
        if source_agg_count else 0
    )

    summary = pd.DataFrame({
        "Metric": [
            "Source Raw Count", "Source Aggregated Count", "Target Count",
            "Records Reduced By Aggregation", "Source Missing Count",
            "Target Extra Count", "Conversion Mismatch Count", "Source Missing %",
        ],
        "Value": [
            source_raw_count, source_agg_count, len(tgt_final),
            aggregation_reduced_count, len(source_missing),
            len(target_extra), len(mismatch_records), round(source_missing_pct, 2),
        ],
    })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"UOM_Conversion_Reconciliation_{timestamp}.xlsx"

    write_frames(output_file, {
        "Summary": summary,
        "Aggregation_Duplicates": agg_details,
        "Source_Missing": source_missing,
        "Target_Extra": target_extra,
        "Conversion_Mismatch": mismatch_records,
    })

    records = len(common)
    passed = records - len(mismatch_records)
    match_pct = passed / records * 100 if records else 0

    details = {
        "Source Raw Count": source_raw_count,
        "Source Aggregated Count": source_agg_count,
        "Target Count": len(tgt_final),
        "Records Reduced By Aggregation": aggregation_reduced_count,
        "Source Missing": len(source_missing),
        "Target Extra": len(target_extra),
        "Conversion Mismatch": len(mismatch_records),
        "Match %": round(match_pct, 2),
    }
    for key, value in details.items():
        log(log_callback, f"{key:<35}: {value}")
    log(log_callback, f"Excel Report Generated: {output_file}")

    return ValidationResult(
        name="UOM Conversion Validation",
        output_file=str(output_file),
        records=records,
        passed=passed,
        failed=len(mismatch_records),
        match_pct=match_pct,
        details=details,
    )
