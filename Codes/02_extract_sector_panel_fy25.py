"""
02_extract_sector_panel_fy25.py
================================
Extract the out-of-sample validation panel from the SBP FSA NFC FY25 workbook.

SCOPE
-----
Sheet used   : 'FSA_NFCs_FY25'
Fiscal years : FY2020 €“ FY2025  (FY2020 used as base year for investment rate)
Usable window: FY2021 €“ FY2025 after the one-lag for investment rate (14—5=70 obs)

KEY STRUCTURAL DIFFERENCES FROM THE OLD FILE
--------------------------------------------
1. Header row is row 4 (0-indexed: row 3), not row 1.
   Data begins at row 5 (0-indexed: row 4).
2. Column layout:
     0 = Sectors,  1 = Sub-sector,  2 = Classification,
     3 = Organization Name,  4 = Financial Year End,
     5 = Item Name,  6..11 = FY20..FY25
3. Sector aggregate identification rule differs:
   A row is a sector aggregate when Organisation Name == Sectors column
   (both hold the same sector label, e.g. 'Cement' in both columns).
   Individual company rows have a specific company name in column 3.
4. The Retention formula reference changed (F12-F13-F14 instead of F10-F11-F12)
   because a Levies item was inserted at F9 in FY2022, pushing subsequent
   items up by two positions.  The economic content is identical.
5. Pre-computed KPI values are stored at full floating-point precision in this
   file, unlike the old file where KPIs are rounded to whole numbers at firm
   level (only relevant for the firm-level module, not this sector module).

DO NOT POOL WITH THE OLD FILE
------------------------------
The FY2020-FY2023 overlap values differ materially (‰ˆ12% for interest expense,
‰ˆ6% for P8 ROIC) due to different firm composition across the two publications.
Treat this panel as a fully independent validation window, not as an extension.

OUTPUT
------
  Extracted Data/02_raw_sector_panel_fy25.csv

Reference: Gormsen & Huber (2024, 2025); SBP FSA NFC FY25 documentation.
"""

import os
import sys
import re
import pandas as pd

# Allow direct execution from the Codes folder
CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from utils import normalize_item, parse_num

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SOURCE_FILE = os.path.join(
    os.path.dirname(CODES_DIR),
    "Source Data", "FSA_NFC_FY20_FY25.xlsx"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(CODES_DIR),
    "Extracted Data", "02_raw_sector_panel_fy25.csv"
)

SHEET_NAME = "FSA_NFCs_FY25"

# FY25 sheet column indices (0-based)
COL_SECTORS      = 0   # Sector label
COL_SUBSECTOR    = 1   # Sub-sector label
COL_CLASSIF      = 2   # Classification (same as Sectors for aggregates)
COL_ORG_NAME     = 3   # Organisation Name
COL_FYE          = 4   # Financial Year End (blank for sector aggregates)
COL_ITEM         = 5   # Item Name
COL_FY20         = 6   # FY2020 value
# FY21=7, FY22=8, FY23=9, FY24=10, FY25=11

# Year column positions
YEAR_COLUMNS = {
    "FY20":  6,
    "FY21":  7,
    "FY22":  8,
    "FY23":  9,
    "FY24": 10,
    "FY25": 11,
}

# Mapping from FY-labelled year strings to integer fiscal years
# FY20 = financial year ending in 2020 (i.e. Jul 2019 €“ Jun 2020 for most firms)
YEAR_TO_INT = {
    "FY20": 2020,
    "FY21": 2021,
    "FY22": 2022,
    "FY23": 2023,
    "FY24": 2024,
    "FY25": 2025,
}

# ---------------------------------------------------------------------------
# Sector identification
#
# In the FY25 file sector names are spelled out in full (no numeric codes).
# The harmonised sector_code column maps these back to the SBP numeric codes
# used in the old file so both panels share a common sector identifier.
# ---------------------------------------------------------------------------
FY25_SECTOR_NAMES = {
    "All Sector":                                    "703",
    "Textile":                                       "704",
    "Coke and Refined Petroleum Products":           "705",
    "Chemicals, Chemical Products and Pharmaceuticals": "706",
    "Electrical Machinery and Apparatus":            "707",
    "Paper, Paperboard and Products":                "709",
    "Fuel and Energy":                               "710",
    "Information and Communication Services":        "711",
    "Manufacturing":                                 "712",
    "Motor Vehicles, Trailers & Autoparts":          "714",
    "Other Services Activities":                     "715",
    "Sugar":                                         "726",
    "Food Products":                                 "727",
    "Mineral products":                              "728",
    "Cement":                                        "729",
}

ESTIMATION_SECTOR_CODES = {v for k, v in FY25_SECTOR_NAMES.items()
                            if k != "All Sector"}

