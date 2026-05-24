"""
03_compute_variables.py
========================
Construct all research variables from the raw extracted sector panels.

INPUT
-----
  Extracted Data/01_raw_sector_panel_old.csv   (from script 01)
  Extracted Data/02_raw_sector_panel_fy25.csv  (from script 02)

OUTPUT
------
  Extracted Data/03_panel_old_computed.csv
    Main estimation panel: 14 sectors — FY2014€“FY2023
    Usable rows for estimation: 126 (FY2015€“FY2023, after one-lag)
    Usable rows for Model 3:    98  (FY2017€“FY2023, after two-lags)

  Extracted Data/04_panel_fy25_computed.csv
    Validation panel: 14 sectors — FY2020€“FY2025
    Usable rows: 70 (FY2021€“FY2025, after one-lag)

VARIABLE CONSTRUCTION RULES
-----------------------------
Investment Rate (Inv_Rate)
  Inv_Rate_t = (OFA_cost_t - OFA_cost_{t-1}) / TotalAssets_{t-1}
  €¢ Numerator uses operating fixed assets AT COST (not net of depreciation),
    which captures actual capital spending decisions.
  €¢ Denominator is lagged total assets, making the rate interpretable as a
    percentage of the prior-year asset base.
  €¢ FY2014 is consumed as the base year †’ first usable observation is FY2015.
  €¢ Negative values are valid (net asset disposals) and must not be set to zero.

Cost-of-Capital Proxy (CoC_Proxy)
  CoC_Proxy_t = InterestExpense_t / (D_NCL_t + E_CL_t)
  €¢ D + E = total external liabilities.
  €¢ Uses the interest expense SUB-ITEM within Financial Expenses (F.7(i)),
    not the aggregate F.7 line which includes non-interest financing costs.
  €¢ Expressed as a proportion; multiply by 100 for percentage-point reporting.
  €¢ Denominator is contemporaneous (same-year), following the standard
    effective interest rate convention.

ROIC €” pre-computed KPI (P8_precomp)
  Taken directly from the I. Key Performance Indicators section.
  P8 = EBIT / average(CapEmployed_t, CapEmployed_{t-1})
  €¢ This is the only ROIC measure that avoids mechanical correlation with
    CoC_Proxy, because it uses EBIT (pre-interest) as numerator.
  €¢ In the old file, P8 at the sector-aggregate level is stored at full
    floating-point precision (unlike firm-level P8 which is rounded).

Control Variables
  Size_ln     = ln(TotalAssets_t)                         [reduces scale effects]
  Leverage_S1 = (D+E)/C, taken directly from S1 KPI       [pre-computed, reliable]
  Cashflow    = Retention_t / TotalAssets_t                [internal financing rate]
  DepRate     = Depreciation_t / TotalAssets_t             [capital intensity proxy]
  SalesGrowth = (Sales_t - Sales_{t-1}) / Sales_{t-1}     [demand-side control]

Model 3 Additional Variables (lags and differences)
  CoC_Proxy_L1 = CoC_Proxy_{t-1}   (one-year lag within sector)
  CoC_Proxy_L2 = CoC_Proxy_{t-2}   (two-year lag within sector)
  r_SBP        = PLACEHOLDER €” annual average SBP policy rate
                 (external source; to be filled manually after extraction)
  CPI_inflation = PLACEHOLDER €” annual CPI inflation rate
                 (external source; PBS or IMF IFS)
  delta_r_SBP  = r_SBP_t - r_SBP_{t-1}  (formula column; blank until r_SBP filled)
  Interaction  = CoC_Proxy_t — delta_r_SBP_t  (blank until r_SBP filled)
  Real_CoC     = CoC_Proxy_t - CPI_inflation_t (optional; blank until CPI filled)

Winsorisation
  Inv_Rate and CoC_Proxy are winsorised at the 1st and 99th percentiles of
  the full panel distribution (not sector-by-sector).
  The pre-winsorised values are retained as _raw columns for diagnostics.

Reference: Gormsen & Huber (2024, 2025); DataStrategy_ExtractionGuide.docx.
"""

import os
import sys
import numpy as np
import pandas as pd

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from utils import safe_div

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
PROJECT_DIR = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

INPUT_OLD  = os.path.join(EXTRACTED_DIR, "01_raw_sector_panel_old.csv")
INPUT_FY25 = os.path.join(EXTRACTED_DIR, "02_raw_sector_panel_fy25.csv")

OUTPUT_OLD  = os.path.join(EXTRACTED_DIR, "03_panel_old_computed.csv")
OUTPUT_FY25 = os.path.join(EXTRACTED_DIR, "04_panel_fy25_computed.csv")

