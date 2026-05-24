"""
01_extract_firm_panel_old.py
=============================
Extract the firm-level panel from the SBP FSA 2005-23 workbook.

SCOPE
-----
Sheet used    : '2014-23'  (the only estimation-quality sheet)
Unit of obs   : individual listed company x fiscal year
Firms expected: ~433 firms, 323 of which appear in all 10 years

IDENTIFICATION — HOW TO TELL FIRMS FROM SECTOR AGGREGATES
----------------------------------------------------------
The 2014-23 sheet mixes both in the same rows.  The Sector/Organisation
Name column (col 2, 0-based) is the sole discriminator:

  Starts with 3-digit code  (703, 704, ..., 729)  -> sector aggregate  SKIP
  Starts with 723/724/725                          -> Textile sub-agg   SKIP
  Starts with 6-digit code  (e.g. 380002)         -> individual firm   KEEP
  Any other text (header, blank)                  -> metadata          SKIP

ITEMS EXTRACTED PER FIRM
-------------------------
See ITEM_LABELS dict.  Key addition vs. sector-level script:
  ShareholdersEquity_C  — needed to reconstruct S1 = (D+E)/C at full
                          precision (old file KPIs are integer-rounded).

IMPORTANT: P8, S1, S4 pre-computed KPIs are intentionally NOT extracted
from this file.  In the 2014-23 workbook these KPIs are stored as rounded
integers at firm level (e.g. P8=11 instead of 11.07).  Reconstructing
them from full-precision raw items (see script 03) eliminates the
measurement error that would otherwise bias Model 2 coefficient estimates.

OUTPUT
------
  Extracted Data/01_raw_firm_panel_old.csv
    One row per (firm_id, fiscal_year).
    ~4,330 rows  (433 firms x 10 years, unbalanced — firms with fewer
    than 10 years produce fewer rows).

Reference: FirmLevel_DataStrategy.docx; Gormsen & Huber (2024, 2025).
"""

import os
import sys
import re
import pandas as pd

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
if CODES_DIR not in sys.path:
    sys.path.insert(0, CODES_DIR)

from utils import normalize_item, parse_num

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SOURCE_FILE = os.path.join(
    os.path.dirname(CODES_DIR), "Source Data", "2005-23.xlsx"
)
OUTPUT_FILE = os.path.join(
    os.path.dirname(CODES_DIR), "Extracted Data", "01_raw_firm_panel_old.csv"
)

SHEET_NAME = "2014-23"

# Year column positions (0-based): col 4 = 2014, col 13 = 2023
YEAR_COLUMNS = {
    "2014":  4, "2015":  5, "2016":  6, "2017":  7, "2018":  8,
    "2019":  9, "2020": 10, "2021": 11, "2022": 12, "2023": 13,
}

# ---------------------------------------------------------------------------
# Row identification patterns
# ---------------------------------------------------------------------------
# 6-digit code at the start of Org Name identifies an individual firm
FIRM_PATTERN    = re.compile(r'^\d{6}\s*-')
# 3-digit code identifies a sector or sub-sector aggregate  -> skip
SECTOR_PATTERN  = re.compile(r'^\d{3}\s*-')

# ---------------------------------------------------------------------------
# Items to extract  (exact label text after stripping whitespace)
#
# NOTE: P8_precomp / S1_precomp / S4_precomp are deliberately excluded.
#       In the 2014-23 file these are integer-rounded at firm level.
#       They are reconstructed from raw items in script 03.
# ---------------------------------------------------------------------------
ITEM_LABELS = {
    # ---- Balance sheet: assets ----
    "OFA_cost":            "2. Operating fixed assets at cost",

    # ---- Balance sheet: equity & liabilities ----
    "ShareholdersEquity_C": "C. Shareholders' Equity (C1+C2+C3)",
    "D_NCL":               "D. Non-Current Liabilities (D1+D2+D3+D4+D5)",
    "E_CL":                "E. Current Liabilities (E1+E2+E3+E4)",
    "TotalAssets":         "Total Assets (A+B) / Equity & Liabilities (C+D+E)",

    # ---- Income statement ----
    "EBIT":                "6. EBIT (F3-F4+F5)",
    "Sales":               "1. Sales",

    # ---- Financial expenses: sub-item only (NOT the F.7 aggregate) ----
    "InterestExpense":     "of which: (i) Interest expenses",

    # ---- H. Miscellaneous ----
    "CapEmployed":         "1. Total capital employed (C+D)",
    "Retention":           "2. Retention in business (F10-F11-F12)",
    "Depreciation":        "3. Depreciation for the year",
}


