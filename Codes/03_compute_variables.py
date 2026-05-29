"""
03_compute_variables.py
========================
Construct all research variables from the raw firm-level extracted panels.

INPUT
-----
  Extracted Data/01_raw_firm_panel_old.csv   (from script 01)
  Extracted Data/02_raw_firm_panel_fy25.csv  (from script 02)

OUTPUT
------
  Extracted Data/03_firm_panel_old_computed.csv
  Extracted Data/04_firm_panel_fy25_computed.csv

VARIABLE CONSTRUCTION
---------------------
Inv_Rate       = (OFA_cost_t - OFA_cost_{t-1}) / TotalAssets_{t-1}
CoC_Proxy      = InterestExpense_t / (D_NCL_t + E_CL_t)
P8_ROIC        = EBIT_t / avg(CapEmployed_t, CapEmployed_{t-1})   [OLD: reconstructed]
                 P8_precomp / 100                                  [FY25: direct]
S1_Leverage    = TotalDebt / ShareholdersEquity_C                  [OLD: reconstructed]
                 S1_precomp                                        [FY25: direct]
Size_ln        = ln(TotalAssets_t)
Cashflow       = Retention_t / TotalAssets_t
DepRate        = Depreciation_t / TotalAssets_t
SalesGrowth    = (Sales_t - Sales_{t-1}) / Sales_{t-1}
CoC_Proxy_L1/L2: within-firm lags of CoC_Proxy
r_SBP, CPI_inflation: external placeholders (fill manually)

KPI ROUNDING NOTE (old file only)
----------------------------------
P8 and S1 KPIs in the 2014-23 file are stored as rounded integers at firm
level.  Using them directly as dependent variables or controls would inject
measurement error of up to +/-0.5 pp per observation.  This script therefore
reconstructs P8 and S1 from full-precision raw balance sheet items.
For the FY25 file, KPIs are at full floating-point precision and are used as-is.

Reference: FirmLevel_DataStrategy.docx; Gormsen & Huber (2024, 2025).
"""

import os
import sys
import numpy as np
import pandas as pd

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
PROJECT_DIR   = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

INPUT_OLD  = os.path.join(EXTRACTED_DIR, "01_raw_firm_panel_old.csv")
INPUT_FY25 = os.path.join(EXTRACTED_DIR, "02_raw_firm_panel_fy25.csv")
OUTPUT_OLD  = os.path.join(EXTRACTED_DIR, "03_firm_panel_old_computed.csv")
OUTPUT_FY25 = os.path.join(EXTRACTED_DIR, "04_firm_panel_fy25_computed.csv")

WINS_LOWER = 0.01
WINS_UPPER = 0.99

