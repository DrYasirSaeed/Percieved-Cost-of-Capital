"""
02_extract_firm_panel_fy25.py
==============================
Extract the firm-level validation panel from the SBP FSA NFC FY25 workbook.

SCOPE
-----
Sheet used    : 'FSA_NFCs_FY25'
Fiscal years  : FY2020 - FY2025  (FY2020 = OFA base year for Inv_Rate)
Unit of obs   : individual listed company x fiscal year
Firms expected: ~390 firms, 338 of which appear in all 6 years

IDENTIFICATION — HOW TO TELL FIRMS FROM SECTOR AGGREGATES
----------------------------------------------------------
The FY25 sheet uses a different identification rule than the old file:

  Primary test : Organisation Name column (col 3) != Sectors column (col 0)
                 -> if they match, the row is a sector aggregate (SKIP)
                 -> if they differ, the row is an individual firm  (KEEP)

  Secondary check (used as sanity, not as primary filter):
                 Financial Year End column (col 4) is non-null for firm rows
                 (carries 'Jun', 'Sep', 'Dec', or 'Mar') and blank/null for
                 sector aggregate rows.

  This FYE column is also extracted as a data column because it identifies
  non-June fiscal year firms — critical for the robustness check that
  excludes September-year-end Sugar companies from the policy rate
  alignment analysis.

KPI PRECISION IN THIS FILE
---------------------------
Unlike the old file, all pre-computed KPIs (P8, S1, S4) in the FY25 file
are stored at full floating-point precision (e.g. P8 = 11.07, not 11).
They can therefore be used directly as dependent variables and controls
without reconstruction from raw items.

ITEMS EXTRACTED
---------------
Same 11 raw balance sheet / income statement items as script 01, plus the
pre-computed KPIs P8, S1, S4 (safe to use in this file).

OUTPUT
------
  Extracted Data/02_raw_firm_panel_fy25.csv
    One row per (firm_id, fiscal_year).
    ~2,340 rows  (390 firms x 6 years, unbalanced).

Reference: FirmLevel_DataStrategy.docx; Gormsen & Huber (2024, 2025).
"""

import os
import sys
import pandas as pd

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from utils import normalize_item, parse_num

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SOURCE_FILE = os.path.join(
    os.path.dirname(CODES_DIR), "Source Data", "FSA_NFC_FY20_FY25.xlsx"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(CODES_DIR), "Extracted Data", "02_raw_firm_panel_fy25.csv"
)

SHEET_NAME = "FSA_NFCs_FY25"

# Column positions (0-based) in FSA_NFCs_FY25 sheet
COL_SECTORS  = 0   # Sector label  (same as Org Name for sector aggregates)
COL_SUBSECT  = 1   # Sub-sector
COL_CLASSIF  = 2   # Classification
COL_ORG      = 3   # Organisation Name  (company name for firm rows)
COL_FYE      = 4   # Financial Year End ('Jun', 'Sep', 'Dec', 'Mar'; blank for aggregates)
COL_ITEM     = 5   # Item Name
# Year value columns
YEAR_COLUMNS = {
    "FY20":  6, "FY21":  7, "FY22":  8,
    "FY23":  9, "FY24": 10, "FY25": 11,
}
YEAR_TO_INT = {
    "FY20": 2020, "FY21": 2021, "FY22": 2022,
    "FY23": 2023, "FY24": 2024, "FY25": 2025,
}

# All known sector aggregate names (used as exclusion list)
SECTOR_AGG_NAMES = {
    "All Sector", "Textile", "Coke and Refined Petroleum Products",
    "Chemicals, Chemical Products and Pharmaceuticals",
    "Electrical Machinery and Apparatus", "Paper, Paperboard and Products",
    "Fuel and Energy", "Information and Communication Services",
    "Manufacturing", "Motor Vehicles, Trailers & Autoparts",
    "Other Services Activities", "Sugar", "Food Products",
    "Mineral products", "Cement",
}

# ---------------------------------------------------------------------------
# Items to extract
#
# Raw balance-sheet / income-statement items: identical labels to old file
# (except Retention formula reference, which changed from F10-F11-F12 to
# F12-F13-F14 due to the Levies item inserted at F9 in FY2022 — same
# economic content, different numbering).
#
# KPIs P8, S1, S4 are INCLUDED here because they are full-precision in
# this file and can be used directly as DVs or controls in regression.
# ---------------------------------------------------------------------------
ITEM_LABELS = {
    # Balance sheet: assets
    "OFA_cost":            "2. Operating fixed assets at cost",
    # Balance sheet: equity and liabilities
    "ShareholdersEquity_C": "C. Shareholders' Equity (C1+C2+C3)",
    "D_NCL":               "D. Non-Current Liabilities (D1+D2+D3+D4+D5)",
    "E_CL":                "E. Current Liabilities (E1+E2+E3+E4)",
    "TotalAssets":         "Total Assets (A+B) / Equity & Liabilities (C+D+E)",
    # Income statement
    "EBIT":                "6. EBIT (F3-F4+F5)",
    "Sales":               "1. Sales",
    # Financial expenses sub-item only
    "InterestExpense":     "of which: (i) Interest expenses",
    # H. Miscellaneous
    # NOTE: retention formula reference shifted in FY25 (F12-F13-F14 vs F10-F11-F12)
    "CapEmployed":         "1. Total capital employed (C+D)",
    "Retention":           "2. Retention in business (F12-F13-F14)",
    "Depreciation":        "3. Depreciation for the year",
    # Pre-computed KPIs -- full precision in this file, safe to use directly
    "P8_precomp":          "P8. Return on capital employed (F6 as a % of Avg {Current year H1, previous year H1}",
    "S1_precomp":          "S1. Debt equity ratio [(D+E) to C]",
    "S4_precomp":          "S4. Interest cover ratio ( F6 to F7(i))",
}


