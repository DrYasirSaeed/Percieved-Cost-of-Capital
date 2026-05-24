"""
01_extract_sector_panel_old.py
==============================
Extract the main estimation panel from the SBP FSA 2005-23 workbook.

SCOPE
-----
Sheet used   : '2014-23'  (the only estimation-quality sheet)
Sheets skipped: '2005-08' and '2009-13' €” excluded per research design because
  (a) interest expense is not separately reported in 2005-08,
  (b) the KPI uses P5 (PBT-based) rather than P8 (EBIT-based) ROIC in both
      early periods, creating a spurious break at the 2014 boundary,
  (c) capital work in progress is absent in 2005-08.

UNIT OF OBSERVATION
-------------------
Each row in the output is one (sector_code, sector_name, fiscal_year) cell.
The raw panel has 14 sectors — 10 fiscal years = 140 observations.
After construction of one-lag variables the usable estimation window shrinks
to 14 — 9 = 126 observations (FY2015€“FY2023).

ITEMS EXTRACTED
---------------
See ITEM_LABELS dict below for the exact (post-strip) label text and the
short variable name assigned to each item.  Labels are matched with
normalize_item() which collapses leading/trailing whitespace.

OUTPUT
------
  Extracted Data/01_raw_sector_panel_old.csv
    One row per (sector_code, year) €” raw financial statement values,
    no derived variables yet.  Variable construction is in script 03.

Reference: Gormsen & Huber (2024, 2025); SBP FSA 2005-23 documentation.
"""

import os
import sys
import re
import pandas as pd

# ---------------------------------------------------------------------------
# Allow running this script directly from the Codes folder without installing
# the package.  Adds the Codes directory to sys.path so 'import utils' works.
# ---------------------------------------------------------------------------
CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from utils import normalize_item, parse_num

# ---------------------------------------------------------------------------
# File paths  (edit SOURCE_FILE or OUTPUT_FILE if the directory layout changes)
# ---------------------------------------------------------------------------
SOURCE_FILE = os.path.join(
    os.path.dirname(CODES_DIR),
    "Source Data", "2005-23.xlsx"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(CODES_DIR),
    "Extracted Data", "01_raw_sector_panel_old.csv"
)

SHEET_NAME = "2014-23"

# Year column positions in the '2014-23' sheet (0-based column index)
# Columns: 0=Sector, 1=Sub-Sector, 2=Sector/Organisation Name, 3=Item Name,
#          4=2014, 5=2015, ..., 13=2023
YEAR_COLUMNS = {
    "2014":  4,
    "2015":  5,
    "2016":  6,
    "2017":  7,
    "2018":  8,
    "2019":  9,
    "2020": 10,
    "2021": 11,
    "2022": 12,
    "2023": 13,
}

# ---------------------------------------------------------------------------
# Sector filter: 14 estimation sectors (3-digit SBP codes)
#
# The All Sector aggregate (703) is a weighted sum of all 14 rows €” including
# it in regression would create mechanical multicollinearity.  It is retained
# only for validation output.
#
# Textile sub-sector aggregates (723 Spinning, 724 Made-up, 725 Other) are
# sub-components of the Textile Sector aggregate (704); including them would
# double-count Textile.
# ---------------------------------------------------------------------------
ESTIMATION_SECTORS = {
    "704": "Textile",
    "705": "Coke and Refined Petroleum Products",
    "706": "Chemicals, Chemical Products and Pharmaceuticals",
    "707": "Electrical Machinery and Apparatus",
    "709": "Paper, Paperboard and Products",
    "710": "Fuel and Energy",
    "711": "Information and Communication Services",
    "712": "Manufacturing",
    "714": "Motor Vehicles, Trailers & Autoparts",
    "715": "Other Services Activities",
    "726": "Sugar",
    "727": "Food Products",
    "728": "Mineral products",
    "729": "Cement",
}

# All Sector retained separately for descriptive validation
VALIDATION_SECTOR = {"703": "All Sector"}

# All sectors we want to keep (estimation + validation aggregates)
ALL_SECTORS_TO_KEEP = {**ESTIMATION_SECTORS, **VALIDATION_SECTOR}