# ---------------------------------------------------------------------------
# Step 1 — Load sheet
# ---------------------------------------------------------------------------

def load_sheet(source_path: str) -> pd.DataFrame:
    """
    Read the 2014-23 sheet into a raw DataFrame with positional column indices.

    Args:
        source_path: Absolute path to 2005-23.xlsx.

    Returns:
        DataFrame; rows 0+ are data (row 0 = header row, skipped in parsing).
    """
    print(f"Loading '{SHEET_NAME}' from:\n  {source_path}")
    df = pd.read_excel(source_path, sheet_name=SHEET_NAME, header=None)
    print(f"  Sheet dimensions: {df.shape[0]:,} rows x {df.shape[1]} columns")
    return df


# ---------------------------------------------------------------------------
# Step 2 — Parse firm rows into nested dict
# ---------------------------------------------------------------------------

def parse_firm_data(df: pd.DataFrame) -> tuple:
    """
    Iterate over every row and collect data for individual firm rows only.

    Builds a nested dict:
        firm_id  ->  item_label  ->  year_str  ->  float_or_None

    Also captures Sector and Sub-Sector metadata per firm for downstream
    use as grouping variables in robustness checks.

    Args:
        df: Raw DataFrame from load_sheet().

    Returns:
        Tuple of:
          data          {firm_id: {norm_item: {year: value}}}
          firm_meta     {firm_id: {'sector': str, 'subsector': str}}
          ordered_firms list of firm_ids in order of first appearance
    """
    data          = {}
    firm_meta     = {}
    ordered_firms = []

    skipped_sector = 0
    skipped_other  = 0
    rows_kept      = 0

    for _, row in df.iloc[1:].iterrows():   # skip row 0 (header)
        org_raw  = row[2]
        item_raw = row[3]

        if pd.isna(org_raw) or pd.isna(item_raw):
            continue

        org_str  = str(org_raw).strip()
        item_str = normalize_item(item_raw)

        if not org_str or not item_str:
            continue

        # Sector aggregate or sub-aggregate -> skip
        if SECTOR_PATTERN.match(org_str):
            skipped_sector += 1
            continue

        # Not a 6-digit firm code -> header or unrecognised row -> skip
        if not FIRM_PATTERN.match(org_str):
            skipped_other += 1
            continue

        # --- firm row ---
        firm_id = org_str   # e.g. "380002 - Attock Cement Pakistan Ltd."

        if firm_id not in data:
            data[firm_id]      = {}
            ordered_firms.append(firm_id)
            firm_meta[firm_id] = {
                "sector":    str(row[0]).strip() if pd.notna(row[0]) else "",
                "subsector": str(row[1]).strip() if pd.notna(row[1]) else "",
            }

        # Parse year columns
        year_vals = {}
        for yr, col in YEAR_COLUMNS.items():
            cell = row[col] if col < len(row) else None
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                year_vals[yr] = None
            elif isinstance(cell, (int, float)):
                year_vals[yr] = float(cell)
            else:
                year_vals[yr] = parse_num(cell)

        data[firm_id][item_str] = year_vals
        rows_kept += 1

    print(f"  Rows parsed: kept={rows_kept:,}  "
          f"skipped(sector agg)={skipped_sector:,}  "
          f"skipped(other)={skipped_other:,}")
    print(f"  Unique firms identified: {len(ordered_firms):,}")
    return data, firm_meta, ordered_firms


# ---------------------------------------------------------------------------
# Step 3 — Reshape to long format
# ---------------------------------------------------------------------------