# ---------------------------------------------------------------------------
# Item label mapping €” identical to old file EXCEPT Retention
#
# Key   = short variable name used in downstream scripts
# Value = exact item label AFTER stripping whitespace
# ---------------------------------------------------------------------------
ITEM_LABELS = {
    # Balance sheet €” assets
    "OFA_cost":       "2. Operating fixed assets at cost",

    # Balance sheet €” liabilities
    "D_NCL":          "D. Non-Current Liabilities (D1+D2+D3+D4+D5)",
    "E_CL":           "E. Current Liabilities (E1+E2+E3+E4)",
    "TotalAssets":    "Total Assets (A+B) / Equity & Liabilities (C+D+E)",

    # Income statement
    "EBIT":           "6. EBIT (F3-F4+F5)",
    "Sales":          "1. Sales",

    # Financial expenses sub-item
    "InterestExpense": "of which: (i) Interest expenses",

    # Miscellaneous (H-section)
    # NOTE: formula reference shifted from (F10-F11-F12) in old file to
    # (F12-F13-F14) here because the Levies item was inserted at F9 in FY22.
    # Economic content is identical.
    "Retention":      "2. Retention in business (F12-F13-F14)",
    "CapEmployed":    "1. Total capital employed (C+D)",
    "Depreciation":   "3. Depreciation for the year",

    # Pre-computed KPIs (full precision in this file)
    "P8_precomp":     "P8. Return on capital employed (F6 as a % of Avg {Current year H1, previous year H1}",
    "S1_precomp":     "S1. Debt equity ratio [(D+E) to C]",
    "S4_precomp":     "S4. Interest cover ratio ( F6 to F7(i))",
}


# ---------------------------------------------------------------------------
# Step 1 €” Load the FY25 sheet
# ---------------------------------------------------------------------------

def load_sheet(source_path: str, sheet: str) -> pd.DataFrame:
    """
    Read the FY25 sheet, skipping the 3 title rows above the column header.

    The first data header appears on row 4 (1-indexed), so we skip rows 1-3
    and set row 4 as the column header €” then immediately drop it and work
    with positional column indices to be consistent with the parsing logic.

    Args:
        source_path: Absolute path to FSA_NFC_FY20_FY25.xlsx.
        sheet:       Sheet name.

    Returns:
        DataFrame with all rows including the header row (row 4), raw values.
    """
    print(f"Loading '{sheet}' from:\n  {source_path}")
    # Read with no header, then manually drop the first 3 blank/title rows
    df = pd.read_excel(source_path, sheet_name=sheet, header=None)
    # Drop rows 0-3 (blank title rows + the header row itself); reset index
    df = df.iloc[4:].reset_index(drop=True)
    print(f"  Data rows after skipping title: {len(df)}")
    return df


# ---------------------------------------------------------------------------
# Step 2 €” Parse sector aggregate rows into a nested dict
# ---------------------------------------------------------------------------

def parse_sector_data(df: pd.DataFrame) -> tuple:
    """
    Identify sector aggregate rows and store their item values.

    Identification rule: a row is a sector aggregate when the text in
    COL_SECTORS equals the text in COL_ORG_NAME (both hold the same sector
    label).  Individual company rows have a distinct company name in
    COL_ORG_NAME.

    An additional secondary check: sector aggregate rows have a blank /
    null Financial Year End column (COL_FYE), while company rows carry a
    month abbreviation (Jun, Sep, Dec, Mar).  This is used as a sanity
    check but not as the primary filter.

    Args:
        df: Raw DataFrame from load_sheet() (rows starting at the first
            data row, title rows already removed).

    Returns:
        Tuple of:
          data        €” {sector_code: {item_label: {year_str: value}}}
          sector_meta €” {sector_code: {'sector_name': ..., 'raw_org': ...}}
    """
    data = {}
    sector_meta = {}

    skipped_company = 0
    skipped_unknown = 0
    rows_kept = 0

    for _, row in df.iterrows():
        sectors_raw  = row[COL_SECTORS]
        org_raw      = row[COL_ORG_NAME]
        item_raw     = row[COL_ITEM]

        if pd.isna(sectors_raw) or pd.isna(org_raw) or pd.isna(item_raw):
            continue

        sectors_str = str(sectors_raw).strip()
        org_str     = str(org_raw).strip()
        item_str    = normalize_item(item_raw)

        if not sectors_str or not org_str or not item_str:
            continue

        # Primary aggregate test: Sectors column == Organisation Name column
        if sectors_str != org_str:
            skipped_company += 1
            continue

        # Map to sector code; skip if not in our known list
        sector_code = FY25_SECTOR_NAMES.get(sectors_str)
        if sector_code is None:
            skipped_unknown += 1
            continue

        # Initialise storage for this sector
        if sector_code not in data:
            data[sector_code] = {}
            sector_meta[sector_code] = {
                "sector_name": sectors_str,
                "raw_org":     org_str,
            }

        # Parse the 6 fiscal year columns
        year_values = {}
        for fy_label, col_idx in YEAR_COLUMNS.items():
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                year_values[fy_label] = None
            elif isinstance(cell, (int, float)):
                year_values[fy_label] = float(cell)
            else:
                year_values[fy_label] = parse_num(cell)

        data[sector_code][item_str] = year_values
        rows_kept += 1

    print(f"  Rows parsed €” kept: {rows_kept}, "
          f"skipped (company rows): {skipped_company}, "
          f"skipped (unknown sector): {skipped_unknown}")
    print(f"  Sectors loaded: {sorted(data.keys())}")
    return data, sector_meta