# Sector codes that must be excluded (sub-aggregates of Textile)
TEXTILE_SUB_CODES = {"723", "724", "725"}

# ---------------------------------------------------------------------------
# Item label mapping
# Key   = short variable name used in downstream scripts
# Value = exact item label text AFTER stripping whitespace
#         (the SBP workbook indents sub-items with leading spaces)
#
# Precedence: if multiple candidates are listed the first exact match wins;
# if no exact match the first substring match wins (see utils.get_item_year_value).
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

    # Financial expenses sub-item (NOT the aggregate F.7 line)
    "InterestExpense": "of which: (i) Interest expenses",

    # Miscellaneous (H-section)
    "Retention":      "2. Retention in business (F10-F11-F12)",
    "CapEmployed":    "1. Total capital employed (C+D)",
    "Depreciation":   "3. Depreciation for the year",

    # Pre-computed KPIs (I-section) €” used directly, not reconstructed
    "P8_precomp":     "P8. Return on capital employed (F6 as a % of Avg {Current year H1, previous year H1}",
    "S1_precomp":     "S1. Debt equity ratio [(D+E) to C]",
    "S4_precomp":     "S4. Interest cover ratio ( F6 to F7(i))",
}


# ---------------------------------------------------------------------------
# Step 1 €” Load the workbook sheet into a DataFrame
# ---------------------------------------------------------------------------

def load_sheet(source_path: str, sheet: str) -> pd.DataFrame:
    """
    Read the specified sheet from the SBP FSA workbook into a raw DataFrame.

    No headers are assumed; column references are positional throughout.

    Args:
        source_path: Absolute path to 2005-23.xlsx.
        sheet:       Sheet name (should be '2014-23' for this pipeline).

    Returns:
        DataFrame with one row per raw workbook row and integer column indices.
    """
    print(f"Loading '{sheet}' from:\n  {source_path}")
    df = pd.read_excel(source_path, sheet_name=sheet, header=None)
    print(f"  Sheet dimensions: {df.shape[0]} rows — {df.shape[1]} columns")
    return df


# ---------------------------------------------------------------------------
# Step 2 €” Parse into a nested dict  {sector_code: {item_label: {year: value}}}
# ---------------------------------------------------------------------------

def parse_sector_data(df: pd.DataFrame) -> dict:
    """
    Iterate over every row and build a nested dictionary keyed by
    (sector_code †’ normalised_item_label †’ fiscal_year †’ numeric_value).

    Filtering rules applied here:
      - Rows whose Sector/Organisation Name starts with a 3-digit code
        present in ALL_SECTORS_TO_KEEP are retained.
      - Rows whose code is in TEXTILE_SUB_CODES are silently skipped.
      - All other rows (individual company rows, blank rows, header rows)
        are skipped.

    Args:
        df: Raw DataFrame from load_sheet().

    Returns:
        Nested dict: {sector_code_str: {item_label: {year_str: float_or_None}}}
    """
    data = {}          # {sector_code: {item: {year: value}}}
    sector_meta = {}   # {sector_code: {'raw_org': ..., 'sector_col': ...}}

    # Regex to identify 3-digit code at the start of Org Name (e.g. "704 - Textile Sector")
    sector_pattern = re.compile(r'^(\d{3})\s*-\s*')

    skipped_sub = 0
    skipped_other = 0
    rows_kept = 0

    for row_idx, row in df.iterrows():
        org_raw = row[2]
        item_raw = row[3]

        if pd.isna(org_raw) or pd.isna(item_raw):
            continue

        org_str = str(org_raw).strip()
        item_str = normalize_item(item_raw)

        if not org_str or not item_str:
            continue

        match = sector_pattern.match(org_str)
        if not match:
            # Not a 3-digit coded row †’ individual company or header row
            skipped_other += 1
            continue

        code = match.group(1)

        # Drop Textile sub-aggregates
        if code in TEXTILE_SUB_CODES:
            skipped_sub += 1
            continue

        # Drop any other codes not in our keep list
        if code not in ALL_SECTORS_TO_KEEP:
            continue

        # Initialise storage for this sector on first encounter
        if code not in data:
            data[code] = {}
            sector_meta[code] = {
                "raw_org":    org_str,
                "sector_col": str(row[0]).strip() if pd.notna(row[0]) else "",
            }

        # Parse the 10 year columns
        year_values = {}
        for year_str, col_idx in YEAR_COLUMNS.items():
            cell = row[col_idx] if col_idx < len(row) else None
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                year_values[year_str] = None
            elif isinstance(cell, (int, float)):
                year_values[year_str] = float(cell)
            else:
                year_values[year_str] = parse_num(cell)

        data[code][item_str] = year_values
        rows_kept += 1

    print(f"  Rows parsed €” kept: {rows_kept}, "
          f"skipped (textile sub): {skipped_sub}, "
          f"skipped (company/other): {skipped_other}")
    print(f"  Sectors loaded: {sorted(data.keys())}")
    return data, sector_meta


