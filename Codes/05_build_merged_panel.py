"""
05_build_merged_panel.py
========================
Build a stitched firm-level panel spanning FY2015-FY2025 from the two
SBP FSA publications.

STRATEGY
--------
The two model-ready panels cannot be pooled without care:
  - The overlap years FY2020-FY2023 show revised financials across the two
    publications; stacking both copies would duplicate observations.
  - Firms affected by mergers, acquisitions, or major restructuring produce
    large P8 discrepancies in the overlap period — they are excluded entirely.

Construction:
  OLD  contribution : FY2015-FY2023 (drop FY2014, base year only)
  FY25 contribution : FY2024-FY2025 (exclude the overlap years FY2020-FY2023
                      to prevent duplicates)

Exclusion criterion (Step 1):
  A firm is flagged as restructuring-affected if its mean absolute P8
  difference between the two publications (07_p8_reconstruction_check.csv)
  exceeds 2.0 percentage points across all overlap years.

After stacking, CoC_Proxy lags are recomputed within the merged time series
so that FY2024 observations correctly inherit CoC_Proxy from FY2023.

INPUTS
------
  Extracted Data/05_model_ready_old.csv
  Extracted Data/06_model_ready_fy25.csv
  Extracted Data/07_p8_reconstruction_check.csv

OUTPUTS
-------
  Extracted Data/excluded_firms.csv     -- exclusion list
  Extracted Data/09_merged_panel.csv    -- stitched model-ready panel

FLAG COLUMNS
------------
  source_file         : "old" | "fy25"
  post2023            : 1 for fiscal_year >= 2024, else 0
  in_model1_sample    : Inv_Rate and CoC_Proxy both non-null
  in_model3_sample    : in_model1_sample and CoC_Proxy_L2 non-null
  balanced_subsample  : firm present in all expected years given its source
  zero_interest       : InterestExpense == 0
  negative_equity     : ShareholdersEquity_C < 0
  non_june_fye        : non-June fiscal year-end (FY25 rows only)
  robustness_excl     : Fuel & Energy or Cement sector

Reference: FirmLevel_DataStrategy.docx; Gormsen & Huber (2024, 2025).
"""

import os
import sys
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CODES_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR   = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

INPUT_OLD      = os.path.join(EXTRACTED_DIR, "05_model_ready_old.csv")
INPUT_FY25     = os.path.join(EXTRACTED_DIR, "06_model_ready_fy25.csv")
INPUT_P8_CHECK = os.path.join(EXTRACTED_DIR, "07_p8_reconstruction_check.csv")

OUTPUT_EXCL   = os.path.join(EXTRACTED_DIR, "excluded_firms.csv")
OUTPUT_MERGED = os.path.join(EXTRACTED_DIR, "09_merged_panel.csv")

P8_DIFF_THRESHOLD = 2.0   # pp -- firms above this are flagged as restructured

ROBUSTNESS_EXCL_SECTORS = {"Fuel and Energy Sector", "Fuel and Energy", "Cement"}


# ---------------------------------------------------------------------------
# Step 1 -- Build exclusion list
# ---------------------------------------------------------------------------

