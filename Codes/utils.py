"""
utils.py
========
Shared helper functions for the Perceived Cost of Capital data pipeline.

All modules in this project import from here to ensure consistent
string normalisation, numeric parsing, and safe arithmetic throughout.

Reference: Gormsen & Huber (2024, 2025) — perceived cost of capital.
Data source: State Bank of Pakistan FSA publications.
"""

import re
import pandas as pd


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def normalize_item(s) -> str:
    """
    Strip leading/trailing whitespace and collapse all internal whitespace
    sequences to a single space.

    The SBP workbooks indent sub-items with leading spaces (e.g.
    "    2. Operating fixed assets at cost").  After normalisation the
    leading spaces are removed, so label matching works without knowing
    the exact indentation used in each sheet.

    Args:
        s: Raw cell value (string, numeric, or NaN).

    Returns:
        Clean single-space-normalised string, or "" for NaN / None.
    """
    if pd.isna(s):
        return ""
    return re.sub(r'\s+', ' ', str(s)).strip()


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

def parse_num(s):
    """
    Convert a raw cell value to float, handling:
      - Comma-separated thousands (e.g. "1,234,567")
      - Percentage symbols (divides by 100)
      - Parenthesised negatives used in some SBP cells (e.g. "(5,432)")
      - Dash / N/A / blank -> None

    Args:
        s: Raw string or numeric cell value.

    Returns:
        float, or None if the value cannot be parsed or is explicitly missing.
    """
    if pd.isna(s):
        return None
    t = str(s).strip()
    if t in ("-", "N/A", "n/a", ""):
        return None

    negative = False
    if t.startswith('(') and t.endswith(')'):
        negative = True
        t = t[1:-1].strip()

    is_percent = '%' in t
    t = t.replace(',', '').replace('%', '')

    try:
        value = float(t)
        if negative:
            value = -value
        if is_percent:
            value /= 100.0
        return value
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Safe arithmetic
# ---------------------------------------------------------------------------

def safe_div(numerator, denominator):
    """
    Divide numerator by denominator, returning None instead of raising
    ZeroDivisionError or propagating NaN.

    Args:
        numerator:   Dividend (float or None).
        denominator: Divisor  (float or None).

    Returns:
        float ratio, or None when either input is invalid or denominator is 0.
    """
    if numerator is None or denominator is None:
        return None
    if pd.isna(numerator) or pd.isna(denominator):
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def safe_add(*args):
    """
    Sum all non-None, non-NaN values from the argument list.

    Useful when one component may be missing for some sector-years
    (e.g. a sector reports zero long-term liabilities and the cell is blank).

    Args:
        *args: Any mix of float values, None, or NaN.

    Returns:
        float sum of valid values, or None if no valid values are present.
    """
    valid = [a for a in args if a is not None and not pd.isna(a)]
    if not valid:
        return None
    return sum(valid)


# ---------------------------------------------------------------------------
# Item-value lookup
# ---------------------------------------------------------------------------

def get_item_year_value(company_map: dict, item_names, year: str):
    """
    Retrieve the value of a financial statement item for a given year.

    The SBP workbooks sometimes change bracket notations across sheets
    (e.g. "D. Non-Current Liabilities (D1+D2)" vs "D. Non-Current
    Liabilities (D1+D2+D3+D4+D5)").  This function first tries an exact
    match, then falls back to a case-insensitive containment check so
    that the shorter canonical label matches the longer versioned label.

    Args:
        company_map: Nested dict {normalised_item_label: {year_str: value}}
                     for a single entity (sector or firm).
        item_names:  A single string label or a list of candidate labels,
                     in order of preference.
        year:        Year column string (e.g. "2015", "FY22").

    Returns:
        float value, or None if the item / year combination is not found.
    """
    if isinstance(item_names, str):
        item_names = [item_names]

    # Pass 1: exact match (fastest, covers most cases)
    for name in item_names:
        if name in company_map:
            val = company_map[name].get(year)
            if val is not None:
                return val

    # Pass 2: case-insensitive substring match (handles bracket variants)
    for name in item_names:
        name_lower = str(name).lower()
        for key in company_map:
            if name_lower in str(key).lower():
                val = company_map[key].get(year)
                if val is not None:
                    return val

    return None
