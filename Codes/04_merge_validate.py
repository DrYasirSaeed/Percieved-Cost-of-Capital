"""
04_merge_validate.py
=====================
Validate the FY2020€“FY2023 overlap between the two panels and produce a
final model-ready export for each panel.

PURPOSE
-------
Both the old (2005-23) and FY25 workbooks cover FY2020€“FY2023.  Their values
for this shared period are NOT identical because each publication covers a
different set of firms.  Per the research design:

  - Do NOT merge the two files into a single pooled panel.
  - Use the old file as the MAIN estimation panel (Models 1, 2, 3).
  - Use the FY25 file as an INDEPENDENT validation panel (out-of-sample check).
  - Report the overlap discrepancies explicitly in the methodology section.

This script:
  (a) Computes percentage discrepancies for key variables in FY2020€“FY2023.
  (b) Checks whether any sector's FY2020 discrepancy is within 5% for all
      core variables (a prerequisite for the optional unified panel discussed
      in Section 5.1 of the extraction guide).
  (c) Exports four final CSVs:
        05_model_ready_old.csv        €” main estimation panel, est. sectors only
        06_model_ready_fy25.csv       €” FY25 validation panel, est. sectors only
        07_overlap_comparison.csv     €” side-by-side overlap discrepancy table
        08_allsector_validation.csv   €” All Sector aggregate from both files
                                        for descriptive validation

INPUTS
------
  Extracted Data/03_panel_old_computed.csv
  Extracted Data/04_panel_fy25_computed.csv

OUTPUTS
-------
  Extracted Data/05_model_ready_old.csv
  Extracted Data/06_model_ready_fy25.csv
  Extracted Data/07_overlap_comparison.csv
  Extracted Data/08_allsector_validation.csv

Reference: DataStrategy_ExtractionGuide.docx Â§2.3, Â§5.1.
"""

import os
import sys
import pandas as pd
import numpy as np

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
PROJECT_DIR   = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

INPUT_OLD  = os.path.join(EXTRACTED_DIR, "03_panel_old_computed.csv")
INPUT_FY25 = os.path.join(EXTRACTED_DIR, "04_panel_fy25_computed.csv")

OUTPUT_MODEL_OLD   = os.path.join(EXTRACTED_DIR, "05_model_ready_old.csv")
OUTPUT_MODEL_FY25  = os.path.join(EXTRACTED_DIR, "06_model_ready_fy25.csv")
OUTPUT_OVERLAP     = os.path.join(EXTRACTED_DIR, "07_overlap_comparison.csv")
OUTPUT_ALLSECTOR   = os.path.join(EXTRACTED_DIR, "08_allsector_validation.csv")

# Overlap years present in both files
OVERLAP_YEARS = [2020, 2021, 2022, 2023]

# Variables compared in the overlap validation
OVERLAP_VARS = [
    "OFA_cost", "InterestExpense", "D_NCL", "E_CL", "TotalAssets",
    "EBIT", "Sales", "CoC_Proxy_raw", "Inv_Rate_raw", "P8_precomp",
]

# Sectors in the estimation panel (no All Sector)
ESTIMATION_CODES = {
    "704","705","706","707","709","710","711","712",
    "714","715","726","727","728","729"
}

# Threshold for the optional unified-panel check (Section 5.1)
OVERLAP_THRESHOLD_PCT = 5.0


# ---------------------------------------------------------------------------
# Overlap validation
# ---------------------------------------------------------------------------