def build_exclusion_list(p8_path: str) -> set:
    """
    Load the P8 reconstruction check file and flag firms whose mean absolute
    P8 difference across overlap years exceeds P8_DIFF_THRESHOLD.

    The mean is taken per firm_id across all rows in the check file (each row
    is one firm x fiscal_year observation in the FY2020-FY2023 overlap).

    Args:
        p8_path: Path to 07_p8_reconstruction_check.csv.

    Returns:
        Set of firm_id strings that are excluded.
    """
    print("\n" + "=" * 65)
    print("STEP 1 -- Build exclusion list")
    print("=" * 65)

    df = pd.read_csv(p8_path)
    print(f"  P8 check file: {len(df):,} firm-year rows, "
          f"{df['firm_id'].nunique():,} unique firms")

    # Mean abs_diff_pp per firm
    firm_stats = (
        df.groupby(["firm_id", "sector"])["abs_diff_pp"]
        .mean()
        .reset_index()
        .rename(columns={"abs_diff_pp": "mean_p8_diff_pp"})
    )

    flagged = firm_stats[firm_stats["mean_p8_diff_pp"] > P8_DIFF_THRESHOLD].copy()
    flagged["exclusion_reason"] = "restructuring_MA"
    flagged = flagged.sort_values("mean_p8_diff_pp", ascending=False)

    print(f"\n  Threshold : {P8_DIFF_THRESHOLD} pp")
    print(f"  Firms in check file         : {len(firm_stats):,}")
    print(f"  Firms flagged (excluded)    : {len(flagged):,}")
    print(f"  Firms retained              : {len(firm_stats) - len(flagged):,}")

    if len(flagged):
        print(f"\n  Top 10 excluded firms (highest mean P8 diff):")
        print(f"  {'firm_id':<55s}  {'mean_pp':>8s}")
        print(f"  {'-'*55}  {'-'*8}")
        for _, row in flagged.head(10).iterrows():
            fid = str(row["firm_id"])[:55]
            print(f"  {fid:<55s}  {row['mean_p8_diff_pp']:>8.2f}")

    flagged.to_csv(OUTPUT_EXCL, index=False, encoding="utf-8-sig")
    print(f"\n  Saved -> {OUTPUT_EXCL}")

    return set(flagged["firm_id"])


# ---------------------------------------------------------------------------
# Step 2 -- Old-file contribution: FY2015-FY2023
# ---------------------------------------------------------------------------

def build_old_contribution(old_path: str, excl_ids: set) -> pd.DataFrame:
    """
    Load the old-file model-ready panel, remove excluded firms, drop FY2014,
    and tag with source_file = "old".

    Args:
        old_path: Path to 05_model_ready_old.csv.
        excl_ids: Set of firm_id strings to drop.

    Returns:
        Filtered DataFrame for FY2015-FY2023.
    """
    print("\n" + "=" * 65)
    print("STEP 2 -- Old-file contribution (FY2015-FY2023)")
    print("=" * 65)

    df = pd.read_csv(old_path)
    print(f"  Loaded: {len(df):,} rows, {df['firm_id'].nunique():,} firms")

    n_before = len(df)
    df = df[~df["firm_id"].isin(excl_ids)].copy()
    print(f"  After dropping excluded firms : {len(df):,} rows "
          f"({n_before - len(df):,} removed, "
          f"{df['firm_id'].nunique():,} firms remaining)")

    df = df[df["fiscal_year"] != 2014].copy()
    print(f"  After dropping FY2014 (base)  : {len(df):,} rows")

    df["source_file"] = "old"
    return df


# ---------------------------------------------------------------------------
# Step 3 -- FY25-file extension: FY2024 and FY2025 only
# ---------------------------------------------------------------------------

def build_fy25_extension(fy25_path: str, excl_ids: set,
                         old_cols: list) -> pd.DataFrame:
    """
    Load the FY25 model-ready panel, retain only FY2024 and FY2025,
    remove excluded firms, and align columns to the old file schema.

    Columns present in the FY25 file but absent from the old file are dropped,
    EXCEPT 'fye' which is retained as it carries non-June FYE flags.
    Columns present in the old file but missing from the FY25 rows are
    added as NaN.

    Args:
        fy25_path: Path to 06_model_ready_fy25.csv.
        excl_ids:  Set of firm_id strings to drop.
        old_cols:  Column list from the old-file contribution.

    Returns:
        Filtered and column-aligned DataFrame for FY2024-FY2025.
    """
    print("\n" + "=" * 65)
    print("STEP 3 -- FY25 extension (FY2024-FY2025)")
    print("=" * 65)

    df = pd.read_csv(fy25_path)
    print(f"  Loaded: {len(df):,} rows, {df['firm_id'].nunique():,} firms")

    n_before = len(df)
    df = df[~df["firm_id"].isin(excl_ids)].copy()
    print(f"  After dropping excluded firms : {len(df):,} rows "
          f"({n_before - len(df):,} removed, "
          f"{df['firm_id'].nunique():,} firms remaining)")

    df = df[df["fiscal_year"].isin([2024, 2025])].copy()
    print(f"  After keeping FY2024-FY2025  : {len(df):,} rows, "
          f"{df['firm_id'].nunique():,} firms")

    df["source_file"] = "fy25"

    # --- Column alignment ---
    # Determine which columns to keep:
    #   - All columns already in old file  (fill NaN if missing here)
    #   - Plus 'fye' if present in FY25 but not old file
    keep_extra = []
    if "fye" in df.columns and "fye" not in old_cols:
        keep_extra.append("fye")

    fy25_only = [c for c in df.columns
                 if c not in old_cols and c not in keep_extra]
    if fy25_only:
        print(f"\n  Dropping FY25-only columns ({len(fy25_only)}): "
              + ", ".join(fy25_only[:8])
              + (" ..." if len(fy25_only) > 8 else ""))
    df = df.drop(columns=fy25_only, errors="ignore")

    # Add any old-file columns missing from FY25
    missing_from_fy25 = [c for c in old_cols if c not in df.columns]
    if missing_from_fy25:
        print(f"  Adding NaN placeholders for {len(missing_from_fy25)} "
              f"old-file-only columns: "
              + ", ".join(missing_from_fy25[:8])
              + (" ..." if len(missing_from_fy25) > 8 else ""))
    for col in missing_from_fy25:
        df[col] = np.nan

    return df


