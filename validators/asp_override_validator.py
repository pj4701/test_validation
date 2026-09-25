from __future__ import annotations

from datetime import datetime
from pathlib import Path
import gc
import pandas as pd

from .base import ValidationResult, clean_columns, log, require_files, write_frames


REQUIRED = [
    "ASP Override Source File",
    "ASP Current Future Target File",
    "Demand Domain Mapping File",
    "ASP Rejection File",
]
MAX_EXCEL_ROWS = 1_000_000


def _read_rejection_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        total = max(sum(1 for _ in f) - 1, 0)
    rej = pd.read_csv(
        path, engine="python", on_bad_lines="skip", encoding_errors="ignore"
    )
    rej = clean_columns(rej)
    rej.rename(columns={rej.columns[-1]: "Rejection Reason"}, inplace=True)
    return rej, total


def run_validation(files: dict, output_dir: str | Path = "outputs",
                   log_callback=None) -> ValidationResult:
    require_files(files, REQUIRED)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log(log_callback, "========== ASP OVERRIDE CURRENT & FUTURE ==========")

    src = clean_columns(pd.read_csv(files["ASP Override Source File"]))
    tgt = clean_columns(pd.read_csv(files["ASP Current Future Target File"]))
    map_df = clean_columns(pd.read_csv(files["Demand Domain Mapping File"]))
    rej, total_rejection_records = _read_rejection_file(files["ASP Rejection File"])

    log(log_callback, f"Source Rows : {len(src):,}")
    log(log_callback, f"Target Rows : {len(tgt):,}")
    log(log_callback, f"Rejection Records In File : {total_rejection_records:,}")
    log(log_callback, f"Rejection Rows Loaded : {len(rej):,}")

    lookup_dict = dict(zip(
        map_df["Demand Domain.[Planning Demand Domain$DisplayName]"],
        map_df["Demand Domain.[End Market Child Code]"]
    ))

    src["Planning Demand Domain"] = (
        src["End Market.[End Market Child]"].astype(str).str.strip().map(lookup_dict)
    )
    unmapped = src[src["Planning Demand Domain"].isna()].copy()

    src["Planning Account"] = (
        src["SoldTo Customer.[Sold To]"].astype(str).str.split(":").str[-1].str.strip()
    )
    src["Planning Region"] = (
        src["Ship To Region.[Ship To]"].astype(str).str.split(":").str[-1].str.strip()
    )

    rej["Planning Demand Domain"] = (
        rej["End Market.[End Market Child]"].astype(str).str.strip().map(lookup_dict)
    )
    rej["Planning Account"] = (
        rej["SoldTo Customer.[Sold To]"].astype(str).str.split(":").str[-1].str.strip()
    )
    rej["Planning Region"] = (
        rej["Ship To Region.[Ship To]"].astype(str).str.split(":").str[-1].str.strip()
    )

    rej.rename(columns={
        "Product.[Product ID]": "Planning Item",
        "[Time].[Month]": "Month",
    }, inplace=True)

    src.rename(columns={
        "Product.[Product ID]": "Planning Item",
        "[Time].[Month]": "Month",
        "Average Sales Price Override": "Unit Price Override WRK",
    }, inplace=True)

    tgt.rename(columns={
        "Item.[Planning Item]": "Planning Item",
        "Demand Domain.[Planning Demand Domain]": "Planning Demand Domain",
        "Account.[Planning Account]": "Planning Account",
        "Region.[Planning Region]": "Planning Region",
        "Time.[Month]": "Month",
    }, inplace=True)

    keys = [
        "Planning Item", "Planning Demand Domain",
        "Planning Account", "Planning Region", "Month"
    ]
    for col in keys:
        src[col] = src[col].astype(str).str.strip()
        tgt[col] = tgt[col].astype(str).str.strip()
        rej[col] = rej[col].astype(str).str.strip()

    src["Unit Price Override WRK"] = pd.to_numeric(
        src["Unit Price Override WRK"], errors="coerce"
    )
    tgt["Unit Price Override WRK"] = pd.to_numeric(
        tgt["Unit Price Override WRK"], errors="coerce"
    )

    src_dup = int(src.duplicated(subset=keys).sum())
    tgt_dup = int(tgt.duplicated(subset=keys).sum())

    merged = pd.merge(
        src, tgt, on=keys, how="outer", indicator=True, suffixes=("_SRC", "_TGT")
    )
    source_only = merged[merged["_merge"] == "left_only"].copy()
    target_only = merged[merged["_merge"] == "right_only"].copy()
    both_mask = merged["_merge"] == "both"
    intersection_count = int(both_mask.sum())

    price_mismatch = merged[
        both_mask
        & (
            merged["Unit Price Override WRK_SRC"].fillna(-999999).round(4)
            != merged["Unit Price Override WRK_TGT"].fillna(-999999).round(4)
        )
    ].copy()

    matched_count = intersection_count - len(price_mismatch)

    rejection_summary = (
        rej["Rejection Reason"].value_counts().reset_index()
    )
    rejection_summary.columns = ["Rejection Reason", "Count"]

    source_only_rejected = pd.merge(
        source_only,
        rej[keys + ["Rejection Reason"]],
        on=keys,
        how="inner",
    )

    rejection_pct = (
        total_rejection_records / len(src) * 100
        if len(src) else 0
    )
    accepted_pct = 100 - rejection_pct

    summary_df = pd.DataFrame({
        "Metric": [
            "Source Records", "Target Records",
            "Rejected Records In File", "Rejected Records Loaded",
            "Rejected Records Parse Failed", "Unmapped Demand Domains",
            "SourceOnly Found In Rejections", "Intersection Count",
            "Matched Records", "Price Mismatch", "Source Only Records",
            "Target Only Records", "% Rejection", "% Accepted",
            "Source Duplicate Keys", "Target Duplicate Keys",
        ],
        "Count": [
            len(src), len(tgt), total_rejection_records, len(rej),
            total_rejection_records - len(rej), len(unmapped),
            len(source_only_rejected), intersection_count,
            matched_count, len(price_mismatch), len(source_only),
            len(target_only), f"{rejection_pct:.2f}%", f"{accepted_pct:.2f}%",
            src_dup, tgt_dup,
        ],
    })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    main_output = output_dir / f"ASP_Current_Future_Comparison_{timestamp}.xlsx"

    write_frames(main_output, {
        "Summary": summary_df,
        "PriceMismatch": price_mismatch,
        "SourceOnly": source_only,
        "RejectedRecords": source_only_rejected,
        "RejectionSummary": rejection_summary,
        "UnmappedDomains": unmapped,
    })

    # Preserve the original large TargetOnly split behavior.
    target_only_files = []
    total_chunks = (len(target_only) + MAX_EXCEL_ROWS - 1) // MAX_EXCEL_ROWS
    for i in range(total_chunks):
        chunk = target_only.iloc[
            i * MAX_EXCEL_ROWS : min((i + 1) * MAX_EXCEL_ROWS, len(target_only))
        ].copy()
        part_file = output_dir / f"TargetOnly_Part_{i+1}_{timestamp}.xlsx"
        write_frames(part_file, {"TargetOnly": chunk})
        target_only_files.append(str(part_file))
        del chunk
        gc.collect()

    records = intersection_count
    match_pct = matched_count / records * 100 if records else 0

    details = {
        "Source Records": len(src),
        "Target Records": len(tgt),
        "Intersection": records,
        "Matched Records": matched_count,
        "Price Mismatch": len(price_mismatch),
        "Source Only": len(source_only),
        "Target Only": len(target_only),
        "Rejected Loaded": len(rej),
        "SourceOnly Rejected": len(source_only_rejected),
        "Unmapped Domains": len(unmapped),
        "Match %": round(match_pct, 2),
        "TargetOnly Files": len(target_only_files),
    }
    for key, value in details.items():
        log(log_callback, f"{key:<28}: {value}")
    log(log_callback, f"Main Report: {main_output}")
    for f in target_only_files:
        log(log_callback, f"TargetOnly Part: {f}")

    return ValidationResult(
        name="ASP Override Current & Future",
        output_file=str(main_output),
        records=records,
        passed=matched_count,
        failed=len(price_mismatch),
        match_pct=match_pct,
        details=details,
    )