def compute_overlap_discrepancies(df_old: pd.DataFrame,
                                   df_fy25: pd.DataFrame) -> pd.DataFrame:
    """
    For each (sector, fiscal_year) in the overlap window (FY2020€“FY2023),
    compute the absolute percentage difference between the two panels for
    each core variable.

    Pct_diff = 100 * |old_value - fy25_value| / |old_value|
    (where old_value is used as the reference; set to NaN if old_value = 0)

    Args:
        df_old:  Computed old-file panel.
        df_fy25: Computed FY25 panel.

    Returns:
        DataFrame with one row per (sector_code, fiscal_year) in the overlap,
        with columns for old values, FY25 values, and percentage differences.
    """
    # Restrict to overlap years and estimation sectors + All Sector
    old_overlap = df_old[
        df_old["fiscal_year"].isin(OVERLAP_YEARS) &
        (df_old["sector_code"].isin(ESTIMATION_CODES) | (df_old["sector_code"] == "703"))
    ].copy()

    fy25_overlap = df_fy25[
        df_fy25["fiscal_year"].isin(OVERLAP_YEARS) &
        (df_fy25["sector_code"].isin(ESTIMATION_CODES) | (df_fy25["sector_code"] == "703"))
    ].copy()

    id_cols = ["sector_code", "sector_name", "fiscal_year"]
    old_sub  = old_overlap[id_cols  + [v for v in OVERLAP_VARS if v in old_overlap.columns]]
    fy25_sub = fy25_overlap[id_cols + [v for v in OVERLAP_VARS if v in fy25_overlap.columns]]

    merged = old_sub.merge(
        fy25_sub,
        on=["sector_code", "sector_name", "fiscal_year"],
        suffixes=("_old", "_fy25"),
    )

    # Compute absolute percentage differences
    for var in OVERLAP_VARS:
        old_col  = var + "_old"
        fy25_col = var + "_fy25"
        diff_col = var + "_pct_diff"
        if old_col in merged.columns and fy25_col in merged.columns:
            merged[diff_col] = np.where(
                (merged[old_col].notna()) & (merged[old_col] != 0),
                100.0 * (merged[old_col] - merged[fy25_col]).abs() / merged[old_col].abs(),
                np.nan
            )

    return merged


def print_overlap_summary(overlap: pd.DataFrame) -> None:
    """
    Print the median percentage discrepancy for each variable in the overlap
    window, flagging variables with a median discrepancy above 5%.

    Args:
        overlap: DataFrame from compute_overlap_discrepancies().
    """
    print("\n--- Overlap discrepancy summary (FY2020-FY2023 median % diff) ---")
    print(f"  {'Variable':<25s}  {'Median %diff':>12s}  {'Max %diff':>10s}  Flag")
    print(f"  {'-'*25}  {'-'*12}  {'-'*10}  ----")
    for var in OVERLAP_VARS:
        diff_col = var + "_pct_diff"
        if diff_col not in overlap.columns:
            continue
        med = overlap[diff_col].median()
        mx  = overlap[diff_col].max()
        if pd.isna(med):
            print(f"  {var:<25s}  {'N/A':>12s}  {'N/A':>10s}")
            continue
        flag = "  *** MATERIAL" if med > OVERLAP_THRESHOLD_PCT else ""
        print(f"  {var:<25s}  {med:12.1f}  {mx:10.1f}{flag}")


def check_unified_panel_feasibility(overlap: pd.DataFrame) -> None:
    """
    For each sector, check whether ALL core overlap variables in FY2020 are
    within the 5% threshold.  Sectors meeting this criterion could potentially
    be included in an optional unified panel (see guide Â§5.1).

    Args:
        overlap: DataFrame from compute_overlap_discrepancies().
    """
    fy2020 = overlap[overlap["fiscal_year"] == 2020].copy()
    diff_cols = [v + "_pct_diff" for v in ["InterestExpense", "TotalAssets", "EBIT", "Sales"]
                 if v + "_pct_diff" in fy2020.columns]

    if not diff_cols:
        return

    fy2020["all_within_5pct"] = (fy2020[diff_cols] < OVERLAP_THRESHOLD_PCT).all(axis=1)
    eligible = fy2020[fy2020["all_within_5pct"]]["sector_name"].tolist()
    print(f"\n  Sectors with FY2020 discrepancy < 5% on all core vars: "
          f"{len(eligible)} / {len(fy2020)}")
    if eligible:
        print("   †’", ", ".join(eligible))
    print("  (Note: even eligible sectors should be treated cautiously in a "
          "unified panel.  The default is separate panels per the research design.)")


