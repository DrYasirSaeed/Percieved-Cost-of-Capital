"""
04_merge_validate.py
=====================
Firm-level overlap validation and model-ready panel export.

PURPOSE
-------
This script:
  (a) Validates P8 ROIC reconstruction: compares reconstructed P8 from the
      old file against full-precision P8_precomp from FY25 for the 377 firms
      present in both files over FY2020-FY2023.
  (b) Documents raw variable discrepancies in the overlap period.
  (c) Exports four model-ready CSVs for use in regression scripts.

OUTPUTS
-------
  05_model_ready_old.csv        -- old file panel, all firms, all variables
  06_model_ready_fy25.csv       -- FY25 panel, all firms, all variables
  07_p8_reconstruction_check.csv -- per-firm-year P8 comparison (old vs FY25)
  08_overlap_discrepancy.csv    -- per-firm-year raw variable % differences

HOW TO USE THE MODEL-READY FILES IN REGRESSION
------------------------------------------------
Filter rows using the pre-computed flag columns:
  in_model1_sample == True     -> Models 1 and 2 (Inv_Rate available)
  in_model3_sample == True     -> Model 3 (CoC_Proxy_L2 available)
  balanced_subsample == True   -> Balanced panel robustness check
  zero_interest == False       -> Debt-carrying firms only (robustness)
  non_june_fye == False        -> Exclude non-June FYE firms (FY25 panel only)
  robustness_excl == False     -> Exclude Fuel & Energy and Cement (robustness)

Reference: FirmLevel_DataStrategy.docx section 7.
"""

import os
import sys
import pandas as pd
import numpy as np

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

PROJECT_DIR   = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

INPUT_OLD  = os.path.join(EXTRACTED_DIR, "03_firm_panel_old_computed.csv")
INPUT_FY25 = os.path.join(EXTRACTED_DIR, "04_firm_panel_fy25_computed.csv")

OUTPUT_MODEL_OLD  = os.path.join(EXTRACTED_DIR, "05_model_ready_old.csv")
OUTPUT_MODEL_FY25 = os.path.join(EXTRACTED_DIR, "06_model_ready_fy25.csv")
OUTPUT_P8_CHECK   = os.path.join(EXTRACTED_DIR, "07_p8_reconstruction_check.csv")
OUTPUT_OVERLAP    = os.path.join(EXTRACTED_DIR, "08_overlap_discrepancy.csv")

OVERLAP_YEARS = [2020, 2021, 2022, 2023]
OVERLAP_VARS  = ["OFA_cost", "InterestExpense", "D_NCL", "E_CL",
                 "TotalAssets", "EBIT", "Sales", "CapEmployed"]


def check_p8_reconstruction(df_old, df_fy25):
    """
    Compare P8 reconstructed from raw items (old file) against full-precision
    P8_precomp (FY25 file) for the firms present in both files.

    Mean absolute difference <= 0.5 pp confirms reconstruction is correct.
    """
    old_ov = df_old[df_old["fiscal_year"].isin(OVERLAP_YEARS)][
        ["firm_id", "sector", "fiscal_year", "P8_ROIC"]
    ].rename(columns={"P8_ROIC": "P8_old_reconstructed"})

    fy25_ov = df_fy25[df_fy25["fiscal_year"].isin(OVERLAP_YEARS)][
        ["firm_id", "fiscal_year", "P8_ROIC"]
    ].rename(columns={"P8_ROIC": "P8_fy25_direct"})

    merged = old_ov.merge(fy25_ov, on=["firm_id", "fiscal_year"], how="inner")
    merged["abs_diff_pp"] = (
        (merged["P8_old_reconstructed"] - merged["P8_fy25_direct"]).abs() * 100
    )

    n_obs  = len(merged)
    mad    = merged["abs_diff_pp"].mean()
    pct_ok = 100 * (merged["abs_diff_pp"] <= 0.5).sum() / n_obs if n_obs else 0

    print(f"\n--- P8 reconstruction validation ---")
    print(f"  Overlap obs compared: {n_obs:,}  "
          f"({merged['firm_id'].nunique():,} firms)")
    print(f"  Mean absolute difference: {mad:.3f} pp")
    print(f"  Obs within 0.5 pp tolerance: {pct_ok:.1f}%")
    if mad > 0.5:
        print("  WARNING: mean diff > 0.5 pp -- review reconstruction logic")
    else:
        print("  OK: reconstruction matches FY25 KPI within tolerance")
    return merged