# Winsorisation bounds (percentiles applied to the full panel distribution)
WINS_LOWER = 0.01
WINS_UPPER = 0.99

# Sectors excluded in robustness specifications (see Section 5.3 of guide)
ROBUSTNESS_EXCLUDE = {"710", "729"}   # Fuel and Energy, Cement


# ---------------------------------------------------------------------------
# Core variable computation
# ---------------------------------------------------------------------------

def compute_variables(df: pd.DataFrame, panel_label: str) -> pd.DataFrame:
    """
    Add all derived research variables to a raw extraction DataFrame.

    The function modifies a copy of the input so the original raw data is
    preserved.  All computations are done sector-by-sector using a GroupBy
    to ensure lags never cross sector boundaries.

    Args:
        df:           Raw panel DataFrame from script 01 or 02.
        panel_label:  Short label for log messages (e.g. 'OLD' or 'FY25').

    Returns:
        DataFrame with all raw columns plus computed variable columns.
    """
    print(f"\n--- Computing variables for {panel_label} panel ---")
    df = df.copy()

    # Ensure rows are sorted by sector then fiscal year before lag operations
    df = df.sort_values(["sector_code", "fiscal_year"]).reset_index(drop=True)

    # -----------------------------------------------------------------------
    # 1. Investment Rate
    #    Inv_Rate_t = (OFA_cost_t - OFA_cost_{t-1}) / TotalAssets_{t-1}
    # -----------------------------------------------------------------------
    df["OFA_cost_L1"]     = df.groupby("sector_code")["OFA_cost"].shift(1)
    df["TotalAssets_L1"]  = df.groupby("sector_code")["TotalAssets"].shift(1)

    df["Inv_Rate_raw"] = (df["OFA_cost"] - df["OFA_cost_L1"]).div(
        df["TotalAssets_L1"]
    )

    print(f"  Inv_Rate: {df['Inv_Rate_raw'].notna().sum()} non-null observations")

    # -----------------------------------------------------------------------
    # 2. Cost-of-Capital Proxy
    #    CoC_Proxy_t = InterestExpense_t / (D_NCL_t + E_CL_t)
    # -----------------------------------------------------------------------
    df["TotalDebt"] = df["D_NCL"] + df["E_CL"]
    df["CoC_Proxy_raw"] = df["InterestExpense"] / df["TotalDebt"]

    # Flag any implausible values (negative interest expense or negative debt)
    n_neg = (df["CoC_Proxy_raw"] < 0).sum()
    if n_neg > 0:
        print(f"  WARNING: {n_neg} negative CoC_Proxy values €” check input data")

    print(f"  CoC_Proxy: {df['CoC_Proxy_raw'].notna().sum()} non-null observations")

    # -----------------------------------------------------------------------
    # 3. Size (natural log of total assets)
    # -----------------------------------------------------------------------
    df["Size_ln"] = np.log(df["TotalAssets"].clip(lower=1))
    # .clip(lower=1) prevents log(0) errors; sector aggregates should never
    # have zero total assets, so this guard should never activate.

    # -----------------------------------------------------------------------
    # 4. Leverage (S1 from KPI section €” used directly, not reconstructed)
    #    S1 = (D+E) / C  where C = Shareholders' Equity
    #    Can be negative when a sector has negative equity (valid, flag it)
    # -----------------------------------------------------------------------
    df["Leverage_S1"] = df["S1_precomp"]

    n_neg_lev = (df["Leverage_S1"] < 0).sum()
    if n_neg_lev > 0:
        print(f"  INFO: {n_neg_lev} negative Leverage_S1 values "
              f"(negative equity possible at sector level)")

    # -----------------------------------------------------------------------
    # 5. Cashflow rate
    #    Cashflow_t = Retention_t / TotalAssets_t
    #    Retention can be negative when dividends + bonus shares > profit after tax
    # -----------------------------------------------------------------------
    df["Cashflow"] = df["Retention"] / df["TotalAssets"]

    n_neg_cf = (df["Cashflow"] < 0).sum()
    if n_neg_cf > 0:
        print(f"  INFO: {n_neg_cf} negative Cashflow values "
              f"(dividend payout exceeded earnings €” economically valid)")

    # -----------------------------------------------------------------------
    # 6. Depreciation rate (optional capital-intensity control)
    # -----------------------------------------------------------------------
    df["DepRate"] = df["Depreciation"] / df["TotalAssets"]

    # -----------------------------------------------------------------------
    # 7. Sales growth
    #    SalesGrowth_t = (Sales_t - Sales_{t-1}) / Sales_{t-1}
    # -----------------------------------------------------------------------
    df["Sales_L1"]     = df.groupby("sector_code")["Sales"].shift(1)
    df["SalesGrowth"]  = (df["Sales"] - df["Sales_L1"]) / df["Sales_L1"]

    # -----------------------------------------------------------------------
    # 8. ROIC from pre-computed KPI (P8)
    #    Stored at full precision in the sector aggregate rows of both files.
    #    Values are expressed as a percentage in the source (e.g. 15.4 = 15.4%).
    #    Convert to proportions for regression use.
    # -----------------------------------------------------------------------
    df["P8_ROIC"] = df["P8_precomp"] / 100.0

    # Interest cover ratio (S4) €” direct from KPI, used in robustness
    df["IntCover_S4"] = df["S4_precomp"]

    # -----------------------------------------------------------------------
    # 9. Lagged CoC_Proxy for Model 2 and Model 3
    # -----------------------------------------------------------------------
    df["CoC_Proxy_L1"] = df.groupby("sector_code")["CoC_Proxy_raw"].shift(1)
    df["CoC_Proxy_L2"] = df.groupby("sector_code")["CoC_Proxy_raw"].shift(2)

    # -----------------------------------------------------------------------
    # 10. External variable placeholders
    #     r_SBP and CPI_inflation must be filled manually from SBP / PBS data.
    #     The formula columns delta_r_SBP, Interaction, and Real_CoC are
    #     computed here where the lagged r_SBP is available but will remain
    #     NaN until r_SBP is populated.
    # -----------------------------------------------------------------------
    if "r_SBP" not in df.columns:
        df["r_SBP"] = np.nan           # PLACEHOLDER: annual avg SBP policy rate
    if "CPI_inflation" not in df.columns:
        df["CPI_inflation"] = np.nan   # PLACEHOLDER: annual CPI inflation rate

    df["r_SBP_L1"]    = df.groupby("sector_code")["r_SBP"].shift(1)
    df["delta_r_SBP"] = df["r_SBP"] - df["r_SBP_L1"]
    df["Interaction"]  = df["CoC_Proxy_raw"] * df["delta_r_SBP"]
    df["Real_CoC"]     = df["CoC_Proxy_raw"] - df["CPI_inflation"]

    return df