# ---------------------------------------------------------------------------
# Step 4 -- Stack and recompute within-firm CoC lags
# ---------------------------------------------------------------------------

def stack_and_recompute_lags(df_old: pd.DataFrame,
                             df_ext: pd.DataFrame) -> pd.DataFrame:
    """
    Vertically concatenate the two contributions, sort by firm_id and
    fiscal_year, then recompute CoC_Proxy_L1 and CoC_Proxy_L2 across
    the full merged time series.

    This ensures that for firms appearing in both files (FY2015-FY2023 from
    old, FY2024-FY2025 from FY25), the lag in FY2024 correctly references
    the FY2023 value extracted from the old file.

    Args:
        df_old: Old-file contribution from build_old_contribution().
        df_ext: FY25 extension from build_fy25_extension().

    Returns:
        Stacked, sorted DataFrame with recomputed lag columns.
    """
    print("\n" + "=" * 65)
    print("STEP 4 -- Stack and recompute CoC lags")
    print("=" * 65)

    # Align column order before concat
    all_cols = list(df_old.columns)
    for c in df_ext.columns:
        if c not in all_cols:
            all_cols.append(c)

    df = pd.concat(
        [df_old.reindex(columns=all_cols),
         df_ext.reindex(columns=all_cols)],
        ignore_index=True
    )
    df = df.sort_values(["firm_id", "fiscal_year"]).reset_index(drop=True)

    print(f"  Stacked panel : {len(df):,} rows, "
          f"{df['firm_id'].nunique():,} unique firms")
    print(f"  Fiscal years  : {sorted(df['fiscal_year'].unique())}")

    # Recompute lags over merged time series
    grp = df.groupby("firm_id", sort=False)
    df["CoC_Proxy_L1"] = grp["CoC_Proxy"].shift(1)
    df["CoC_Proxy_L2"] = grp["CoC_Proxy"].shift(2)

    # Report how many FY2024 rows now have a valid L1 from the old file
    fy2024 = df[df["fiscal_year"] == 2024]
    n_l1_ok = fy2024["CoC_Proxy_L1"].notna().sum()
    n_l2_ok = fy2024["CoC_Proxy_L2"].notna().sum()
    print(f"\n  FY2024 rows with CoC_Proxy_L1 from FY2023 (old file): "
          f"{n_l1_ok:,} / {len(fy2024):,}")
    print(f"  FY2024 rows with CoC_Proxy_L2 from FY2022 (old file): "
          f"{n_l2_ok:,} / {len(fy2024):,}")

    return df


# ---------------------------------------------------------------------------
# Step 5 -- Recompute sample flags
# ---------------------------------------------------------------------------