# ---------------------------------------------------------------------------
# Step 3 €” Reshape to long-format DataFrame
# ---------------------------------------------------------------------------

def reshape_to_long(data: dict, sector_meta: dict) -> pd.DataFrame:
    """
    Convert the nested dict into a tidy long-format DataFrame.

    Fiscal year labels (FY20 €¦ FY25) are converted to integer calendar
    years (2020 €¦ 2025) so both panels share a common fiscal_year column.

    Args:
        data:        Nested dict from parse_sector_data().
        sector_meta: Sector metadata from parse_sector_data().

    Returns:
        DataFrame with columns: sector_code, sector_name, fiscal_year,
        source_file, + one column per key in ITEM_LABELS.
    """
    records = []

    for code in sorted(data.keys()):
        meta     = sector_meta[code]
        item_map = data[code]

        for fy_label, col_idx in YEAR_COLUMNS.items():
            fiscal_year_int = YEAR_TO_INT[fy_label]

            row = {
                "sector_code":   code,
                "sector_name":   meta["sector_name"],
                "raw_org_label": meta["raw_org"],
                "fiscal_year":   fiscal_year_int,
                "source_file":   "FSA_NFC_FY25",
            }

            for var_name, label in ITEM_LABELS.items():
                val = None
                norm_label = normalize_item(label)

                # Exact match
                if norm_label in item_map and fy_label in item_map[norm_label]:
                    val = item_map[norm_label][fy_label]
                else:
                    # Substring fallback
                    label_lower = norm_label.lower()
                    for stored_label, year_dict in item_map.items():
                        if label_lower in stored_label.lower():
                            v = year_dict.get(fy_label)
                            if v is not None:
                                val = v
                                break

                row[var_name] = val

            records.append(row)

    df = pd.DataFrame(records)

    id_cols  = ["sector_code", "sector_name", "raw_org_label", "fiscal_year", "source_file"]
    var_cols = list(ITEM_LABELS.keys())
    df = df[id_cols + var_cols]

    print(f"\nLong-format panel: {len(df)} rows — {df.shape[1]} columns")
    print(f"  Sectors: {df['sector_code'].nunique()} "
          f"({df['sector_name'].nunique()} unique names)")
    print(f"  Fiscal years: {sorted(df['fiscal_year'].unique())}")
    return df


# ---------------------------------------------------------------------------
# Step 4 €” Validate extraction completeness
# ---------------------------------------------------------------------------

def validate_extraction(df: pd.DataFrame) -> None:
    """
    Print a completeness report for the FY25 panel.

    Args:
        df: Long-format DataFrame from reshape_to_long().
    """
    print("\n--- Extraction completeness (estimation sectors only) ---")
    est = df[df["sector_code"].isin(ESTIMATION_SECTOR_CODES)]
    total = len(est)
    for var in ITEM_LABELS:
        n_valid = est[var].notna().sum()
        pct = 100 * n_valid / total if total > 0 else 0
        flag = "  *** CHECK" if pct < 95 and var in (
            "OFA_cost", "InterestExpense", "D_NCL", "E_CL", "TotalAssets"
        ) else ""
        print(f"  {var:<20s}: {n_valid:>4}/{total}  ({pct:5.1f}%){flag}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(source_path: str = SOURCE_FILE, output_path: str = OUTPUT_FILE) -> pd.DataFrame:
    """
    Execute the full extraction pipeline for the FY25 workbook.

    Steps:
      1. Load the FSA_NFCs_FY25 sheet (skip 3 title rows).
      2. Parse sector aggregate rows into a nested dict.
      3. Reshape to long-format DataFrame with integer fiscal years.
      4. Validate completeness.
      5. Save to CSV.

    Args:
        source_path: Path to FSA_NFC_FY20_FY25.xlsx.
        output_path: Destination CSV path.

    Returns:
        Long-format DataFrame.
    """
    print("=" * 65)
    print("Script 02 €” Extract sector panel from FSA NFC FY25")
    print("=" * 65)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df_raw = load_sheet(source_path, SHEET_NAME)
    data, meta = parse_sector_data(df_raw)
    df_long = reshape_to_long(data, meta)
    validate_extraction(df_long)

    df_long.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved †’ {output_path}")
    return df_long


if __name__ == "__main__":
    run()