def compute_raw_discrepancies(df_old, df_fy25):
    """
    Compute percentage differences between the two publications' raw values
    for the FY2020-FY2023 overlap, documenting the sample-composition divergence.
    """
    id_cols = ["firm_id", "sector", "fiscal_year"]
    old_sub  = df_old[df_old["fiscal_year"].isin(OVERLAP_YEARS)][
        id_cols + [v for v in OVERLAP_VARS if v in df_old.columns]
    ]
    fy25_sub = df_fy25[df_fy25["fiscal_year"].isin(OVERLAP_YEARS)][
        id_cols + [v for v in OVERLAP_VARS if v in df_fy25.columns]
    ]
    merged = old_sub.merge(fy25_sub, on=id_cols, suffixes=("_old", "_fy25"))

    for var in OVERLAP_VARS:
        old_col  = var + "_old"
        fy25_col = var + "_fy25"
        if old_col in merged.columns and fy25_col in merged.columns:
            merged[var + "_pct_diff"] = np.where(
                merged[old_col].notna() & (merged[old_col] != 0),
                100 * (merged[old_col] - merged[fy25_col]).abs() / merged[old_col].abs(),
                np.nan,
            )

    print("\n--- Raw variable discrepancy (FY2020-FY2023 overlap, median % diff) ---")
    print(f"  {'Variable':<25s}  {'Median':>8s}  {'p75':>8s}  {'Max':>8s}")
    print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*8}")
    for var in OVERLAP_VARS:
        col = var + "_pct_diff"
        if col not in merged.columns:
            continue
        med = merged[col].median()
        p75 = merged[col].quantile(0.75)
        mx  = merged[col].max()
        if pd.isna(med):
            continue
        flag = "  ***" if med > 10 else ""
        print(f"  {var:<25s}  {med:>8.1f}  {p75:>8.1f}  {mx:>8.1f}{flag}")

    return merged


def export_model_ready(df, output_path, label):
    """
    Save the full computed panel.  No rows dropped -- use flag columns to
    select the appropriate estimation sample in the regression script.
    """
    df = df.sort_values(["firm_id", "fiscal_year"]).reset_index(drop=True)

    n_firms = df["firm_id"].nunique()
    n_obs   = len(df)
    flags   = {
        "in_model1_sample":   "Inv_Rate not NaN",
        "in_model3_sample":   "CoC_Proxy_L2 not NaN",
        "balanced_subsample": "balanced panel",
        "zero_interest":      "zero-interest obs",
        "negative_equity":    "negative equity obs",
    }
    print(f"\n{label}:")
    print(f"  Firms: {n_firms:,}  |  Obs: {n_obs:,}")
    for col, desc in flags.items():
        if col in df.columns:
            print(f"  {col}: {df[col].sum():,}  ({desc})")

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"  Saved -> {output_path}")
    return df


def run():
    """Run all validation checks and export model-ready panels."""
    print("=" * 65)
    print("Script 04 -- Firm-level validation and model-ready export")
    print("=" * 65)

    df_old  = pd.read_csv(INPUT_OLD)
    df_fy25 = pd.read_csv(INPUT_FY25)
    print(f"OLD panel:  {len(df_old):,} rows  ({df_old['firm_id'].nunique():,} firms)")
    print(f"FY25 panel: {len(df_fy25):,} rows  ({df_fy25['firm_id'].nunique():,} firms)")

    p8_check = check_p8_reconstruction(df_old, df_fy25)
    p8_check.to_csv(OUTPUT_P8_CHECK, index=False, encoding="utf-8-sig")
    print(f"  Saved -> {OUTPUT_P8_CHECK}")

    overlap = compute_raw_discrepancies(df_old, df_fy25)
    overlap.to_csv(OUTPUT_OVERLAP, index=False, encoding="utf-8-sig")
    print(f"  Saved -> {OUTPUT_OVERLAP}")

    df_old_out  = export_model_ready(df_old,  OUTPUT_MODEL_OLD,  "OLD (2014-23) model-ready")
    df_fy25_out = export_model_ready(df_fy25, OUTPUT_MODEL_FY25, "FY25 model-ready")

    print("\n" + "=" * 65)
    print("REMINDER: Fill r_SBP and CPI_inflation placeholders before regression.")
    print("  Source: SBP Monetary Policy History (Jul-Jun annual averages)")
    print("  Source: PBS Consumer Price Index")
    print("=" * 65)

    return df_old_out, df_fy25_out, p8_check, overlap


if __name__ == "__main__":
    run()