ROBUSTNESS_EXCL_SECTORS = {"Fuel and Energy Sector", "Fuel and Energy", "Cement"}


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_variables(df: pd.DataFrame,
                      label: str,
                      reconstruct_p8: bool = True) -> pd.DataFrame:
    """
    Add all derived research variables to a raw firm-year DataFrame.

    Lag operations are grouped by firm_id so they never cross firm boundaries.

    Args:
        df:             Raw firm-year DataFrame from script 01 or 02.
        label:          Short panel label for log output.
        reconstruct_p8: True  -> reconstruct P8/S1 from raw items (old file).
                        False -> use P8_precomp/S1_precomp directly (FY25 file).

    Returns:
        DataFrame with all raw columns plus computed variable columns.
    """
    print(f"\n--- Computing variables: {label} ---")
    df  = df.copy().sort_values(["firm_id", "fiscal_year"]).reset_index(drop=True)
    grp = df.groupby("firm_id", sort=False)

    # -- 1. Investment Rate -----------------------------------------------
    df["OFA_cost_L1"]    = grp["OFA_cost"].shift(1)
    df["TotalAssets_L1"] = grp["TotalAssets"].shift(1)
    df["Inv_Rate_raw"]   = (df["OFA_cost"] - df["OFA_cost_L1"]) / df["TotalAssets_L1"]
    print(f"  Inv_Rate:   {df['Inv_Rate_raw'].notna().sum():,} non-null obs")

    # -- 2. CoC Proxy -------------------------------------------------------
    df["TotalDebt"]     = df["D_NCL"] + df["E_CL"]
    df["CoC_Proxy_raw"] = np.where(
        df["TotalDebt"] > 0,
        df["InterestExpense"] / df["TotalDebt"],
        np.nan,
    )
    n_zero = (df["InterestExpense"] == 0).sum()
    print(f"  CoC_Proxy:  {df['CoC_Proxy_raw'].notna().sum():,} non-null obs  "
          f"({n_zero:,} zero-interest firm-years)")

    # -- 3. P8 ROIC ---------------------------------------------------------
    if reconstruct_p8:
        # Old file: KPI is integer-rounded; reconstruct from raw items
        df["CapEmployed_L1"] = grp["CapEmployed"].shift(1)
        df["CapEmpl_avg"]    = (df["CapEmployed"] + df["CapEmployed_L1"]) / 2
        df["P8_ROIC"] = np.where(
            df["CapEmpl_avg"].notna() & (df["CapEmpl_avg"] != 0),
            df["EBIT"] / df["CapEmpl_avg"],
            np.nan,
        )
        print(f"  P8_ROIC (reconstructed): {df['P8_ROIC'].notna().sum():,} non-null obs")
    else:
        # FY25 file: full precision; convert % to proportion
        df["P8_ROIC"] = df["P8_precomp"] / 100.0
        print(f"  P8_ROIC (KPI direct):    {df['P8_ROIC'].notna().sum():,} non-null obs")

    # -- 4. S1 Leverage -----------------------------------------------------
    if reconstruct_p8:
        # Old file: reconstruct (D+E)/C from raw items
        df["S1_Leverage"] = np.where(
            df["ShareholdersEquity_C"].notna() & (df["ShareholdersEquity_C"] != 0),
            df["TotalDebt"] / df["ShareholdersEquity_C"],
            np.nan,
        )
    else:
        df["S1_Leverage"] = df["S1_precomp"]

    n_neg_eq = (df["ShareholdersEquity_C"] < 0).sum()
    if n_neg_eq:
        print(f"  INFO: {n_neg_eq:,} obs with negative equity (valid; flagged)")

    # -- 5. Size (log total assets) -----------------------------------------
    df["Size_ln"] = np.log(df["TotalAssets"].clip(lower=1))

    # -- 6. Cashflow = Retention / TotalAssets --------------------------------
    # Guard against TotalAssets == 0 (e.g. Shakarganj Food Ltd. FY2014)
    df["Cashflow"] = np.where(
        df["TotalAssets"].notna() & (df["TotalAssets"] > 0),
        df["Retention"] / df["TotalAssets"],
        np.nan,
    )

    # -- 7. Depreciation rate = Depreciation / TotalAssets -------------------
    # Same zero-guard as Cashflow
    df["DepRate"] = np.where(
        df["TotalAssets"].notna() & (df["TotalAssets"] > 0),
        df["Depreciation"] / df["TotalAssets"],
        np.nan,
    )

    # -- 8. Sales Growth -------------------------------------------------------
    df["Sales_L1"]    = grp["Sales"].shift(1)
    df["SalesGrowth"] = np.where(
        df["Sales_L1"].notna() & (df["Sales_L1"] > 0),
        (df["Sales"] - df["Sales_L1"]) / df["Sales_L1"],
        np.nan,
    )

    # -- 9. CoC lags (within-firm) -------------------------------------------
    df["CoC_Proxy_L1"] = grp["CoC_Proxy_raw"].shift(1)
    df["CoC_Proxy_L2"] = grp["CoC_Proxy_raw"].shift(2)

    # -- 10. External placeholders -------------------------------------------
    if "r_SBP" not in df.columns:
        df["r_SBP"]        = np.nan   # FILL: SBP policy rate (Jul-Jun annual avg)
    if "CPI_inflation" not in df.columns:
        df["CPI_inflation"] = np.nan  # FILL: annual CPI inflation

    df["r_SBP_L1"]    = grp["r_SBP"].shift(1)
    df["delta_r_SBP"] = df["r_SBP"] - df["r_SBP_L1"]
    df["Interaction"]  = df["CoC_Proxy_raw"] * df["delta_r_SBP"]
    df["Real_CoC"]     = df["CoC_Proxy_raw"] - df["CPI_inflation"]

    # -- 11. Observation flags ------------------------------------------------
    df["zero_interest"]   = (df["InterestExpense"] == 0)
    df["negative_equity"] = (df["ShareholdersEquity_C"] < 0)
    df["robustness_excl"] = df["sector"].isin(ROBUSTNESS_EXCL_SECTORS)

    if "fye" in df.columns:
        df["non_june_fye"] = (
            df["fye"].notna() & (df["fye"] != "") & (df["fye"] != "Jun")
        )
    else:
        df["non_june_fye"] = False

    return df


# ---------------------------------------------------------------------------
# Sample flags
# ---------------------------------------------------------------------------