def recompute_sample_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recompute boolean sample-membership flags on the merged panel.

    in_model1_sample : Inv_Rate and CoC_Proxy both non-null
    in_model3_sample : in_model1_sample AND CoC_Proxy_L2 non-null
    balanced_subsample:
      - For old-source rows: firm must appear in all of FY2015-FY2023 (9 yrs)
      - For fy25-source rows: firm must appear in FY2024 and FY2025 (2 yrs)
      - A firm that has BOTH contributions is balanced if it meets BOTH criteria

    The remaining flags (zero_interest, negative_equity, non_june_fye,
    robustness_excl) are re-derived from raw columns where available; if a
    column was present in the loaded data it is preserved as-is.

    Args:
        df: Stacked DataFrame from stack_and_recompute_lags().

    Returns:
        DataFrame with recomputed flag columns.
    """
    print("\n" + "=" * 65)
    print("STEP 5 -- Recompute sample flags")
    print("=" * 65)

    df = df.copy()

    # -- Model sample flags --------------------------------------------------
    df["in_model1_sample"] = (
        df["Inv_Rate"].notna() & df["CoC_Proxy"].notna()
    ).astype(int)

    df["in_model3_sample"] = (
        (df["in_model1_sample"] == 1) & df["CoC_Proxy_L2"].notna()
    ).astype(int)

    # -- Balanced subsample --------------------------------------------------
    # Expected year counts per source
    old_years  = set(range(2015, 2024))   # 9 years: 2015-2023
    fy25_years = {2024, 2025}             # 2 years

    old_firms_balanced = set(
        df[df["source_file"] == "old"]
        .groupby("firm_id")["fiscal_year"]
        .apply(lambda yrs: old_years.issubset(set(yrs)))
        .pipe(lambda s: s[s].index)
    )
    fy25_firms_balanced = set(
        df[df["source_file"] == "fy25"]
        .groupby("firm_id")["fiscal_year"]
        .apply(lambda yrs: fy25_years.issubset(set(yrs)))
        .pipe(lambda s: s[s].index)
    )

    # A row is in balanced_subsample if:
    #   source == "old"  AND firm is in old_firms_balanced, OR
    #   source == "fy25" AND firm is in fy25_firms_balanced
    df["balanced_subsample"] = (
        ((df["source_file"] == "old")  & df["firm_id"].isin(old_firms_balanced))  |
        ((df["source_file"] == "fy25") & df["firm_id"].isin(fy25_firms_balanced))
    ).astype(int)

    # -- Other flags ---------------------------------------------------------
    if "InterestExpense" in df.columns:
        df["zero_interest"] = (df["InterestExpense"] == 0).astype(int)

    if "ShareholdersEquity_C" in df.columns:
        df["negative_equity"] = (df["ShareholdersEquity_C"] < 0).astype(int)

    if "fye" in df.columns:
        df["non_june_fye"] = (
            df["fye"].notna() &
            (df["fye"].astype(str).str.strip() != "") &
            (df["fye"].astype(str).str.strip() != "Jun")
        ).astype(int)
    else:
        df["non_june_fye"] = 0

    if "sector" in df.columns:
        df["robustness_excl"] = df["sector"].isin(ROBUSTNESS_EXCL_SECTORS).astype(int)

    # -- Report --------------------------------------------------------------
    print(f"  in_model1_sample   : {df['in_model1_sample'].sum():,} obs")
    print(f"  in_model3_sample   : {df['in_model3_sample'].sum():,} obs")
    print(f"  balanced_subsample : {df['balanced_subsample'].sum():,} obs  "
          f"({len(old_firms_balanced):,} old-balanced firms, "
          f"{len(fy25_firms_balanced):,} fy25-balanced firms)")

    return df


# ---------------------------------------------------------------------------
# Step 6 -- post2023 indicator
# ---------------------------------------------------------------------------

def add_post2023(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add post2023 binary column: 1 for fiscal_year >= 2024, 0 otherwise.
    Used as a source-change control variable in robustness regressions.

    Args:
        df: Panel DataFrame.

    Returns:
        DataFrame with post2023 column.
    """
    df = df.copy()
    df["post2023"] = (df["fiscal_year"] >= 2024).astype(int)
    print(f"\n  post2023 == 1 : {df['post2023'].sum():,} obs (FY2024-FY2025)")
    print(f"  post2023 == 0 : {(df['post2023'] == 0).sum():,} obs (FY2015-FY2023)")
    return df


# ---------------------------------------------------------------------------
# Step 7 -- Output and report
# ---------------------------------------------------------------------------

