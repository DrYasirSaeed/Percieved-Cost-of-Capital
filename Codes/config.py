"""
config.py
=========
Central configuration: shared constants used across all pipeline scripts.

Import from here to ensure every module uses identical sector code sets,
file paths, and parameter values.
"""

import os

# ---------------------------------------------------------------------------
# Project directory layout
# ---------------------------------------------------------------------------
CODES_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR   = os.path.dirname(CODES_DIR)
SOURCE_DIR    = os.path.join(PROJECT_DIR, "Source Data")
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")

# Source workbooks
FILE_OLD  = os.path.join(SOURCE_DIR, "2005-23.xlsx")
FILE_FY25 = os.path.join(SOURCE_DIR, "FSA_NFC_FY20_FY25.xlsx")

# ---------------------------------------------------------------------------
# Sector code sets
# ---------------------------------------------------------------------------

# 14 sectors used in all estimation models (same in both panels)
ESTIMATION_SECTOR_CODES_OLD = {
    "704",  # Textile (name: 'Textile Sector' in old file)
    "705",  # Coke and Refined Petroleum Products
    "706",  # Chemicals, Chemical Products and Pharmaceuticals
    "707",  # Electrical Machinery and Apparatus
    "709",  # Paper, Paperboard and Products
    "710",  # Fuel and Energy (name: 'Fuel and Energy Sector' in old file)
    "711",  # Information and Communication Services
    "712",  # Manufacturing
    "714",  # Motor Vehicles, Trailers & Autoparts
    "715",  # Other Services Activities
    "726",  # Sugar
    "727",  # Food Products
    "728",  # Mineral products
    "729",  # Cement
}

# Identical set for the FY25 panel (same 14 codes)
ESTIMATION_SECTOR_CODES_FY25 = ESTIMATION_SECTOR_CODES_OLD.copy()

# All Sector aggregate code — for validation / descriptive use only
ALL_SECTOR_CODE = "703"

# Sectors excluded in robustness specifications (§5.3 of extraction guide)
#   710 = Fuel and Energy (regulated pricing distorts ROIC)
#   729 = Cement (extraordinary capacity cycle creates investment volatility)
ROBUSTNESS_EXCLUDE_CODES = {"710", "729"}

# ---------------------------------------------------------------------------
# Winsorisation parameters
# ---------------------------------------------------------------------------
WINS_LOWER_PERCENTILE = 0.01   # 1st  percentile
WINS_UPPER_PERCENTILE = 0.99   # 99th percentile

# Columns winsorised in script 03
WINSORIZE_COLS = ["Inv_Rate_raw", "CoC_Proxy_raw"]

# ---------------------------------------------------------------------------
# Overlap validation threshold
# ---------------------------------------------------------------------------
# Sectors with ALL core-variable discrepancies below this % in FY2020 are
# candidates for an optional unified panel (not default; see guide §5.1)
OVERLAP_THRESHOLD_PCT = 5.0