# ---------------------------------------------------------------------------
# Winsorisation
# ---------------------------------------------------------------------------

def winsorize_panel(df: pd.DataFrame,
                    cols: list,
                    lower: float = WINS_LOWER,
                    upper: float = WINS_UPPER) -> pd.DataFrame:
    """
    Winsorise specified columns at the given percentile bounds, computed
    over the full panel (not sector-by-sector).

    Pre-winsorised values are copied to <col>_raw before clipping, so the
    extreme observations remain visible for diagnostic use.

    Args:
        df:    Panel DataFrame (already has raw variable columns).
        cols:  List of column names to winsorise.
        lower: Lower percentile (default 1st).
        upper: Upper percentile (default 99th).

    Returns:
        DataFrame with winsorised columns (originals preserved as _raw).
    """
    df = df.copy()
    for col in cols:
        if col not in df.columns:
            print(f"  WARNING: column '{col}' not found €” skipping winsorisation")
            continue
        raw_col = col + "_raw"
        if raw_col not in df.columns:
            df[raw_col] = df[col].copy()

        p_low  = df[col].quantile(lower)
        p_high = df[col].quantile(upper)
        n_clipped_low  = (df[col] < p_low).sum()
        n_clipped_high = (df[col] > p_high).sum()
        df[col] = df[col].clip(lower=p_low, upper=p_high)

        print(f"  Winsorise '{col}': "
              f"[{p_low:.4f}, {p_high:.4f}]  "
              f"({n_clipped_low} low, {n_clipped_high} high clipped)")
    return df


# ---------------------------------------------------------------------------
# Availability flags
# ---------------------------------------------------------------------------