def save_and_report(df: pd.DataFrame, output_path: str) -> None:
    """
    Save merged panel to CSV and print a structured summary report.

    Args:
        df:          Merged, flag-annotated panel DataFrame.
        output_path: Destination CSV path.
    """
    print("\n" + "=" * 65)
    print("STEP 7 -- Output and summary report")
    print("=" * 65)

    df = df.sort_values(["firm_id", "fiscal_year"]).reset_index(drop=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  Saved -> {output_path}")

    n_firms = df["firm_id"].nunique()
    n_obs   = len(df)

    print(f"\n{'=' * 65}")
    print(f"  MERGED PANEL SUMMARY REPORT")
    print(f"{'=' * 65}")

    print(f"\n  Total observations : {n_obs:,}")
    print(f"  Unique firms       : {n_firms:,}")
    print(f"  Fiscal year range  : {df['fiscal_year'].min()} - "
          f"{df['fiscal_year'].max()}")

    # -- Rows by fiscal year -------------------------------------------------
    print(f"\n  Rows by fiscal year:")
    yr_counts = df.groupby("fiscal_year").size()
    for yr, cnt in yr_counts.items():
        bar = "#" * (cnt // 30)
        print(f"    {yr}  {cnt:>5,}  {bar}")

    # -- Rows by source_file -------------------------------------------------
    print(f"\n  Rows by source_file:")
    for src, cnt in df["source_file"].value_counts().items():
        pct = 100 * cnt / n_obs
        print(f"    {src:<6s}  {cnt:>5,}  ({pct:.1f}%)")

    # -- Sample flags --------------------------------------------------------
    print(f"\n  Sample flags:")
    flags = [
        ("in_model1_sample",   "Models 1 & 2 (Inv_Rate and CoC_Proxy non-null)"),
        ("in_model3_sample",   "Model 3 (CoC_Proxy_L2 non-null)"),
        ("balanced_subsample", "Balanced within source"),
        ("zero_interest",      "Zero-interest firm-years"),
        ("negative_equity",    "Negative-equity firm-years"),
        ("non_june_fye",       "Non-June FYE firm-years"),
        ("robustness_excl",    "Fuel & Energy / Cement (robustness exclusion)"),
        ("post2023",           "FY2024-FY2025 (source-change control)"),
    ]
    for col, desc in flags:
        if col in df.columns:
            n = int(df[col].sum())
            print(f"    {col:<22s}: {n:>5,}  -- {desc}")

    # -- Stitched firms (present in both halves) ------------------------------
    old_firm_set  = set(df.loc[df["source_file"] == "old",  "firm_id"])
    fy25_firm_set = set(df.loc[df["source_file"] == "fy25", "firm_id"])
    stitched      = old_firm_set & fy25_firm_set
    print(f"\n  Firms with observations from BOTH sources (stitched): "
          f"{len(stitched):,}")
    print(f"    Old-only firms (FY2015-FY2023 only)  : "
          f"{len(old_firm_set - fy25_firm_set):,}")
    print(f"    FY25-only firms (FY2024-FY2025 only) : "
          f"{len(fy25_firm_set - old_firm_set):,}")

    # -- Placeholder reminder ------------------------------------------------
    for col in ["r_SBP", "CPI_inflation"]:
        if col in df.columns:
            n_miss = df[col].isna().sum()
            print(f"\n  *** REMINDER: '{col}' is still empty "
                  f"({n_miss:,} NaN rows). Fill manually before regression.")

    print(f"\n{'=' * 65}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    """Execute all 7 steps to build the merged panel."""
    print("=" * 65)
    print("Script 05 -- Build stitched merged panel (FY2015-FY2025)")
    print("Reference : Gormsen & Huber (2024, 2025)")
    print("=" * 65)

    # Step 1
    excl_ids = build_exclusion_list(INPUT_P8_CHECK)

    # Step 2
    df_old = build_old_contribution(INPUT_OLD, excl_ids)

    # Step 3
    df_ext = build_fy25_extension(INPUT_FY25, excl_ids,
                                  old_cols=list(df_old.columns))

    # Step 4
    df = stack_and_recompute_lags(df_old, df_ext)

    # Step 5
    df = recompute_sample_flags(df)

    # Step 6
    df = add_post2023(df)

    # Step 7
    save_and_report(df, OUTPUT_MERGED)

    return df


if __name__ == "__main__":
    run()