def add_sample_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add boolean columns identifying which rows belong to which estimation
    sample, enabling one-line filtering in downstream regression scripts.

    Args:
        df: Computed panel DataFrame.

    Returns:
        DataFrame with sample flag columns.
    """
    df = df.copy()
    df["in_model1_sample"] = df["Inv_Rate_raw"].notna()
    df["in_model3_sample"] = df["CoC_Proxy_L2"].notna()

    # Balanced subsample: firms present in EVERY fiscal year of the panel
    max_yrs        = df["fiscal_year"].nunique()
    yr_per_firm    = df.groupby("firm_id")["fiscal_year"].nunique()
    balanced_firms = set(yr_per_firm[yr_per_firm == max_yrs].index)
    df["balanced_subsample"] = df["firm_id"].isin(balanced_firms)

    print(f"\n  Sample flags:")
    print(f"    in_model1_sample : {df['in_model1_sample'].sum():,} obs")
    print(f"    in_model3_sample : {df['in_model3_sample'].sum():,} obs")
    print(f"    balanced_subsample: {df['balanced_subsample'].sum():,} obs  "
          f"({len(balanced_firms):,} firms x {max_yrs} years)")
    return df


# ---------------------------------------------------------------------------
# Winsorisation
# ---------------------------------------------------------------------------

def winsorize_panel(df: pd.DataFrame, cols: list,
                    lower: float = WINS_LOWER,
                    upper: float = WINS_UPPER) -> pd.DataFrame:
    """
    Winsorise specified columns at the given percentile bounds over the
    full panel.  Pre-winsorised values saved as <col>_raw.

    Args:
        df:    Panel DataFrame.
        cols:  Columns to winsorise.
        lower: Lower percentile.
        upper: Upper percentile.
    """
    df = df.copy()
    print("\n  Winsorising at 1st / 99th percentile:")
    for col in cols:
        if col not in df.columns:
            print(f"    WARNING: '{col}' not found -- skipped")
            continue
        raw = col + "_raw"
        if raw not in df.columns:
            df[raw] = df[col].copy()
        p_lo = df[col].quantile(lower)
        p_hi = df[col].quantile(upper)
        n_lo = (df[col] < p_lo).sum()
        n_hi = (df[col] > p_hi).sum()
        df[col] = df[col].clip(lower=p_lo, upper=p_hi)
        print(f"    {col:<20s}: [{p_lo:+.4f}, {p_hi:+.4f}]  "
              f"({n_lo} low, {n_hi} high clipped)")
    return df


# ---------------------------------------------------------------------------
# Main processing function
# ---------------------------------------------------------------------------

def process_panel(input_path: str, output_path: str,
                  label: str, reconstruct_p8: bool) -> pd.DataFrame:
    """
    Load raw CSV, compute variables, winsorise, add sample flags, save.
    """
    print(f"\n{'=' * 65}\nProcessing {label}\n{'=' * 65}")

    df = pd.read_csv(input_path)
    print(f"Loaded {len(df):,} rows")

    df = compute_variables(df, label, reconstruct_p8=reconstruct_p8)
    df = winsorize_panel(df, ["Inv_Rate_raw", "CoC_Proxy_raw",
                              "P8_ROIC", "S1_Leverage", "SalesGrowth",
                              "Cashflow", "DepRate"])

    # Final analysis columns (use winsorised versions)
    df["Inv_Rate"]  = df["Inv_Rate_raw"]
    df["CoC_Proxy"] = df["CoC_Proxy_raw"]
    df["CoC_Proxy_L1"] = df.groupby("firm_id")["CoC_Proxy"].shift(1)
    df["CoC_Proxy_L2"] = df.groupby("firm_id")["CoC_Proxy"].shift(2)

    df = add_sample_flags(df)

    core = ["Inv_Rate_raw", "CoC_Proxy_raw", "P8_ROIC",
            "S1_Leverage", "Cashflow", "SalesGrowth", "Size_ln"]
    avail = [c for c in core if c in df.columns]
    print(f"\n--- Descriptive summary ---")
    print(df[avail].describe().round(4).to_string())

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved -> {output_path}")
    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> tuple:
    """
    Compute variables for both panels.

    Returns:
        Tuple of (df_old, df_fy25).
    """
    print("=" * 65)
    print("Script 03 -- Compute firm-level research variables")
    print("=" * 65)

    df_old = process_panel(
        INPUT_OLD, OUTPUT_OLD,
        label="OLD file (2014-23)", reconstruct_p8=True,
    )
    df_fy25 = process_panel(
        INPUT_FY25, OUTPUT_FY25,
        label="FY25 file", reconstruct_p8=False,
    )
    return df_old, df_fy25


if __name__ == "__main__":
    run()