# ---------------------------------------------------------------------------
# Step 3 €” Reshape to long-format DataFrame
# ---------------------------------------------------------------------------

def reshape_to_long(data: dict, sector_meta: dict) -> pd.DataFrame:
    """
    Convert the nested dict produced by parse_sector_data() into a tidy
    long-format DataFrame: one row per (sector_code, fiscal_year) cell,
    one column per extracted item.

    Items not found for a given sector will appear as NaN.

    Args:
        data:        Nested dict from parse_sector_data().
        sector_meta: Sector metadata dict from parse_sector_data().

    Returns:
        DataFrame with columns:
            sector_code, sector_name, raw_org_label, fiscal_year,
            + one column per key in ITEM_LABELS.
    """
    records = []

    for code in sorted(data.keys()):
        meta = sector_meta[code]
        sector_name = ALL_SECTORS_TO_KEEP.get(code, meta["raw_org"])
        item_map = data[code]   # {normalised_label: {year: value}}

        for year_str in YEAR_COLUMNS:
            row = {
                "sector_code":    code,
                "sector_name":    sector_name,
                "raw_org_label":  meta["raw_org"],
                "fiscal_year":    int(year_str),
                "source_file":    "FSA_2005-23",
            }

            for var_name, label in ITEM_LABELS.items():
                # Look up using exact match first, then substring fallback
                val = None
                norm_label = normalize_item(label)

                # Exact match
                if norm_label in item_map and year_str in item_map[norm_label]:
                    val = item_map[norm_label][year_str]
                else:
                    # Substring match: find a stored label that contains our target
                    label_lower = norm_label.lower()
                    for stored_label, year_dict in item_map.items():
                        if label_lower in stored_label.lower():
                            v = year_dict.get(year_str)
                            if v is not None:
                                val = v
                                break

                row[var_name] = val

            records.append(row)

    df = pd.DataFrame(records)

    # Set intuitive column order
    id_cols = ["sector_code", "sector_name", "raw_org_label", "fiscal_year", "source_file"]
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
    Print a completeness report showing how many of the 140 sector-year
    cells have valid (non-NaN) values for each extracted item.

    A missing rate above 5% for a core variable (OFA_cost, InterestExpense,
    D_NCL, E_CL, TotalAssets) should be investigated before proceeding to
    variable construction.

    Args:
        df: Long-format DataFrame from reshape_to_long().
    """
    print("\n--- Extraction completeness (estimation sectors only) ---")
    est = df[df["sector_code"].isin(ESTIMATION_SECTORS)]
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
    Execute the full extraction pipeline for the old (2005-23) workbook.

    Steps:
      1. Load the 2014-23 sheet.
      2. Parse sector aggregate rows into a nested dict.
      3. Reshape to long-format DataFrame.
      4. Validate completeness.
      5. Save to CSV.

    Args:
        source_path: Path to 2005-23.xlsx  (default: SOURCE_FILE constant).
        output_path: Destination CSV path  (default: OUTPUT_FILE constant).

    Returns:
        Long-format DataFrame (also written to output_path).
    """
    print("=" * 65)
    print("Script 01 €” Extract sector panel from FSA 2005-23 (2014-23 sheet)")
    print("=" * 65)

    # Ensure the output directory exists
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