def reshape_to_long(data: dict,
                    firm_meta: dict,
                    ordered_firms: list) -> pd.DataFrame:
    """
    Convert the nested dict to a tidy long-format DataFrame:
    one row per (firm_id, fiscal_year), one column per extracted item.

    Firm-years where the firm has no data at all for a given year are
    included as NaN rows — the firm was in the file but not that year.
    Firm-years where the firm never appeared in the sheet are simply absent.

    Args:
        data:          Nested dict from parse_firm_data().
        firm_meta:     Sector/sub-sector metadata per firm.
        ordered_firms: Ordered list of firm IDs.

    Returns:
        Long-format DataFrame.
    """
    records = []

    for firm_id in ordered_firms:
        meta     = firm_meta[firm_id]
        item_map = data[firm_id]

        # Determine which years this firm actually has data for
        # A firm is present in a year if ANY item has a non-None value
        years_with_data = set()
        for item_dict in item_map.values():
            for yr, val in item_dict.items():
                if val is not None:
                    years_with_data.add(yr)

        for yr in YEAR_COLUMNS:
            if yr not in years_with_data:
                continue   # firm not present in this year -> omit row

            rec = {
                "firm_id":     firm_id,
                "sector":      meta["sector"],
                "subsector":   meta["subsector"],
                "fiscal_year": int(yr),
                "source_file": "FSA_2005-23",
            }

            for var, label in ITEM_LABELS.items():
                val         = None
                norm_label  = normalize_item(label)
                label_lower = norm_label.lower()

                # Exact match first
                if norm_label in item_map:
                    val = item_map[norm_label].get(yr)

                # Substring fallback (handles bracket-notation variants)
                if val is None:
                    for stored, year_dict in item_map.items():
                        if label_lower in stored.lower():
                            v = year_dict.get(yr)
                            if v is not None:
                                val = v
                                break

                rec[var] = val

            records.append(rec)

    id_cols  = ["firm_id", "sector", "subsector", "fiscal_year", "source_file"]
    var_cols = list(ITEM_LABELS.keys())
    df = pd.DataFrame(records)[id_cols + var_cols]

    # Panel shape summary
    n_firms = df["firm_id"].nunique()
    n_obs   = len(df)
    yr_counts = df.groupby("firm_id")["fiscal_year"].count()
    n_balanced = (yr_counts == 10).sum()
    print(f"\nLong-format panel: {n_obs:,} firm-year rows")
    print(f"  Unique firms: {n_firms:,}")
    print(f"  Firms with all 10 years (balanced): {n_balanced:,}")
    print(f"  Fiscal years: {sorted(df['fiscal_year'].unique())}")
    return df


# ---------------------------------------------------------------------------
# Step 4 — Completeness check on core variables
# ---------------------------------------------------------------------------

def validate_extraction(df: pd.DataFrame) -> None:
    """
    Print non-null rates for the core items that drive variable construction.
    A rate below 90% for OFA_cost, InterestExpense, D_NCL, E_CL, or
    TotalAssets warrants investigation before proceeding to script 03.

    Args:
        df: Long-format DataFrame from reshape_to_long().
    """
    print("\n--- Extraction completeness ---")
    total = len(df)
    core  = ["OFA_cost", "InterestExpense", "D_NCL", "E_CL",
             "TotalAssets", "EBIT", "ShareholdersEquity_C",
             "Sales", "CapEmployed", "Retention"]
    for var in core:
        n   = df[var].notna().sum()
        pct = 100 * n / total if total else 0
        flag = "  *** CHECK" if pct < 90 else ""
        print(f"  {var:<25s}: {n:>6,}/{total:,}  ({pct:5.1f}%){flag}")

    # Zero-interest firms: valid observations but form a distinct sub-group
    n_zero = (df["InterestExpense"] == 0).sum()
    n_nonz = (df["InterestExpense"].notna() & (df["InterestExpense"] > 0)).sum()
    print(f"\n  InterestExpense == 0  : {n_zero:>6,} firm-year obs  "
          f"(zero-debt; valid but flagged in script 03)")
    print(f"  InterestExpense  > 0  : {n_nonz:>6,} firm-year obs  "
          f"(debt-carrying; primary identification sample)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(source_path: str = SOURCE_FILE,
        output_path: str = OUTPUT_FILE) -> pd.DataFrame:
    """
    Execute the full firm-level extraction for the 2005-23 workbook.

    Steps:
      1. Load the 2014-23 sheet.
      2. Filter to 6-digit firm rows; parse into nested dict.
      3. Reshape to long format (one row per firm-year).
      4. Validate completeness.
      5. Save to CSV.

    Args:
        source_path: Path to 2005-23.xlsx.
        output_path: Destination CSV path.

    Returns:
        Long-format firm-year DataFrame.
    """
    print("=" * 65)
    print("Script 01 -- Extract firm-level panel from FSA 2005-23")
    print("=" * 65)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df_raw               = load_sheet(source_path)
    data, meta, firms    = parse_firm_data(df_raw)
    df_long              = reshape_to_long(data, meta, firms)
    validate_extraction(df_long)

    df_long.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved -> {output_path}")
    return df_long


if __name__ == "__main__":
    run()