def add_sample_flags(df: pd.DataFrame, estimation_codes: set) -> pd.DataFrame:
    """
    Add boolean flag columns indicating which rows belong to which
    estimation sample (to make downstream filtering straightforward).

      in_estimation_panel: True for the 14 non-All-Sector sectors
      in_model1_sample:    True if Inv_Rate is not NaN (has lagged OFA)
      in_model3_sample:    True if CoC_Proxy_L2 is not NaN (has two lags)

    Args:
        df:               Computed panel DataFrame.
        estimation_codes: Set of sector_code strings to include in estimation.

    Returns:
        DataFrame with three additional flag columns.
    """
    df = df.copy()
    df["in_estimation_panel"] = df["sector_code"].isin(estimation_codes)
    df["in_model1_sample"]    = df["in_estimation_panel"] & df["Inv_Rate_raw"].notna()
    df["in_model3_sample"]    = df["in_estimation_panel"] & df["CoC_Proxy_L2"].notna()
    df["robustness_excl"]     = df["sector_code"].isin(ROBUSTNESS_EXCLUDE)

    n_m1 = df["in_model1_sample"].sum()
    n_m3 = df["in_model3_sample"].sum()
    print(f"\n  Model 1 / 2 sample: {n_m1} sector-year obs  "
          f"(target 126 for OLD, 70 for FY25)")
    print(f"  Model 3 sample:     {n_m3} sector-year obs  "
          f"(target 98 for OLD, 42 for FY25)")
    return df


# ---------------------------------------------------------------------------
# Descriptive summary
# ---------------------------------------------------------------------------

def print_summary(df: pd.DataFrame, label: str) -> None:
    """
    Print a concise descriptive summary for the core research variables.

    Args:
        df:    Computed panel (estimation sectors only).
        label: Panel label for display.
    """
    core_vars = ["Inv_Rate_raw", "CoC_Proxy_raw", "P8_ROIC",
                 "Leverage_S1", "Cashflow", "SalesGrowth", "Size_ln"]
    est = df[df["in_estimation_panel"]]
    print(f"\n--- Descriptive summary for {label} estimation sectors ---")
    print(est[core_vars].describe().round(4).to_string())


# ---------------------------------------------------------------------------
# Main processing function
# ---------------------------------------------------------------------------

def process_panel(input_path: str,
                  output_path: str,
                  estimation_codes: set,
                  label: str) -> pd.DataFrame:
    """
    Load a raw extraction CSV, compute all variables, winsorise, add flags,
    and save.

    Args:
        input_path:        CSV from script 01 or 02.
        output_path:       Destination CSV.
        estimation_codes:  Set of sector_code strings for estimation sample.
        label:             Display label (e.g. 'OLD' or 'FY25').

    Returns:
        Fully computed and winsorised DataFrame.
    """
    print(f"\n{'=' * 65}")
    print(f"Processing {label} panel")
    print(f"{'=' * 65}")

    df = pd.read_csv(input_path, dtype={"sector_code": str})
    print(f"Loaded {len(df)} rows from {input_path}")

    df = compute_variables(df, label)

    # Winsorise investment rate and CoC proxy (on the full panel including
    # All Sector if present, but the winsorisation bounds are driven by the
    # estimation sectors which make up 140/150 rows)
    print("\nWinsorising at 1st / 99th percentile:")
    df = winsorize_panel(df, cols=["Inv_Rate_raw", "CoC_Proxy_raw"])
    # After winsorisation create the final analysis columns
    df["Inv_Rate"]   = df["Inv_Rate_raw"]
    df["CoC_Proxy"]  = df["CoC_Proxy_raw"]
    # Update lags to use the winsorised CoC_Proxy
    df["CoC_Proxy_L1"] = df.groupby("sector_code")["CoC_Proxy"].shift(1)
    df["CoC_Proxy_L2"] = df.groupby("sector_code")["CoC_Proxy"].shift(2)

    df = add_sample_flags(df, estimation_codes)
    print_summary(df, label)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved †’ {output_path}")
    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> tuple:
    """
    Compute variables for both the old and FY25 panels.

    Returns:
        Tuple of (df_old, df_fy25).
    """
    print("=" * 65)
    print("Script 03 €” Compute research variables")
    print("=" * 65)

    # Estimation sector codes (14 sectors, no All Sector)
    try:
        from config import ESTIMATION_SECTOR_CODES_OLD, ESTIMATION_SECTOR_CODES_FY25
    except ImportError:
        ESTIMATION_SECTOR_CODES_OLD = {
            "704","705","706","707","709","710","711","712",
            "714","715","726","727","728","729"
        }
        ESTIMATION_SECTOR_CODES_FY25 = ESTIMATION_SECTOR_CODES_OLD

    df_old = process_panel(
        input_path=INPUT_OLD,
        output_path=OUTPUT_OLD,
        estimation_codes=ESTIMATION_SECTOR_CODES_OLD,
        label="OLD (2014-23)",
    )

    df_fy25 = process_panel(
        input_path=INPUT_FY25,
        output_path=OUTPUT_FY25,
        estimation_codes=ESTIMATION_SECTOR_CODES_FY25,
        label="FY25",
    )

    return df_old, df_fy25


if __name__ == "__main__":
    run()