# ---------------------------------------------------------------------------
# Step 1 -- Load sheet (skip the 3 title rows above the column header)
# ---------------------------------------------------------------------------

def load_sheet(source_path: str) -> pd.DataFrame:
    """
    Read FSA_NFCs_FY25 sheet, skipping the 3 decorative title rows.

    The actual data header row is row 4 (1-indexed); rows 1-3 are blank or
    contain only a title string.  We read without a header, then drop the
    first 4 rows (title rows + the header row itself) so all subsequent
    row access is positional.

    Args:
        source_path: Absolute path to FSA_NFC_FY20_FY25.xlsx.

    Returns:
        DataFrame starting at the first data row (row 5 in the workbook).
    """
    print(f"Loading '{SHEET_NAME}' from:\n  {source_path}")
    df = pd.read_excel(source_path, sheet_name=SHEET_NAME, header=None)
    # Rows 0-3 are title/header -> drop; row 4 onwards is data
    df = df.iloc[4:].reset_index(drop=True)
    print(f"  Data rows after skipping title/header: {len(df):,}")
    return df


# ---------------------------------------------------------------------------
# Step 2 -- Parse firm rows into nested dict
# ---------------------------------------------------------------------------

def parse_firm_data(df: pd.DataFrame) -> tuple:
    """
    Collect data for individual firm rows.

    Identification: a row is a FIRM when Organisation Name (col 3) differs
    from the Sectors label (col 0).  The presence of a non-null Financial
    Year End value (col 4) provides a redundant confirmation.

    Args:
        df: Raw DataFrame from load_sheet() (title rows already removed).

    Returns:
        Tuple of:
          data          {firm_id: {norm_item: {fy_label: value}}}
          firm_meta     {firm_id: {'sector': str, 'subsector': str, 'fye': str}}
          ordered_firms list of firm_ids in first-appearance order
    """
    data          = {}
    firm_meta     = {}
    ordered_firms = []

    skipped_agg   = 0
    rows_kept     = 0

    for _, row in df.iterrows():
        sectors_raw = row[COL_SECTORS]
        org_raw     = row[COL_ORG]
        item_raw    = row[COL_ITEM]
        fye_raw     = row[COL_FYE]

        if pd.isna(org_raw) or pd.isna(item_raw):
            continue

        sectors_str = str(sectors_raw).strip() if pd.notna(sectors_raw) else ""
        org_str     = str(org_raw).strip()
        item_str    = normalize_item(item_raw)
        fye_str     = str(fye_raw).strip() if pd.notna(fye_raw) else ""

        if not org_str or not item_str:
            continue

        # Primary filter: sector aggregates have identical Sectors and Org Name
        if sectors_str == org_str or org_str in SECTOR_AGG_NAMES:
            skipped_agg += 1
            continue

        firm_id = org_str   # full company name, e.g. "Attock Cement Pakistan Ltd."

        if firm_id not in data:
            data[firm_id]      = {}
            ordered_firms.append(firm_id)
            subsect_str = str(row[COL_SUBSECT]).strip() if pd.notna(row[COL_SUBSECT]) else ""
            firm_meta[firm_id] = {
                "sector":    sectors_str,
                "subsector": subsect_str,
                "fye":       fye_str,   # fiscal year-end month; blank for aggregates
            }
        else:
            # Update FYE if it was blank on the first row but now populated
            if not firm_meta[firm_id]["fye"] and fye_str:
                firm_meta[firm_id]["fye"] = fye_str

        year_vals = {}
        for fy_lbl, col in YEAR_COLUMNS.items():
            cell = row[col] if col < len(row) else None
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                year_vals[fy_lbl] = None
            elif isinstance(cell, (int, float)):
                year_vals[fy_lbl] = float(cell)
            else:
                year_vals[fy_lbl] = parse_num(cell)

        data[firm_id][item_str] = year_vals
        rows_kept += 1

    print(f"  Rows parsed: kept={rows_kept:,}  skipped(agg)={skipped_agg:,}")
    print(f"  Unique firms identified: {len(ordered_firms):,}")
    return data, firm_meta, ordered_firms


# ---------------------------------------------------------------------------
# Step 3 -- Reshape to long format
# ---------------------------------------------------------------------------

