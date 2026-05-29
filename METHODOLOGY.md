# Data Curation Methodology
## Perceived Cost of Capital in Pakistan — Firm-Level Panel Construction

**Project:** Perceived Cost of Capital and Corporate Investment in Pakistan  
**Reference framework:** Gormsen & Huber (2024, 2025)  
**Data sources:** State Bank of Pakistan — Financial Statements Analysis (FSA) of Non-Financial Companies  
**Last updated:** May 2026

---

## Table of Contents

1. [Research Design Overview](#1-research-design-overview)
2. [Data Sources](#2-data-sources)
3. [Firm Identification](#3-firm-identification)
4. [Items Extracted](#4-items-extracted)
5. [KPI Precision and Reconstruction](#5-kpi-precision-and-reconstruction)
6. [Variable Construction](#6-variable-construction)
7. [Winsorisation](#7-winsorisation)
8. [Two-Panel Strategy](#8-two-panel-strategy)
9. [Overlap Validation](#9-overlap-validation)
10. [Exclusion of Restructuring and M&A-Affected Firms](#10-exclusion-of-restructuring-and-ma-affected-firms)
11. [Stitched Merged Panel](#11-stitched-merged-panel)
12. [Sample Flag Definitions](#12-sample-flag-definitions)
13. [External Placeholders](#13-external-placeholders)
14. [Pipeline Summary and Output Files](#14-pipeline-summary-and-output-files)
15. [Limitations and Caveats](#15-limitations-and-caveats)

---

## 1. Research Design Overview

This project constructs a firm-year panel of Pakistani listed non-financial companies to test whether the **perceived cost of capital** — measured by the realised cost of debt — influences corporate investment decisions, following the methodology of Gormsen and Huber (2024, 2025). The theoretical prior is that even firms with access to investment-grade financing respond to changes in their observed financing costs when forming expectations about future project returns.

The empirical strategy requires:

- A **primary estimation panel** covering a long horizon (FY2014–FY2023) for the main regression specifications.
- An **independent out-of-sample validation panel** (FY2020–FY2025) from a separately published data vintage to test whether findings replicate under revised financial data and an extended time horizon.
- A **stitched merged panel** (FY2015–FY2025) for specifications that require the longest possible time series, with explicit controls for the source-file break.

All three panels are constructed from the same two SBP FSA publications but are used independently to prevent look-ahead bias and cross-contamination.

---

## 2. Data Sources

### 2.1 FSA 2005–23 Workbook (`2005-23.xlsx`)

| Attribute | Detail |
|---|---|
| Publisher | State Bank of Pakistan, Statistics and Data Warehouse Department |
| Full title | Financial Statements Analysis of Companies (Non-Financial) Listed on Pakistan Stock Exchange |
| Coverage | FY2005–FY2023; panel extracted from the `2014-23` sheet only |
| Sheet scope | FY2014–FY2023 (ten fiscal years) |
| Unit of observation | Individual listed company × fiscal year |
| Data type | Balance sheet and income statement items, plus pre-computed KPIs |

**Why only the `2014-23` sheet?** Earlier sheets (e.g. `2005-08`, `2009-13`) use different item numbering, different aggregation hierarchies, and inconsistent sub-item definitions. Pooling across sheets would introduce structural breaks that cannot be controlled for without hand-mapping each item individually. The `2014-23` sheet is the longest internally consistent slice available.

### 2.2 FSA NFC FY25 Workbook (`FSA_NFC_FY20_FY25.xlsx`)

| Attribute | Detail |
|---|---|
| Publisher | State Bank of Pakistan |
| Coverage | FY2020–FY2025 (six fiscal years) |
| Sheet used | `FSA_NFCs_FY25` |
| Unit of observation | Individual listed company × fiscal year |
| Additional column | Financial Year End (FYE) month — not present in the 2005-23 file |

This file is a fresh publication vintage covering an overlapping but non-identical firm sample, with revised financial figures for FY2020–FY2023. The FY2024 and FY2025 years extend beyond anything available in the old file.

---

## 3. Firm Identification

Both workbooks mix **individual firm rows** and **sector aggregate rows** in the same sheet. The sector aggregates are not observations to be used in firm-level regressions — they are pre-computed totals. Confusing the two would produce a severely biased sample (sector totals have asset bases orders of magnitude larger than individual firms and do not represent independent economic units).

### 3.1 Old File (`2014-23` sheet)

**Rule:** The Sector/Organisation Name column (column index 2, 0-based) carries a numeric prefix code:

| Code format | Meaning | Action |
|---|---|---|
| 6-digit code (e.g. `380002 - Attock Cement Pakistan Ltd.`) | Individual listed company | **KEEP** |
| 3-digit code (e.g. `704 - Textile`) | Sector or sub-sector aggregate | **SKIP** |
| No numeric code | Header row or blank | **SKIP** |

This rule is implemented via two compiled regular expressions:

```python
FIRM_PATTERN   = re.compile(r'^\d{6}\s*-')   # matches individual firms
SECTOR_PATTERN = re.compile(r'^\d{3}\s*-')   # matches sector aggregates
```

Of 61,831 raw sheet rows, 59,400 are firm rows (kept) and 2,430 are sector aggregate rows (skipped), yielding **433 unique firms** over FY2014–FY2023.

### 3.2 FY25 File (`FSA_NFCs_FY25` sheet)

The FY25 publication uses a different layout: companies no longer carry numeric code prefixes. The identification rule changes to:

**Rule:** A row is an individual firm if and only if the Organisation Name column (col 3) **differs** from the Sectors column (col 0). Sector aggregates have identical values in both columns.

A secondary confirmation is available: the Financial Year End (FYE) column (col 4) carries a value (`Jun`, `Sep`, `Dec`, `Mar`) for firm rows and is blank for sector aggregate rows.

A fixed exclusion set of 15 known sector aggregate names provides an additional safeguard:

```
"All Sector", "Textile", "Coke and Refined Petroleum Products",
"Chemicals, Chemical Products and Pharmaceuticals", ...
```

Of 56,994 data rows, 54,937 are firm rows (kept) and 2,055 are skipped, yielding **393 unique firms** over FY2020–FY2025.

---

## 4. Items Extracted

The following items are extracted from both files. Exact label strings are matched using a `normalize_item()` helper that strips leading/trailing whitespace and collapses internal whitespace to a single space — necessary because SBP uses variable indentation in the Item Name column to signal hierarchy.

| Variable name | SBP item label | Economic content |
|---|---|---|
| `OFA_cost` | `2. Operating fixed assets at cost` | Gross fixed assets at historical cost |
| `ShareholdersEquity_C` | `C. Shareholders' Equity (C1+C2+C3)` | Book equity |
| `D_NCL` | `D. Non-Current Liabilities (D1+D2+D3+D4+D5)` | Long-term debt |
| `E_CL` | `E. Current Liabilities (E1+E2+E3+E4)` | Short-term debt and payables |
| `TotalAssets` | `Total Assets (A+B) / Equity & Liabilities (C+D+E)` | Balance sheet total |
| `EBIT` | `6. EBIT (F3-F4+F5)` | Earnings before interest and tax |
| `Sales` | `1. Sales` | Net revenue |
| `InterestExpense` | `of which: (i) Interest expenses` | Financial charges on debt |
| `CapEmployed` | `1. Total capital employed (C+D)` | Equity plus long-term debt |
| `Retention` | `2. Retention in business (F10-F11-F12)` (old) / `(F12-F13-F14)` (FY25) | Retained earnings for the year |
| `Depreciation` | `3. Depreciation for the year` | Annual depreciation charge |

**Note on `Retention` label change:** In the FY25 file, SBP inserted a `Levies` line item at position F9, shifting the Retention formula reference from `F10-F11-F12` to `F12-F13-F14`. The economic content is identical. The extraction code matches on the label suffix (`Retention in business`) to handle both variants.

**Additional items in FY25 file only (full-precision KPIs):**

| Variable name | SBP KPI label |
|---|---|
| `P8_precomp` | `P8. Return on capital employed` |
| `S1_precomp` | `S1. Debt equity ratio [(D+E) to C]` |
| `S4_precomp` | `S4. Interest cover ratio (F6 to F7(i))` |

These KPIs are extracted from the FY25 file because they are stored at full floating-point precision there (see Section 5).

---

## 5. KPI Precision and Reconstruction

### 5.1 The Integer-Rounding Problem in the Old File

A critical data quality issue affects the 2005-23 workbook: **pre-computed KPIs (P8, S1, S4) are stored as rounded integers at the individual firm level**. For example, a firm with a true ROIC of 11.07% appears as `P8 = 11`. This integer rounding injects measurement error of up to ±0.5 percentage points per observation.

If the rounded KPI were used directly as a dependent variable in Models 1 or 2, the rounding error would appear in the regression residual and could attenuate coefficient estimates (classical measurement error in the dependent variable does not bias OLS but inflates standard errors; measurement error in an independent variable — relevant if P8 appears as a control — does bias coefficients toward zero). To eliminate both risks entirely, all KPIs are **reconstructed from the underlying full-precision raw balance sheet items**.

### 5.2 Reconstruction Formulas

**P8 — Return on Capital Employed (ROIC):**

$$\text{P8\_ROIC}_t = \frac{\text{EBIT}_t}{(\text{CapEmployed}_t + \text{CapEmployed}_{t-1}) / 2}$$

Capital Employed is averaged over the current and prior year because ROIC measures the return generated on the stock of capital deployed during the year, not just the end-of-year balance.

**S1 — Debt-Equity Ratio:**

$$\text{S1\_Leverage}_t = \frac{\text{D\_NCL}_t + \text{E\_CL}_t}{\text{ShareholdersEquity\_C}_t}$$

This is the reason `ShareholdersEquity_C` is extracted from the old file — it is not needed for the core CoC proxy computation but is required to reconstruct S1 at full precision.

### 5.3 FY25 File: Direct KPI Use

In the FY25 publication, KPIs are stored at full floating-point precision (e.g. P8 = 11.07 rather than 11). Reconstruction is therefore unnecessary. P8 is used as:

$$\text{P8\_ROIC} = \text{P8\_precomp} / 100$$

(Converting the KPI from percentage to proportion for consistency with the reconstructed values in the old file.)

---

## 6. Variable Construction

All variables are computed within the `03_compute_variables.py` script. Lag operations use `groupby("firm_id").shift()` to ensure lags never cross firm boundaries — a firm's FY2014 observation does not contribute to another firm's FY2015 lag.

### 6.1 Investment Rate

$$\text{Inv\_Rate}_t = \frac{\text{OFA\_cost}_t - \text{OFA\_cost}_{t-1}}{\text{TotalAssets}_{t-1}}$$

**Rationale:** Gross fixed assets at cost (OFA_cost) captures new capital expenditure net of disposals at cost, avoiding the depreciation-induced mechanical decline in net assets. Scaling by lagged total assets normalises for firm size and follows the standard investment regression literature (Bond & Van Reenen 2007). The FY2014 observations serve as the base year for computing FY2015 first differences; FY2014 rows are dropped from the estimation panel because they contain no computed `Inv_Rate`.

### 6.2 Cost of Capital Proxy

$$\text{CoC\_Proxy}_t = \frac{\text{InterestExpense}_t}{\text{D\_NCL}_t + \text{E\_CL}_t}$$

**Rationale:** This is the Gormsen-Huber (2024) perceived cost of debt: the actual interest paid divided by the stock of interest-bearing debt outstanding. It measures what firms *actually experienced* as their financing cost in a given year — their perceived cost of capital — rather than the risk-free rate or a market-implied spread. Unlike market-based proxies (e.g. bond yields), this measure is available for all listed firms regardless of whether they have publicly traded debt.

**Zero-debt firms:** When `D_NCL + E_CL = 0`, the proxy is undefined and set to `NaN`. These observations are retained in the dataset but flagged via `zero_interest = True`. Robustness checks that restrict to debt-carrying firms apply `zero_interest == False`.

### 6.3 Size

$$\text{Size\_ln}_t = \ln(\text{TotalAssets}_t)$$

Clipped at a lower bound of 1 before taking the log to prevent undefined values for the single observation (Shakarganj Food Ltd., FY2014) where total assets are recorded as zero. Log total assets is the standard size control in investment regressions (Fazzari, Hubbard & Petersen 1988).

### 6.4 Cash Flow

$$\text{Cashflow}_t = \frac{\text{Retention}_t}{\text{TotalAssets}_t}$$

Set to `NaN` when `TotalAssets = 0` (zero-guard applied). Cash flow is included as a control for internal financing capacity; its coefficient in the investment equation has been debated as a test for financing constraints (Kaplan & Zingales 1997).

**Note on extreme values:** A small number of firms with anomalously tiny asset bases (e.g. Zahur Cotton Mills FY2022, TotalAssets = PKR 93m, Retention = PKR 40.7bn) produce Cashflow values exceeding 400 in the raw data. These are data anomalies — likely unreported asset transfers or classification errors — not valid economic observations. `Cashflow` is therefore winsorised at the 1st/99th percentile alongside the main research variables (see Section 7).

### 6.5 Depreciation Rate

$$\text{DepRate}_t = \frac{\text{Depreciation}_t}{\text{TotalAssets}_t}$$

Same zero-guard as Cashflow. Depreciation rate proxies for the rate of capital obsolescence and therefore the minimum investment required to maintain the existing capital stock. Raw values reach +11.9 in the tails (firms with near-zero assets) and are winsorised at 1st/99th percentile (see Section 7).

### 6.6 Sales Growth

$$\text{SalesGrowth}_t = \frac{\text{Sales}_t - \text{Sales}_{t-1}}{\text{Sales}_{t-1}}$$

Set to `NaN` when `Sales_{t-1} ≤ 0` (zero or negative lagged sales do not produce economically meaningful growth rates). Sales growth is included as an accelerator-type demand variable.

### 6.7 CoC Proxy Lags

```
CoC_Proxy_L1 = within-firm one-year lag of CoC_Proxy
CoC_Proxy_L2 = within-firm two-year lag of CoC_Proxy
```

Lagged CoC is used in Model 3 to address potential reverse causality: current investment may affect current financing costs through the demand for credit, but it cannot affect last year's realised cost of debt.

### 6.8 External Policy Variables

| Column | Content | Source |
|---|---|---|
| `r_SBP` | SBP policy rate, Jul–Jun fiscal year annual average (%) | SBP Monetary Policy History |
| `CPI_inflation` | Annual CPI inflation rate (%) | Pakistan Bureau of Statistics / IMF IFS |
| `r_SBP_L1` | Prior-year policy rate — year-level calendar shift (%) | Derived |
| `delta_r_SBP` | `r_SBP − r_SBP_L1`, change in policy rate (pp) | Derived |
| `Interaction` | `CoC_Proxy × delta_r_SBP` | Derived |
| `Real_CoC` | `CoC_Proxy − CPI_inflation/100` | Derived |

**FY2014–FY2025 values are now populated** from `Extracted Data/10_external_macro_data.csv`, a hand-compiled file tracked in the repository. This file must be updated if the panel is extended beyond FY2025.

**Implementation note:** `r_SBP_L1` is computed as a **year-level calendar shift** of the macro series (not a `groupby("firm_id").shift()` operation). This matters for an unbalanced panel: a within-firm shift would assign the FY2021 rate as the "FY2023 lag" for any firm missing FY2022, whereas a calendar shift always maps fiscal year *t* to the correct rate from year *t*−1 regardless of gaps in firm coverage.

The macro series exhibits substantial variation across the panel period:

| Year | r_SBP (%) | CPI (%) | delta_r_SBP (pp) | Real rate (pp) |
|---|---|---|---|---|
| FY2015 | 9.03 | 4.53 | −0.68 | +4.50 |
| FY2017 | 5.75 | 4.16 | −0.77 | +1.59 |
| FY2019 | 9.57 | 6.74 | +3.67 | +2.83 |
| FY2021 | 7.00 | 9.50 | −5.05 | −2.50 |
| FY2023 | 17.22 | 30.77 | +7.84 | −13.55 |
| FY2024 | 21.92 | 26.00 | +4.70 | −4.08 |
| FY2025 | 15.11 | 4.49 | −6.81 | +10.62 |

The large swings in `delta_r_SBP` (range: −6.81 to +7.84 pp) provide the primary identification variation for Models 1–3.

---

## 7. Winsorisation

Continuous variables are winsorised at the **1st and 99th percentiles computed over the full panel** (not year-by-year or firm-by-firm) using `pandas.DataFrame.clip()`. Pre-winsorisation values are preserved in `_raw` suffix columns.

**Why panel-wide winsorisation rather than year-by-year?** Year-by-year winsorisation would distort cross-year comparisons because the cut-off itself would vary with the business cycle. Panel-wide winsorisation applies a single consistent rule, which is appropriate when the panel is used in a pooled regression with time fixed effects.

**All seven variables winsorised and their post-winsorisation bounds (old file, FY2014–2023):**

| Variable | Raw min | Raw max | p1 bound | p99 bound | Obs clipped | Rationale |
|---|---|---|---|---|---|---|
| `Inv_Rate` | −∞ | +∞ | −0.810 | +0.800 | 68 | Asset disposals and large capex spikes |
| `CoC_Proxy` | 0.000 | +∞ | 0.000 | +0.143 | 41 | Distressed firms with tiny debt balances |
| `P8_ROIC` | −160× | +160× | −1.170 | +1.412 | 68 | Firms with near-zero capital employed |
| `S1_Leverage` | −649 | +337 | −20.620 | +43.063 | 76 | Near-zero or negative book equity |
| `SalesGrowth` | −1.000 | +26,100% | −1.000 | +2.777 | 30 | New-entrant base-year denominator effects |
| `Cashflow` | −73.8 | +437.6 | −0.703 | +0.257 | 76 | Asset-base anomalies (see §6.4) |
| `DepRate` | −0.003 | +11.87 | 0.000 | +0.106 | 44 | Near-zero asset denominators |

Pre-winsorisation values are preserved as `<variable>_raw` columns in all output files, allowing researchers to verify the impact of outlier treatment on any specific finding.

**Why is `P8_ROIC` winsorised?** In the old file, a small number of firms with very low capital employed (CapEmployed_avg < PKR 50m) generate mechanically extreme ROIC values. For example, Karim Cotton Mills FY2015 reports EBIT of PKR 2,164m against an average capital employed of PKR 13.5m, producing a raw P8_ROIC of 160× — a data anomaly likely reflecting a restatement or classification error in the balance sheet.

**Why is `S1_Leverage` winsorised?** Firms in financial distress or undergoing restructuring can carry near-zero or negative book equity, producing leverage ratios of −649 to +337 in the raw data.

**Why are `Cashflow` and `DepRate` winsorised?** Both variables use `TotalAssets` as the denominator. A subset of firms report near-zero total assets in isolated years (likely due to unreported asset transfers or classification inconsistencies between the two publication vintages), producing ratios that are economically meaningless. Winsorisation was added after the initial pipeline build when the descriptive statistics revealed Cashflow SD = 8.55 and a maximum of +437.6. After winsorisation, Cashflow SD = 0.13 and DepRate SD = 0.019.

---

## 8. Two-Panel Strategy

### 8.1 Why the Two Panels Must Not Be Pooled Directly

The two SBP publications share four years in common (FY2020–FY2023) but are **not consistent for the same firm-year observations**. SBP revises financial data between publication vintages as companies file amended accounts. For the 373 firms present in both publications over FY2020–FY2023 (1,422 firm-year observations):

- **Median percentage difference** is 0% for most items — the majority of firms are unchanged.
- **But tail discrepancies are extreme**: EBIT differs by up to 43,215%, InterestExpense by up to 17,098%, OFA_cost by up to 10,514%.

Stacking both panels for the overlap years would create **duplicate rows with contradictory values** for the same firm-year. There is no principled method to average or choose between two publication vintages for a given observation.

### 8.2 Panel Roles

| Panel | File | Years | Firms | Role |
|---|---|---|---|---|
| Primary estimation | `05_model_ready_old.csv` | FY2014–FY2023 | 433 | Main regression specifications |
| Out-of-sample validation | `06_model_ready_fy25.csv` | FY2020–FY2025 | 393 | Replicate findings on revised data + 2 new years |
| Stitched merged | `09_merged_panel.csv` | FY2015–FY2025 | 342 | Long-horizon specifications with source-change control |

Estimating on `05_model_ready_old.csv` and replicating on `06_model_ready_fy25.csv` provides a **methodologically clean out-of-sample test**: the two samples use different data vintages, partially different firms, and partially non-overlapping time periods.

---

## 9. Overlap Validation

### 9.1 P8 Reconstruction Check

To verify that the P8 reconstruction from raw items (old file) is internally consistent with the full-precision KPI (FY25 file), we compare the two measures for the 373 firms present in both files over FY2020–FY2023:

| Metric | Value |
|---|---|
| Overlap observations compared | 1,422 (373 firms × ~4 years) |
| Mean absolute difference | **3.194 percentage points** |
| Observations within 0.5 pp tolerance | **77.3%** |

The 3.2 pp mean difference does **not** indicate a reconstruction error. It reflects the systematic revision of financial statements between the two SBP publication vintages. The 77.3% within-tolerance rate for the majority of firms confirms that the reconstruction formula is correct. The tail discrepancies are concentrated in firms whose accounts were materially restated — precisely the firms flagged by the exclusion criterion (Section 10).

### 9.2 Raw Variable Discrepancies

The overlap comparison file (`08_overlap_discrepancy.csv`) documents percentage differences for all eight raw items over FY2020–FY2023. Median differences are 0% across all items (confirming most firms are unrevised), but 75th-percentile and maximum differences are large for some items (notably EBIT and InterestExpense), consistent with selective restatements concentrated in a subset of firms.

---

## 10. Exclusion of Restructuring and M&A-Affected Firms

### 10.1 Rationale

Firms undergoing mergers, acquisitions, demergers, or major corporate restructuring exhibit large and sudden changes in their financial statements that are unrelated to normal operating decisions. Including such observations would:

1. Contaminate the investment rate variable (Inv_Rate) with asset additions arising from acquisition rather than organic capital expenditure.
2. Contaminate the CoC proxy with financing costs arising from acquisition-related debt rather than steady-state borrowing.
3. Produce outlier residuals that may exert undue leverage in panel regressions.

### 10.2 Identification Rule

A firm is classified as restructuring-affected if its **mean absolute P8 discrepancy** across the FY2020–FY2023 overlap period exceeds **2.0 percentage points**:

$$\text{Excluded if } \overline{|P8^{\text{old}}_t - P8^{\text{FY25}}_t|} > 2.0 \text{ pp}$$

This threshold is chosen because:
- A 2 pp difference in ROIC between two publication vintages for the same firm-year is inconsistent with normal minor restatements (which affect the first decimal place) and is instead consistent with a major revision of capital structure, asset base, or earnings.
- The threshold is applied to the **mean** across all overlap years for a given firm, not to individual years, preventing a single anomalous year-end from triggering exclusion.
- The 2 pp cut-off is conservative: it retains 280 of 373 overlap firms (75%) while excluding 93 firms (25%) whose financials show structurally inconsistent reporting across the two publications.

### 10.3 Excluded Firms (Top 10)

| Firm | Mean P8 diff (pp) | Note |
|---|---|---|
| Hascol Petroleum Ltd. | 101.70 | Massive restatement post financial distress |
| Dewan Sugar Mills Ltd. | 60.81 | Restructuring and debt rescheduling |
| Haseeb Waqas Sugar Mills Ltd. | 59.35 | |
| Pakistan International Airlines Corp. | 43.87 | Privatisation-related restructuring |
| Fauji Foods Ltd. (formerly Noon Pakistan) | 34.84 | Brand/entity renaming and restatement |
| Lotte Chemical Pakistan Ltd. | 32.67 | |
| Dadabhoy Construction Tech. Ltd. | 26.97 | |
| Faran Sugar Mills Ltd. | 25.58 | |
| ZIL Ltd. | 23.66 | |
| Abdullah Shah Ghazi Sugar Mills | 22.99 | |

Full exclusion list saved in `excluded_firms.csv`.

---

## 11. Stitched Merged Panel

### 11.1 Construction

The merged panel (`09_merged_panel.csv`) is built by taking:
- **Old file**: FY2015–FY2023 (FY2014 dropped — base year only, no Inv_Rate), after removing 93 excluded firms → 340 firms, 2,543 observations.
- **FY25 extension**: FY2024–FY2025 only (FY2020–FY2023 dropped to prevent overlap duplication), after removing excluded firms → 280 firms, 552 observations.

The two pieces are stacked vertically. No firm appears twice in any single fiscal year.

### 11.2 Lag Recomputation

After stacking, `CoC_Proxy_L1` and `CoC_Proxy_L2` are **recomputed from scratch** over the merged time series using `groupby("firm_id").shift()`. This ensures that for stitched firms (those appearing in both halves), the FY2024 lag correctly references the FY2023 value extracted from the old file rather than using the pre-computed lag from the FY25 panel:

- 264 of 276 FY2024 observations (96%) receive a valid `CoC_Proxy_L1` from the old file's FY2023 row.
- 263 of 276 FY2024 observations (95%) receive a valid `CoC_Proxy_L2` from the old file's FY2022 row.

### 11.3 Panel Composition

| Metric | Value |
|---|---|
| Total observations | 3,095 |
| Unique firms | 342 |
| Fiscal year range | FY2015 – FY2025 |
| Stitched firms (in both halves) | 264 |
| Old-only firms | 62 |
| FY25-only firms | 16 |

### 11.4 Source-Change Control

The binary indicator `post2023` (= 1 for FY2024–FY2025, = 0 otherwise) is included as a control variable in all regressions run on the merged panel. It absorbs any level shift in financial reporting conventions, sample composition, or macroeconomic conditions associated with the transition between the two source files. Without this control, the FY2024–2025 extension might confound the policy rate identification with the source-change shock.

---

## 12. Sample Flag Definitions

The following boolean columns are pre-computed in all model-ready files. In regression scripts, apply these as row filters rather than manually re-deriving conditions.

| Flag column | Definition | Typical use |
|---|---|---|
| `in_model1_sample` | `Inv_Rate` and `CoC_Proxy` both non-null | Main sample for Models 1 and 2 |
| `in_model3_sample` | `in_model1_sample == 1` and `CoC_Proxy_L2` non-null | Model 3 (lagged CoC specification) |
| `balanced_subsample` | Firm present in every year it could appear given its source | Balanced-panel robustness check |
| `zero_interest` | `InterestExpense == 0` | Exclude zero-debt firms |
| `negative_equity` | `ShareholdersEquity_C < 0` | Flag/exclude financially distressed firms |
| `non_june_fye` | FYE month is not June (FY25 panel only) | Exclude Sugar sector Sep-FYE misalignment |
| `robustness_excl` | Sector is Fuel & Energy or Cement | Sector-specific robustness exclusion |
| `post2023` | `fiscal_year >= 2024` | Source-change control (merged panel) |

**On `non_june_fye`:** Pakistan's fiscal year runs July–June, aligned with the SBP policy rate cycle used as the identification variable. Sugar companies report on a September fiscal year. Including them means their FY2024 observation covers October 2023–September 2024, not July 2023–June 2024, so the policy rate averaged over the SBP fiscal year does not map cleanly to the firm's actual financing period. Excluding non-June FYE firms in robustness checks tests whether fiscal year misalignment drives any results.

**On `robustness_excl` (Fuel & Energy and Cement):** These two sectors are capital-intensive but face commodity-price-driven earnings volatility that may dominate the CoC signal. Their exclusion tests whether CoC effects are concentrated in or driven by commodity sectors.

---

## 13. External Macro Data

### 13.1 Status

`r_SBP` and `CPI_inflation` are **fully populated** for FY2014–FY2025 from `Extracted Data/10_external_macro_data.csv`, a hand-compiled file committed to the repository. All derived columns (`r_SBP_L1`, `delta_r_SBP`, `Interaction`, `Real_CoC`) are populated in `09_merged_panel.csv`. If the panel is extended beyond FY2025, add a new row to `10_external_macro_data.csv` and re-run steps 5 and 6 of the pipeline.

### 13.2 Sources and Construction

**`r_SBP` — SBP Policy Rate (%)**
- State Bank of Pakistan target policy rate, averaged over the fiscal year (July 1 – June 30).
- Source: SBP Monetary Policy History — https://www.sbp.org.pk/m_policy/m_policy_rates.asp
- Construction: simple average of the daily policy rate over each fiscal year's 365 days, using the rate-change announcement dates.

**`CPI_inflation` — Annual CPI Inflation (%)**
- Annual headline CPI inflation rate for Pakistan, fiscal year basis.
- Sources: Pakistan Bureau of Statistics (PBS) Consumer Price Index; IMF International Financial Statistics (IFS series PA.P65.CPI.A).

**`r_SBP_L1`** is computed as a year-level calendar shift of the macro series — not a `groupby("firm_id").shift()`. See §6.8 for the rationale.

**`Real_CoC`** = `CoC_Proxy − CPI_inflation/100` converts CPI from percentage to proportion before subtracting, so both operands are in the same decimal units.

---

## 14. Pipeline Summary and Output Files

### Scripts (execute in order)

| Step | Script | Function | Key input | Key output |
|---|---|---|---|---|
| 1 | `01_extract_firm_panel_old.py` | Extract firm panel from 2005-23 workbook | `2005-23.xlsx` | `01_raw_firm_panel_old.csv` |
| 2 | `02_extract_firm_panel_fy25.py` | Extract firm panel from FY25 workbook | `FSA_NFC_FY20_FY25.xlsx` | `02_raw_firm_panel_fy25.csv` |
| 3 | `03_compute_variables.py` | Build all variables; winsorise 7 columns | `01_`, `02_` raw CSVs | `03_`, `04_` computed CSVs |
| 4 | `04_merge_validate.py` | P8 overlap check; export model-ready panels | `03_`, `04_` CSVs | `05_` to `08_` CSVs |
| 5 | `05_build_merged_panel.py` | Exclusion list; stitch panels; recompute lags | `05_`, `06_`, `07_` CSVs + `10_` macro | `excluded_firms.csv`, `09_merged_panel.csv` |
| 6 | `06_descriptive_statistics.py` | 12 descriptive tables + master Excel workbook | `09_merged_panel.csv` | `Results/desc_*.csv`, `Results/descriptive_statistics_master.xlsx` |

Steps 1–5 are orchestrated by `main.py`. Step 6 is run independently: `python 06_descriptive_statistics.py`.

**Note:** After step 5 completes, macro data from `10_external_macro_data.csv` must be merged into `09_merged_panel.csv` before step 6. This is done automatically if `05_build_merged_panel.py` is called with the macro file present; otherwise run the macro-injection snippet documented in the repository README.

### Extracted Data Output Files

| File | Rows | Firms | Description |
|---|---|---|---|
| `01_raw_firm_panel_old.csv` | 3,742 | 433 | Raw extracted items, old file, FY2014–2023 |
| `02_raw_firm_panel_fy25.csv` | 2,188 | 393 | Raw extracted items, FY25 file, FY2020–2025 |
| `03_firm_panel_old_computed.csv` | 3,742 | 433 | Old file + all 7 winsorised variables |
| `04_firm_panel_fy25_computed.csv` | 2,188 | 393 | FY25 file + all 7 winsorised variables |
| `05_model_ready_old.csv` | 3,742 | 433 | **Primary estimation panel**, FY2014–2023 |
| `06_model_ready_fy25.csv` | 2,188 | 393 | **Validation panel**, FY2020–2025 |
| `07_p8_reconstruction_check.csv` | 1,422 | 373 | Per-firm-year P8 comparison (old vs FY25) |
| `08_overlap_discrepancy.csv` | — | 373 | Raw variable % differences in overlap years |
| `10_external_macro_data.csv` | 12 | — | **Hand-compiled macro series** FY2014–2025 (tracked in git) |
| `excluded_firms.csv` | — | 93 | Restructuring/M&A exclusion list |
| `09_merged_panel.csv` | 3,095 | 342 | **Stitched panel with macro**, FY2015–2025 |

### Results Folder — Descriptive Statistics Output

Script `06_descriptive_statistics.py` produces 13 CSV files and one master Excel workbook in `Results/`:

| File | Angle covered |
|---|---|
| `desc_01_full_variable_stats.csv` | Full distribution: N, mean, SD, min, p5–p95, max, skewness, excess kurtosis |
| `desc_02_by_fiscal_year.csv` | Year-by-year means/medians for all core variables + macro |
| `desc_03_by_sector.csv` | Per-sector firm count, obs, year span, % zero-interest, variable means |
| `desc_04_by_size_quartile.csv` | Q1 (Small) to Q4 (Large): investment, CoC, leverage, ROIC by firm size |
| `desc_05_by_debt_status.csv` | Zero-interest vs debt-carrying firms on all dimensions |
| `desc_06a_panel_balance.csv` | Years-per-firm distribution (67.8% of firms have all 11 years) |
| `desc_06b_entry_exit.csv` | Firm entry and exit counts by year |
| `desc_07_sample_flags.csv` | Obs and firm counts for each flag and key intersections |
| `desc_08_correlation.csv` | 11×11 Pearson correlation matrix of core regression variables |
| `desc_09_macro_series.csv` | Year-level macro table with panel mean/median CoC and Inv_Rate |
| `desc_10_sector_year_CoC_heatmap.csv` | 14 × 11 matrix of mean CoC_Proxy by sector and year |
| `desc_11_raw_financials_PKRbn.csv` | Balance sheet scale in PKR billions (TotalAssets through Depreciation) |
| `desc_12_source_comparison.csv` | Old-file vs FY25-extension side-by-side comparison |
| `descriptive_statistics_master.xlsx` | All 13 tables as formatted sheets in one workbook |

### Descriptive Statistics — Merged Panel (post-winsorisation, all 7 variables)

| Variable | N | Mean | SD | p25 | Median | p75 |
|---|---|---|---|---|---|---|
| Inv_Rate | 3,052 | 0.049 | 0.174 | 0.000 | 0.019 | 0.073 |
| CoC_Proxy | 3,095 | 0.035 | 0.036 | 0.001 | 0.029 | 0.055 |
| P8_ROIC | 3,060 | 0.112 | 0.252 | 0.010 | 0.110 | 0.211 |
| S1_Leverage | 3,095 | 1.307 | 4.812 | 0.361 | 0.868 | 1.622 |
| SalesGrowth | 2,739 | 0.115 | 0.517 | −0.088 | 0.077 | 0.242 |
| Cashflow | 3,095 | −0.011 | 0.128 | −0.032 | 0.011 | 0.045 |
| DepRate | 3,095 | 0.027 | 0.019 | 0.015 | 0.025 | 0.036 |
| Size_ln | 3,095 | 15.307 | 2.152 | 14.015 | 15.448 | 16.764 |

---

## 15. Limitations and Caveats

### 15.1 Fiscal Year Alignment
SBP FSA fiscal years follow the Pakistan fiscal year (July–June). Sugar companies (approximately 31 firms in the FY25 file) report on a September fiscal year. Their FY2024 observation covers October 2023–September 2024, creating a 9-month misalignment with the July–June policy rate cycle. The `non_june_fye` flag allows these firms to be excluded in robustness checks.

### 15.2 Interest Expense as CoC Proxy Limitations
The realised interest-expense-to-debt ratio captures the *average* cost of the existing debt stock, not the *marginal* cost of new borrowing. Firms that locked in long-term fixed-rate debt years ago will show a lower proxy than firms borrowing at current market rates. This creates a lag between true perceived CoC and the measured proxy. The two-year lag specification in Model 3 partly addresses this by using the CoC proxy from FY−2 as the identifying variation.

### 15.3 Survivorship
The SBP FSA covers only companies listed on the Pakistan Stock Exchange that file annual accounts with the SBP. Delisted, failed, or voluntarily unlisted companies drop out of the panel. This creates a survivorship bias: the sample in later years systematically excludes firms that exited due to financial distress. Coefficients on the financial distress variables should be interpreted in light of this selection.

### 15.4 P8 Reconstruction Accuracy
The mean absolute P8 difference between reconstruction and direct KPI is 3.2 pp (FY2020–FY2023 overlap). As documented in Section 9, this reflects publication-vintage revisions rather than reconstruction error. However, it implies that for the 22.7% of observations where the two measures differ by more than 0.5 pp, there is residual uncertainty about which vintage better reflects economic reality. Researchers using P8_ROIC as a dependent variable should report robustness to the direct FY25 KPI (`P8_precomp`) as an alternative.

### 15.5 Source-File Break in the Merged Panel
The merged panel stitches data from two different publication vintages. Even with the `post2023` indicator, any systematic difference in the way SBP revised historical data for the FY25 publication — beyond what is captured by the firm-level exclusion criterion — could confound time-series comparisons around the FY2023/2024 boundary. Researchers should report split-sample results for the old panel alone (FY2015–2023) as the primary specification, with the merged panel as a robustness and extension check.

---

## References

- Gormsen, N.J. & Huber, K. (2024). *Equity Factors and Firm Investment.* Working paper.
- Gormsen, N.J. & Huber, K. (2025). *Corporate Investment and the Cost of Capital.* Working paper.
- Bond, S. & Van Reenen, J. (2007). Microeconometric models of investment and employment. *Handbook of Econometrics*, 6, 4417–4498.
- Fazzari, S.M., Hubbard, R.G. & Petersen, B.C. (1988). Financing constraints and corporate investment. *Brookings Papers on Economic Activity*, 1988(1), 141–206.
- Kaplan, S.N. & Zingales, L. (1997). Do investment-cash flow sensitivities provide useful measures of financing constraints? *Quarterly Journal of Economics*, 112(1), 169–215.
- State Bank of Pakistan. *Financial Statements Analysis of Companies (Non-Financial) Listed on Pakistan Stock Exchange*, various years. https://www.sbp.org.pk/departments/stats/fsa.htm

---

*This document is auto-maintained alongside the pipeline code. Any change to extraction rules, variable definitions, exclusion criteria, or winsorisation thresholds should be reflected here before committing.*