# ---------------------------------------------------------------------------
# Final export helpers
# ---------------------------------------------------------------------------

def export_model_ready(df: pd.DataFrame,
                        output_path: str,
                        label: str) -> pd.DataFrame:
    """
    Filter to estimation sectors only and select the columns most relevant
    for econometric estimation.  The model-ready file is a subset of the
    full computed panel €” all intermediate columns are retained.

    Args:
        df:          Full computed panel (includes All Sector).
        output_path: Destination CSV.
        label:       Display label.

    Returns:
        Filtered DataFrame.
    """
    est = df[df["sector_code"].isin(ESTIMATION_CODES)].copy()

    # Sort for a clean, readable output
    est = est.sort_values(["sector_code", "fiscal_year"]).reset_index(drop=True)

    # Print panel summary
    n_obs = len(est)
    n_m1  = est["in_model1_sample"].sum() if "in_model1_sample" in est.columns else "N/A"
    n_m3  = est["in_model3_sample"].sum() if "in_model3_sample" in est.columns else "N/A"
    print(f"\n{label} model-ready panel:")
    print(f"  Total sector-year obs: {n_obs}")
    print(f"  Model 1/2 sample:      {n_m1}  (Inv_Rate not NaN)")
    print(f"  Model 3 sample:        {n_m3}  (CoC_Proxy_L2 not NaN)")

    est.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"  Saved †’ {output_path}")
    return est


def export_allsector_validation(df_old: pd.DataFrame,
                                 df_fy25: pd.DataFrame,
                                 output_path: str) -> None:
    """
    Stack All Sector rows from both files into a single comparison table
    for use as a descriptive validation check in the paper.

    Args:
        df_old:      Old-file computed panel.
        df_fy25:     FY25 computed panel.
        output_path: Destination CSV.
    """
    allsec_old  = df_old[df_old["sector_code"] == "703"].copy()
    allsec_fy25 = df_fy25[df_fy25["sector_code"] == "703"].copy()

    combined = pd.concat([allsec_old, allsec_fy25], ignore_index=True)
    combined = combined.sort_values(["source_file", "fiscal_year"])

    combined.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nAll Sector validation table saved †’ {output_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> tuple:
    """
    Load computed panels, run overlap validation, and export model-ready files.

    Returns:
        Tuple of (df_old_est, df_fy25_est, overlap_df).
    """
    print("=" * 65)
    print("Script 04 €” Merge validation and model-ready export")
    print("=" * 65)

    df_old  = pd.read_csv(INPUT_OLD,  dtype={"sector_code": str})
    df_fy25 = pd.read_csv(INPUT_FY25, dtype={"sector_code": str})
    print(f"Loaded OLD panel:  {len(df_old)} rows")
    print(f"Loaded FY25 panel: {len(df_fy25)} rows")

    # --- Overlap validation ---
    overlap = compute_overlap_discrepancies(df_old, df_fy25)
    print_overlap_summary(overlap)
    check_unified_panel_feasibility(overlap)

    overlap.to_csv(OUTPUT_OVERLAP, index=False, encoding="utf-8-sig")
    print(f"\nOverlap comparison saved †’ {OUTPUT_OVERLAP}")

    # --- All Sector validation table ---
    export_allsector_validation(df_old, df_fy25, OUTPUT_ALLSECTOR)

    # --- Model-ready panels ---
    df_old_est  = export_model_ready(df_old,  OUTPUT_MODEL_OLD,  "OLD (2014-23)")
    df_fy25_est = export_model_ready(df_fy25, OUTPUT_MODEL_FY25, "FY25")

    print("\n" + "=" * 65)
    print("All outputs written.  See Extracted Data/ for CSV files.")
    print("REMINDER: Fill in the r_SBP and CPI_inflation placeholder")
    print("columns in 05_model_ready_old.csv and 06_model_ready_fy25.csv")
    print("before running any regression.  Source: SBP Monetary Policy")
    print("History and Pakistan Bureau of Statistics.")
    print("=" * 65)

    return df_old_est, df_fy25_est, overlap


if __name__ == "__main__":
    run()