def reshape_to_long(data: dict,
                    firm_meta: dict,
                    ordered_firms: list) -> pd.DataFrame:
    """
    Build a tidy long-format DataFrame from the nested dict.

    FYE (fiscal year end month) is included as a column so that robustness
    checks excluding non-June firms can be applied without re-reading the
    source file.

    Args:
        data:          Nested dict from parse_firm_data().
        firm_meta:     Metadata dict from parse_firm_data().
        ordered_firms: Ordered list of firm IDs.

    Returns:
        Long-format DataFrame.
    """
    records = []

    for firm_id in ordered_firms:
        meta     = firm_meta[firm_id]
        item_map = data[firm_id]

        # Years this firm has at least one non-null value
        years_with_data = set()
        for item_dict in item_map.values():
            for fy, val in item_dict.items():
                if val is not None:
                    years_with_data.add(fy)

        for fy_lbl in YEAR_COLUMNS:
            if fy_lbl not in years_with_data:
                continue

            rec = {
                "firm_id":     firm_id,
                "sector":      meta["sector"],
                "subsector":   meta["subsector"],
                "fye":         meta["fye"],   # 'Jun', 'Sep', 'Dec', 'Mar', or ''
                "fiscal_year": YEAR_TO_INT[fy_lbl],
                "source_file": "FSA_NFC_FY25",
            }

            for var, label in ITEM_LABELS.items():
                val         = None
                norm_label  = normalize_item(label)
                label_lower = norm_label.lower()

                if norm_label in item_map:
                    val = item_map[norm_label].get(fy_lbl)

                if val is None:
                    for stored, year_dict in item_map.items():
                        if label_lower in stored.lower():
                            v = year_dict.get(fy_lbl)
                            if v is not None:
                                val = v
                                break

                rec[var] = val

            records.append(rec)

    id_cols  = ["firm_id", "sector", "subsector", "fye", "fiscal_year", "source_file"]
    var_cols = list(ITEM_LABELS.keys())
    df = pd.DataFrame(records)[id_cols + var_cols]

    n_firms    = df["firm_id"].nunique()
    n_obs      = len(df)
    yr_counts  = df.groupby("firm_id")["fiscal_year"].count()
    n_balanced = (yr_counts == 6).sum()

    print(f"\nLong-format panel: {n_obs:,} firm-year rows")
    print(f"  Unique firms: {n_firms:,}")
    print(f"  Firms with all 6 years (balanced): {n_balanced:,}")
    print(f"  Fiscal years: {sorted(df['fiscal_year'].unique())}")

    # FYE distribution
    fye_counts = df.drop_duplicates("firm_id")["fye"].value_counts()
    print(f"\n  Fiscal year-end distribution (firms):")
    for fye_val, cnt in fye_counts.items():
        print(f"    {fye_val or '(blank)':>6s}: {cnt:>4} firms")

    return df


# ---------------------------------------------------------------------------
# Step 4 -- Completeness check
# ---------------------------------------------------------------------------

def validate_extraction(df: pd.DataFrame) -> None:
    """
    Print non-null rates for core variables. Also count zero-interest and
    non-June fiscal year firms.

    Args:
        df: Long-format DataFrame from reshape_to_long().
    """
    print("\n--- Extraction completeness ---")
    total = len(df)
    core  = ["OFA_cost", "InterestExpense", "D_NCL", "E_CL",
             "TotalAssets", "EBIT", "ShareholdersEquity_C",
             "Sales", "CapEmployed", "P8_precomp", "S1_precomp"]
    for var in core:
        n   = df[var].notna().sum()
        pct = 100 * n / total if total else 0
        flag = "  *** CHECK" if pct < 90 else ""
        print(f"  {var:<25s}: {n:>6,}/{total:,}  ({pct:5.1f}%){flag}")

    n_zero = (df["InterestExpense"] == 0).sum()
    n_nonj = df[df["fye"].notna() & (df["fye"] != "") & (df["fye"] != "Jun")]["firm_id"].nunique()
    print(f"\n  Zero interest expense obs: {n_zero:,}  (zero-debt firms; flagged in script 03)")
    print(f"  Non-June FYE firms: {n_nonj:,}  (flagged for robustness checks)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(source_path: str = SOURCE_FILE,
        output_path: str = OUTPUT_FILE) -> pd.DataFrame:
    """
    Execute the full firm-level extraction for the FY25 workbook.

    Args:
        source_path: Path to FSA_NFC_FY20_FY25.xlsx.
        output_path: Destination CSV path.

    Returns:
        Long-format firm-year DataFrame.
    """
    print("=" * 65)
    print("Script 02 -- Extract firm-level panel from FSA NFC FY25")
    print("=" * 65)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df_raw            = load_sheet(source_path)
    data, meta, firms = parse_firm_data(df_raw)
    df_long           = reshape_to_long(data, meta, firms)
    validate_extraction(df_long)

    df_long.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved -> {output_path}")
    return df_long


if __name__ == "__main__":
    run()
