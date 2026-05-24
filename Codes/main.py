"""
main.py
=======
Orchestrator for the Perceived Cost of Capital data pipeline.

Run this script to execute all four steps in sequence:

  Step 1 — Extract sector panel from SBP FSA 2005-23 (2014-23 sheet)
  Step 2 — Extract sector panel from SBP FSA NFC FY25
  Step 3 — Compute all research variables (CoC proxy, investment rate, etc.)
  Step 4 — Validate overlap, export model-ready panels

USAGE
-----
  From the Codes directory:
      python main.py

  Or run individual scripts for a single step:
      python 01_extract_sector_panel_old.py
      python 02_extract_sector_panel_fy25.py
      python 03_compute_variables.py
      python 04_merge_validate.py

PREREQUISITES
-------------
  pip install -r requirements.txt

  Source files must be present:
    Source Data/2005-23.xlsx
    Source Data/FSA_NFC_FY20_FY25.xlsx

OUTPUT FILES
------------
All outputs are written to the 'Extracted Data/' folder:

  01_raw_sector_panel_old.csv   — Raw extracted values, old file
  02_raw_sector_panel_fy25.csv  — Raw extracted values, FY25 file
  03_panel_old_computed.csv     — Old file + all computed variables
  04_panel_fy25_computed.csv    — FY25 file + all computed variables
  05_model_ready_old.csv        — Estimation panel (14 sectors, old file)
  06_model_ready_fy25.csv       — Validation panel (14 sectors, FY25)
  07_overlap_comparison.csv     — FY2020-FY2023 discrepancy table
  08_allsector_validation.csv   — All Sector aggregate from both files

NEXT STEPS AFTER RUNNING
-------------------------
  1. Open 05_model_ready_old.csv and 06_model_ready_fy25.csv.
  2. Fill in the r_SBP column with annual average SBP policy rates
     (computed on a Jul-Jun fiscal year basis from SBP Monetary Policy History).
  3. Fill in the CPI_inflation column (Pakistan Bureau of Statistics or IMF IFS).
  4. The delta_r_SBP, Interaction, and Real_CoC formula columns will
     auto-populate on the next pipeline run once those columns are filled.
  5. Run regression scripts (Models 1, 2, 3) on the model-ready panels.

Reference: Gormsen & Huber (2024, 2025).
"""

import os
import sys
import time
import subprocess

CODES_DIR = os.path.dirname(os.path.abspath(__file__))

# Pipeline scripts, in execution order
PIPELINE_STEPS = [
    ("Step 1 — Extract old panel (2014-23 sheet)",
     "01_extract_sector_panel_old.py"),
    ("Step 2 — Extract FY25 panel",
     "02_extract_sector_panel_fy25.py"),
    ("Step 3 — Compute research variables",
     "03_compute_variables.py"),
    ("Step 4 — Validate overlap, export model-ready panels",
     "04_merge_validate.py"),
]


def run_step(label: str, script_filename: str) -> bool:
    """
    Run one pipeline script as a subprocess and stream its output.

    Args:
        label:           Human-readable step description.
        script_filename: Filename of the script (in the Codes directory).

    Returns:
        True if the script exited with code 0, False otherwise.
    """
    print(f"\n{'─' * 65}")
    print(f"  {label}")
    print(f"{'─' * 65}")

    script_path = os.path.join(CODES_DIR, script_filename)
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=CODES_DIR,
    )
    if result.returncode != 0:
        print(f"\n  ERROR: {script_filename} exited with code {result.returncode}")
        return False
    return True


def main():
    """
    Execute all pipeline steps sequentially and report elapsed time.
    Halts on the first step that fails.
    """
    print("\n" + "=" * 65)
    print("  Perceived Cost of Capital — Data Extraction Pipeline")
    print("  Reference: Gormsen & Huber (2024, 2025)")
    print("=" * 65)

    t0 = time.time()

    for label, script in PIPELINE_STEPS:
        success = run_step(label, script)
        if not success:
            print(f"\nPipeline aborted at: {script}")
            sys.exit(1)

    elapsed = time.time() - t0
    print(f"\n{'=' * 65}")
    print(f"Pipeline complete in {elapsed:.1f} seconds.")
    print(f"{'=' * 65}")

    # Verify output files exist
    project_dir = os.path.dirname(CODES_DIR)
    ext_dir = os.path.join(project_dir, "Extracted Data")
    print("\nKey output files:")
    for fname in [
        "01_raw_sector_panel_old.csv",
        "02_raw_sector_panel_fy25.csv",
        "05_model_ready_old.csv",
        "06_model_ready_fy25.csv",
        "07_overlap_comparison.csv",
        "08_allsector_validation.csv",
    ]:
        full = os.path.join(ext_dir, fname)
        status = "OK     " if os.path.isfile(full) else "MISSING"
        print(f"  [{status}] {fname}")


if __name__ == "__main__":
    main()
