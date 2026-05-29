"""
07_pre_analysis_graphs.py
==========================
Pre-analysis visualisation suite for the merged firm-level panel.

FIGURES PRODUCED (saved to Results/Figures/)
--------------------------------------------
  01_distributions_core_vars.png     -- 8-panel histogram+KDE grid
  02_boxplots_core_vars.png          -- Box-and-whisker for all 7 winsorised vars
  03_time_series_coc_inv.png         -- Mean CoC and Inv_Rate by year with CI bands
  04_macro_series.png                -- r_SBP, CPI, delta_r_SBP, Real_CoC over time
  05_macro_coc_alignment.png         -- Firm mean CoC vs SBP rate (dual-axis + scatter)
  06_sector_coc_inv_bar.png          -- Mean CoC and Inv_Rate by sector (horizontal bars)
  07_sector_composition.png          -- Firm count and % zero-interest by sector
  08_sector_year_heatmap.png         -- CoC_Proxy mean: 14 sectors x 11 years
  09_size_quartile_profiles.png      -- Key variable means by size quartile
  10_size_quartile_boxplots.png      -- Box plots of CoC and Inv by size quartile
  11_scatter_coc_inv.png             -- CoC_Proxy vs Inv_Rate scatter (sector colour)
  12_scatter_coc_lag_inv.png         -- CoC_Proxy_L1 vs Inv_Rate (lag identification)
  13_correlation_heatmap.png         -- Pearson correlation matrix heat map
  14_panel_balance.png               -- Years-in-panel bar + entry/exit line
  15_debt_status_comparison.png      -- Zero-interest vs debt-carrying radar/bars
  16_sample_flags_bar.png            -- Observation count per sample flag
  17_raw_financials_dist.png         -- TotalAssets, Sales, EBIT distributions (log)
  18_real_coc_over_time.png          -- Real_CoC distribution over time (violin)
  19_inv_rate_by_sector_year.png     -- Inv_Rate mean: 14 sectors x 11 years heatmap
  20_coc_policy_rate_scatter.png     -- Firm-level CoC vs year-mean policy rate

INPUT
-----
  Extracted Data/09_merged_panel.csv

OUTPUT
------
  Results/Figures/  (PNG, 300 dpi each)

Reference: Gormsen & Huber (2024, 2025).
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                    # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths and global style
# ---------------------------------------------------------------------------
CODES_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR   = os.path.dirname(CODES_DIR)
EXTRACTED_DIR = os.path.join(PROJECT_DIR, "Extracted Data")
FIGURES_DIR   = os.path.join(PROJECT_DIR, "Results", "Figures")
INPUT_PANEL   = os.path.join(EXTRACTED_DIR, "09_merged_panel.csv")

os.makedirs(FIGURES_DIR, exist_ok=True)

# -- Colour palette ----------------------------------------------------------
BLUE    = "#1F4E79"
BLUE2   = "#2E75B6"
ORANGE  = "#C55A11"
GREEN   = "#375623"
RED     = "#C00000"
GREY    = "#595959"
LGREY   = "#D9D9D9"
TEAL    = "#00B0F0"

SECTOR_NORM = {
    "Textile Sector":         "Textile",
    "Fuel and Energy Sector": "Fuel and Energy",
}

SECTOR_SHORT = {
    "Textile":                                              "Textile",
    "Chemicals, Chemical Products and Pharmaceuticals":     "Chemicals & Pharma",
    "Manufacturing":                                        "Manufacturing",
    "Motor Vehicles, Trailers & Autoparts":                 "Auto",
    "Food Products":                                        "Food Products",
    "Cement":                                               "Cement",
    "Fuel and Energy":                                      "Fuel & Energy",
    "Information and Communication Services":               "ICT",
    "Coke and Refined Petroleum Products":                  "Coke & Petroleum",
    "Other Services Activities":                            "Other Services",
    "Mineral products":                                     "Minerals",
    "Paper, Paperboard and Products":                       "Paper",
    "Sugar":                                                "Sugar",
    "Electrical Machinery and Apparatus":                   "Electrical Mach.",
}

# Palette for 14 sectors
SECTOR_PALETTE = sns.color_palette("tab20", 14)

DPI  = 300
FONT = "DejaVu Sans"

def apply_style():
    plt.rcParams.update({
        "font.family":        FONT,
        "font.size":          9,
        "axes.titlesize":     10,
        "axes.titleweight":   "bold",
        "axes.labelsize":     9,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.grid":          True,
        "axes.grid.axis":     "y",
        "grid.color":         LGREY,
        "grid.linewidth":     0.6,
        "xtick.labelsize":    8,
        "ytick.labelsize":    8,
        "legend.fontsize":    7.5,
        "legend.framealpha":  0.85,
        "figure.dpi":         100,
        "savefig.dpi":        DPI,
        "savefig.bbox":       "tight",
        "savefig.facecolor":  "white",
    })

def save(fig, name):
    path = os.path.join(FIGURES_DIR, name)
    fig.savefig(path)
    plt.close(fig)
    print(f"  Saved -> {name}")

def add_median_line(ax, data, color=RED, lw=1.2):
    med = data.median()
    ax.axvline(med, color=color, lw=lw, ls="--", label=f"Median {med:.3f}")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load():
    df = pd.read_csv(INPUT_PANEL)
    df["sector_norm"]  = df["sector"].replace(SECTOR_NORM)
    df["sector_short"] = df["sector_norm"].map(SECTOR_SHORT).fillna(df["sector_norm"])
    df["size_q"] = pd.qcut(df["TotalAssets"], q=4,
                           labels=["Q1 Small","Q2 Med-Small",
                                   "Q3 Med-Large","Q4 Large"])
    print(f"Loaded: {len(df):,} rows | {df['firm_id'].nunique():,} firms | "
          f"FY{df['fiscal_year'].min()}-FY{df['fiscal_year'].max()}")
    return df

# ---------------------------------------------------------------------------
# Figure 01 — Distributions of core variables
# ---------------------------------------------------------------------------
def fig01_distributions(df):
    vars_info = [
        ("Inv_Rate",     "Investment Rate",               "Proportion"),
        ("CoC_Proxy",    "Cost of Capital Proxy",         "Proportion"),
        ("P8_ROIC",      "Return on Capital Employed",    "Proportion"),
        ("S1_Leverage",  "Leverage Ratio (D+E)/C",        "Ratio"),
        ("SalesGrowth",  "Sales Growth Rate",             "Proportion"),
        ("Cashflow",     "Cash Flow Rate",                "Proportion"),
        ("DepRate",      "Depreciation Rate",             "Proportion"),
        ("Size_ln",      "Firm Size ln(Assets)",          "Natural log"),
    ]
    fig, axes = plt.subplots(2, 4, figsize=(14, 6.5))
    axes = axes.flatten()
    for i, (col, label, xlabel) in enumerate(vars_info):
        ax = axes[i]
        s  = df[col].dropna()
        ax.hist(s, bins=60, color=BLUE2, alpha=0.65, density=True,
                edgecolor="white", linewidth=0.3)
        s.plot.kde(ax=ax, color=ORANGE, lw=1.8, label="KDE")
        ax.axvline(s.median(), color=RED, lw=1.3, ls="--",
                   label=f"Median {s.median():.3f}")
        ax.axvline(s.mean(),   color=GREEN, lw=1.3, ls=":",
                   label=f"Mean {s.mean():.3f}")
        ax.set_title(label)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Density")
        ax.legend(fontsize=6.5, loc="upper right")
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    fig.suptitle("Figure 1 — Distributions of Core Research Variables (post-winsorisation)",
                 fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    save(fig, "01_distributions_core_vars.png")

# ---------------------------------------------------------------------------
# Figure 02 — Box plots
# ---------------------------------------------------------------------------
def fig02_boxplots(df):
    cols   = ["Inv_Rate","CoC_Proxy","P8_ROIC","S1_Leverage",
              "SalesGrowth","Cashflow","DepRate"]
    labels = ["Inv Rate","CoC Proxy","P8 ROIC","S1 Leverage",
              "Sales Growth","Cashflow","Dep Rate"]
    fig, axes = plt.subplots(1, 7, figsize=(15, 5))
    for i, (col, lab) in enumerate(zip(cols, labels)):
        ax = axes[i]
        s  = df[col].dropna()
        ax.boxplot(s, vert=True, patch_artist=True,
                   boxprops=dict(facecolor=BLUE2, alpha=0.7, color=BLUE),
                   medianprops=dict(color=RED, lw=2),
                   whiskerprops=dict(color=GREY),
                   capprops=dict(color=GREY),
                   flierprops=dict(marker=".", color=GREY, alpha=0.3,
                                  markersize=2))
        ax.set_title(lab, fontsize=8.5)
        ax.set_xticks([])
        n_lo = (s < s.quantile(0.25) - 1.5*(s.quantile(0.75)-s.quantile(0.25))).sum()
        n_hi = (s > s.quantile(0.75) + 1.5*(s.quantile(0.75)-s.quantile(0.25))).sum()
        ax.set_xlabel(f"n={len(s):,}\nout={n_lo+n_hi}", fontsize=7)
    fig.suptitle("Figure 2 — Box-and-Whisker Plots of Core Variables",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "02_boxplots_core_vars.png")

# ---------------------------------------------------------------------------
# Figure 03 — Time series: mean CoC and Inv_Rate with 95% CI bands
# ---------------------------------------------------------------------------
def fig03_time_series(df):
    grp = df.groupby("fiscal_year")
    yrs = sorted(df["fiscal_year"].unique())

    def ci(series_list):
        means, lo, hi = [], [], []
        for s in series_list:
            m  = s.mean()
            se = s.sem()
            means.append(m); lo.append(m - 1.96*se); hi.append(m + 1.96*se)
        return np.array(means), np.array(lo), np.array(hi)

    coc_m, coc_lo, coc_hi = ci([grp.get_group(y)["CoC_Proxy"].dropna() for y in yrs])
    inv_m, inv_lo, inv_hi = ci([grp.get_group(y)["Inv_Rate"].dropna()  for y in yrs])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    # CoC panel
    ax1.fill_between(yrs, coc_lo, coc_hi, alpha=0.2, color=BLUE2)
    ax1.plot(yrs, coc_m, "o-", color=BLUE, lw=2, ms=5, label="Mean CoC Proxy")
    # Shade high-rate period
    ax1.axvspan(2022.5, 2024.5, alpha=0.08, color=RED, label="Peak tightening")
    ax1.set_ylabel("CoC Proxy (decimal)", color=BLUE)
    ax1.set_title("Mean Firm-Level Cost of Capital Proxy (±95% CI)", fontweight="bold")
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:.2%}"))

    # Inv_Rate panel
    ax2.fill_between(yrs, inv_lo, inv_hi, alpha=0.2, color=ORANGE)
    ax2.plot(yrs, inv_m, "s-", color=ORANGE, lw=2, ms=5, label="Mean Investment Rate")
    ax2.axhline(0, color=GREY, lw=0.8, ls="--")
    ax2.set_ylabel("Investment Rate (decimal)", color=ORANGE)
    ax2.set_xlabel("Fiscal Year")
    ax2.set_title("Mean Investment Rate (±95% CI)", fontweight="bold")
    ax2.legend(loc="upper left")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:.1%}"))
    ax2.set_xticks(yrs)

    fig.suptitle("Figure 3 — Time-Series Evolution: CoC and Investment",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "03_time_series_coc_inv.png")

# ---------------------------------------------------------------------------
# Figure 04 — Macro series (r_SBP, CPI, delta_r_SBP, real rate)
# ---------------------------------------------------------------------------
def fig04_macro(df):
    macro = (df.drop_duplicates("fiscal_year")
               .sort_values("fiscal_year")
               [["fiscal_year","r_SBP","CPI_inflation","delta_r_SBP"]]
               .copy())
    macro["real_rate"] = macro["r_SBP"] - macro["CPI_inflation"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
    yrs = macro["fiscal_year"].tolist()

    def bar_with_line(ax, vals, title, ylabel, color, zero_line=False):
        colors = [color if v >= 0 else RED for v in vals]
        ax.bar(yrs, vals, color=colors, alpha=0.75, width=0.6, edgecolor="white")
        ax.plot(yrs, vals, "o-", color=GREY, lw=1.2, ms=4, zorder=5)
        if zero_line:
            ax.axhline(0, color=GREY, lw=0.8, ls="--")
        ax.set_title(title, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.set_xticks(yrs)
        ax.set_xticklabels([str(y) for y in yrs], rotation=45, ha="right")

    bar_with_line(axes[0,0], macro["r_SBP"].tolist(),
                  "SBP Policy Rate", "Rate (%)", BLUE)
    bar_with_line(axes[0,1], macro["CPI_inflation"].tolist(),
                  "CPI Inflation", "Inflation (%)", ORANGE)
    bar_with_line(axes[1,0], macro["delta_r_SBP"].tolist(),
                  "Change in Policy Rate (delta_r_SBP)", "Change (pp)", BLUE2,
                  zero_line=True)
    bar_with_line(axes[1,1], macro["real_rate"].tolist(),
                  "Real Policy Rate (r_SBP - CPI)", "Real Rate (pp)", GREEN,
                  zero_line=True)

    fig.suptitle("Figure 4 — Pakistan Macro Series FY2015–FY2025",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "04_macro_series.png")

# ---------------------------------------------------------------------------
# Figure 05 — Macro-CoC alignment (dual-axis + scatter)
# ---------------------------------------------------------------------------
def fig05_macro_coc(df):
    yr_stats = (df.groupby("fiscal_year")
                  .agg(mean_CoC=("CoC_Proxy","mean"),
                       med_CoC=("CoC_Proxy","median"),
                       r_SBP=("r_SBP","first"),
                       CPI=("CPI_inflation","first"))
                  .reset_index().sort_values("fiscal_year"))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Left: dual-axis time series
    ax = axes[0]
    ax2 = ax.twinx()
    lns1 = ax.plot(yr_stats["fiscal_year"], yr_stats["mean_CoC"]*100,
                   "o-", color=BLUE,   lw=2.2, ms=6, label="Mean CoC (%)")
    lns2 = ax.plot(yr_stats["fiscal_year"], yr_stats["med_CoC"]*100,
                   "s--", color=BLUE2, lw=1.5, ms=5, label="Median CoC (%)")
    lns3 = ax2.plot(yr_stats["fiscal_year"], yr_stats["r_SBP"],
                    "^-", color=ORANGE, lw=2, ms=6, label="SBP Policy Rate (%)")
    ax.set_xlabel("Fiscal Year"); ax.set_ylabel("Firm CoC (%)", color=BLUE)
    ax2.set_ylabel("SBP Policy Rate (%)", color=ORANGE)
    ax.set_xticks(yr_stats["fiscal_year"])
    ax.set_xticklabels(yr_stats["fiscal_year"].astype(str), rotation=45, ha="right")
    lns = lns1 + lns2 + lns3
    ax.legend(lns, [l.get_label() for l in lns], loc="upper left", fontsize=7.5)
    ax.set_title("Firm CoC vs SBP Policy Rate Over Time", fontweight="bold")

    # Right: scatter CoC mean vs r_SBP
    ax = axes[1]
    sc = ax.scatter(yr_stats["r_SBP"], yr_stats["mean_CoC"]*100,
                    c=yr_stats["fiscal_year"], cmap="RdYlBu_r",
                    s=90, zorder=5, edgecolors=GREY, lw=0.5)
    for _, row in yr_stats.iterrows():
        ax.annotate(str(int(row["fiscal_year"])),
                    (row["r_SBP"], row["mean_CoC"]*100),
                    textcoords="offset points", xytext=(5, 3), fontsize=7)
    # Regression line
    x, y = yr_stats["r_SBP"], yr_stats["mean_CoC"]*100
    m, b = np.polyfit(x, y, 1)
    xr = np.linspace(x.min(), x.max(), 100)
    ax.plot(xr, m*xr + b, "--", color=GREY, lw=1.2, label=f"OLS: slope={m:.3f}")
    ax.set_xlabel("SBP Policy Rate (%)"); ax.set_ylabel("Mean Firm CoC (%)")
    ax.set_title("Cross-Year: SBP Rate vs Mean Firm CoC", fontweight="bold")
    ax.legend()
    fig.colorbar(sc, ax=ax, label="Fiscal Year", shrink=0.7)

    fig.suptitle("Figure 5 — Alignment Between Firm Cost of Capital and Monetary Policy",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "05_macro_coc_alignment.png")

# ---------------------------------------------------------------------------
# Figure 06 — Sector bars: mean CoC and Inv_Rate
# ---------------------------------------------------------------------------
def fig06_sector_bars(df):
    sec_stats = (df.groupby("sector_short")
                   .agg(mean_CoC=("CoC_Proxy","mean"),
                        mean_Inv=("Inv_Rate","mean"),
                        N_firms=("firm_id","nunique"))
                   .reset_index()
                   .sort_values("mean_CoC", ascending=True))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
    colors = [BLUE2 if v >= 0 else ORANGE for v in sec_stats["mean_CoC"]]

    # CoC bar
    bars = ax1.barh(sec_stats["sector_short"], sec_stats["mean_CoC"]*100,
                    color=BLUE2, alpha=0.8, edgecolor="white", height=0.65)
    grand_mean = df["CoC_Proxy"].mean() * 100
    ax1.axvline(grand_mean, color=RED, lw=1.4, ls="--",
                label=f"Panel mean {grand_mean:.2f}%")
    for bar, v in zip(bars, sec_stats["mean_CoC"]*100):
        ax1.text(v + 0.05, bar.get_y() + bar.get_height()/2,
                 f"{v:.2f}%", va="center", fontsize=7)
    ax1.set_xlabel("Mean CoC Proxy (%)")
    ax1.set_title("Mean Cost of Capital by Sector", fontweight="bold")
    ax1.legend()
    ax1.grid(axis="x"); ax1.grid(axis="y", alpha=0)

    # Inv_Rate bar (sorted by Inv_Rate)
    sec_inv = sec_stats.sort_values("mean_Inv", ascending=True)
    colors2 = [ORANGE if v >= 0 else RED for v in sec_inv["mean_Inv"]]
    bars2 = ax2.barh(sec_inv["sector_short"], sec_inv["mean_Inv"]*100,
                     color=colors2, alpha=0.8, edgecolor="white", height=0.65)
    grand_inv = df["Inv_Rate"].mean() * 100
    ax2.axvline(grand_inv, color=BLUE, lw=1.4, ls="--",
                label=f"Panel mean {grand_inv:.2f}%")
    for bar, v in zip(bars2, sec_inv["mean_Inv"]*100):
        ax2.text(v + 0.05, bar.get_y() + bar.get_height()/2,
                 f"{v:.2f}%", va="center", fontsize=7)
    ax2.set_xlabel("Mean Investment Rate (%)")
    ax2.set_title("Mean Investment Rate by Sector", fontweight="bold")
    ax2.legend()
    ax2.grid(axis="x"); ax2.grid(axis="y", alpha=0)

    fig.suptitle("Figure 6 — Sector-Level Means: Cost of Capital and Investment Rate",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "06_sector_coc_inv_bar.png")

# ---------------------------------------------------------------------------
# Figure 07 — Sector composition: firm count, obs, % zero-interest
# ---------------------------------------------------------------------------
def fig07_sector_composition(df):
    sec = (df.groupby("sector_short")
             .agg(N_firms=("firm_id","nunique"),
                  N_obs=("firm_id","count"),
                  pct_zero=("zero_interest","mean"))
             .reset_index()
             .sort_values("N_firms", ascending=True))

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))

    axes[0].barh(sec["sector_short"], sec["N_firms"],
                 color=BLUE2, alpha=0.8, edgecolor="white")
    for i, v in enumerate(sec["N_firms"]):
        axes[0].text(v+0.5, i, str(v), va="center", fontsize=7.5)
    axes[0].set_xlabel("Number of Firms")
    axes[0].set_title("Unique Firms per Sector", fontweight="bold")

    axes[1].barh(sec["sector_short"], sec["N_obs"],
                 color=TEAL, alpha=0.8, edgecolor="white")
    for i, v in enumerate(sec["N_obs"]):
        axes[1].text(v+1, i, str(v), va="center", fontsize=7.5)
    axes[1].set_xlabel("Firm-Year Observations")
    axes[1].set_title("Observations per Sector", fontweight="bold")
    axes[1].set_yticklabels([])

    axes[2].barh(sec["sector_short"], sec["pct_zero"]*100,
                 color=ORANGE, alpha=0.8, edgecolor="white")
    for i, v in enumerate(sec["pct_zero"]*100):
        axes[2].text(v+0.3, i, f"{v:.0f}%", va="center", fontsize=7.5)
    axes[2].set_xlabel("% Zero-Interest Observations")
    axes[2].set_title("Zero-Interest Firm-Years (%)", fontweight="bold")
    axes[2].set_yticklabels([])

    fig.suptitle("Figure 7 — Sector Composition of the Panel",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "07_sector_composition.png")

# ---------------------------------------------------------------------------
# Figure 08 — Sector x Year CoC heatmap
# ---------------------------------------------------------------------------
def fig08_sector_heatmap(df):
    pivot = df.pivot_table(values="CoC_Proxy", index="sector_short",
                           columns="fiscal_year", aggfunc="mean", observed=True)
    cnt   = df.pivot_table(values="CoC_Proxy", index="sector_short",
                           columns="fiscal_year", aggfunc="count", observed=True)
    pivot[cnt < 3] = np.nan
    pivot = pivot.sort_values(pivot.columns[-1], ascending=False)
    pivot_pct = pivot * 100

    fig, ax = plt.subplots(figsize=(12, 6))
    mask = pivot_pct.isna()
    sns.heatmap(pivot_pct, ax=ax, cmap="YlOrRd", mask=mask,
                annot=True, fmt=".1f", annot_kws={"size": 7},
                linewidths=0.4, linecolor=LGREY,
                cbar_kws={"label": "Mean CoC Proxy (%)", "shrink": 0.6})
    ax.set_xlabel("Fiscal Year"); ax.set_ylabel("")
    ax.set_title("Figure 8 — Mean CoC Proxy (%) by Sector and Year",
                 fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    save(fig, "08_sector_year_heatmap.png")

# ---------------------------------------------------------------------------
# Figure 09 — Size quartile profiles (bar chart of means)
# ---------------------------------------------------------------------------
def fig09_size_profiles(df):
    vars_show = ["CoC_Proxy","Inv_Rate","P8_ROIC","SalesGrowth",
                 "S1_Leverage","Cashflow","DepRate"]
    labels    = ["CoC Proxy","Inv Rate","ROIC","Sales Growth",
                 "Leverage","Cashflow","Dep Rate"]
    quart_means = (df.groupby("size_q", observed=True)[vars_show]
                     .mean().reset_index())

    x = np.arange(len(quart_means))
    colours = [BLUE, BLUE2, TEAL, ORANGE]

    fig, axes = plt.subplots(2, 4, figsize=(14, 7))
    axes = axes.flatten()
    for i, (col, lab) in enumerate(zip(vars_show, labels)):
        ax = axes[i]
        vals = quart_means[col].values
        bars = ax.bar(x, vals, color=colours, alpha=0.82, edgecolor="white")
        ax.set_xticks(x)
        ax.set_xticklabels(["Q1\nSmall","Q2\nMed-S","Q3\nMed-L","Q4\nLarge"],
                           fontsize=7.5)
        ax.set_title(lab, fontweight="bold")
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2, v,
                    f"{v:.3f}", ha="center", va="bottom" if v>=0 else "top",
                    fontsize=7)
        ax.axhline(0, color=GREY, lw=0.6, ls="--")
    # Hide last unused subplot
    axes[-1].set_visible(False)
    fig.suptitle("Figure 9 — Key Variable Means by Firm Size Quartile",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "09_size_quartile_profiles.png")

# ---------------------------------------------------------------------------
# Figure 10 — Size quartile box plots for CoC and Inv_Rate
# ---------------------------------------------------------------------------
def fig10_size_boxplots(df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    palette = {q: c for q, c in zip(["Q1 Small","Q2 Med-Small",
                                      "Q3 Med-Large","Q4 Large"],
                                     [BLUE, BLUE2, TEAL, ORANGE])}
    order = ["Q1 Small","Q2 Med-Small","Q3 Med-Large","Q4 Large"]

    for ax, col, lab in zip(axes,
                             ["CoC_Proxy","Inv_Rate"],
                             ["CoC Proxy (%)","Investment Rate (%)"]):
        data = df[df[col].notna()].copy()
        data[col] *= 100
        sns.boxplot(data=data, x="size_q", y=col, order=order,
                    palette=palette, ax=ax,
                    medianprops=dict(color=RED, lw=2),
                    whiskerprops=dict(color=GREY),
                    boxprops=dict(alpha=0.75),
                    flierprops=dict(marker=".", color=GREY, alpha=0.2, ms=2))
        ax.set_xlabel("Size Quartile"); ax.set_ylabel(lab)
        ax.set_title(f"{lab} by Size Quartile", fontweight="bold")
        ax.set_xticklabels(["Q1\nSmall","Q2\nMed-S","Q3\nMed-L","Q4\nLarge"])

    fig.suptitle("Figure 10 — Cost of Capital and Investment Rate Across Firm Sizes",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "10_size_quartile_boxplots.png")

# ---------------------------------------------------------------------------
# Figure 11 — Scatter: CoC_Proxy vs Inv_Rate (coloured by sector)
# ---------------------------------------------------------------------------
def fig11_scatter_coc_inv(df):
    subs = df[df["in_model1_sample"]==1].copy()
    secs  = sorted(subs["sector_short"].unique())
    cmap  = {s: SECTOR_PALETTE[i % 14] for i, s in enumerate(secs)}

    fig, ax = plt.subplots(figsize=(10, 6))
    for sec in secs:
        sub = subs[subs["sector_short"]==sec]
        ax.scatter(sub["CoC_Proxy"]*100, sub["Inv_Rate"]*100,
                   color=cmap[sec], alpha=0.30, s=10, label=sec)

    # OLS trend line
    x = subs["CoC_Proxy"].dropna()
    y = subs.loc[x.index, "Inv_Rate"].dropna()
    common = x.index.intersection(y.index)
    m, b   = np.polyfit(x[common], y[common], 1)
    xr     = np.linspace(x[common].min(), x[common].max(), 200)
    ax.plot(xr*100, (m*xr+b)*100, "-", color=RED, lw=2,
            label=f"OLS slope={m:.3f}")
    ax.axhline(0, color=GREY, lw=0.7, ls="--")

    ax.set_xlabel("Cost of Capital Proxy (%)")
    ax.set_ylabel("Investment Rate (%)")
    ax.set_title("Figure 11 — CoC Proxy vs Investment Rate (by Sector)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", ncol=2, fontsize=6.5,
              markerscale=1.5, framealpha=0.9)
    fig.tight_layout()
    save(fig, "11_scatter_coc_inv.png")

# ---------------------------------------------------------------------------
# Figure 12 — Scatter: CoC_Proxy_L1 vs Inv_Rate (lag identification)
# ---------------------------------------------------------------------------
def fig12_scatter_lag(df):
    subs = df[df["in_model3_sample"]==1][
        ["CoC_Proxy_L1","CoC_Proxy_L2","Inv_Rate","sector_short"]
    ].dropna()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    for ax, col, lab in zip(axes,
                             ["CoC_Proxy_L1","CoC_Proxy_L2"],
                             ["CoC Proxy (t-1)","CoC Proxy (t-2)"]):
        ax.scatter(subs[col]*100, subs["Inv_Rate"]*100,
                   color=BLUE2, alpha=0.20, s=8)
        m, b = np.polyfit(subs[col], subs["Inv_Rate"], 1)
        xr   = np.linspace(subs[col].min(), subs[col].max(), 200)
        ax.plot(xr*100, (m*xr+b)*100, color=RED, lw=2,
                label=f"OLS slope={m:.3f}")
        ax.axhline(0, color=GREY, lw=0.7, ls="--")
        ax.set_xlabel(f"{lab} (%)")
        ax.set_ylabel("Investment Rate (%)")
        ax.set_title(f"Inv_Rate vs {lab}", fontweight="bold")
        ax.legend()

    fig.suptitle("Figure 12 — Lagged CoC Proxy vs Investment Rate (Model 3 Identification)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "12_scatter_coc_lag_inv.png")

# ---------------------------------------------------------------------------
# Figure 13 — Correlation heatmap
# ---------------------------------------------------------------------------
def fig13_corr_heatmap(df):
    corr_vars = ["Inv_Rate","CoC_Proxy","CoC_Proxy_L1","CoC_Proxy_L2",
                 "P8_ROIC","S1_Leverage","SalesGrowth","Size_ln",
                 "Cashflow","Real_CoC","delta_r_SBP"]
    avail = [v for v in corr_vars if v in df.columns]
    corr  = df[avail].corr(method="pearson")
    mask  = np.triu(np.ones_like(corr, dtype=bool), k=1)

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr, mask=mask, ax=ax,
                cmap="RdBu_r", center=0, vmin=-1, vmax=1,
                annot=True, fmt=".2f", annot_kws={"size": 7.5},
                linewidths=0.5, linecolor=LGREY,
                cbar_kws={"shrink": 0.7, "label": "Pearson r"})
    ax.set_title("Figure 13 — Pearson Correlation Matrix (Core Variables)",
                 fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=40)
    ax.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    save(fig, "13_correlation_heatmap.png")

# ---------------------------------------------------------------------------
# Figure 14 — Panel balance: years-per-firm bar + entry/exit line
# ---------------------------------------------------------------------------
def fig14_panel_balance(df):
    yrs_per_firm = df.groupby("firm_id")["fiscal_year"].count()
    bal_counts   = yrs_per_firm.value_counts().sort_index()

    all_yrs = sorted(df["fiscal_year"].unique())
    entry, exit_, active = [], [], []
    for yr in all_yrs:
        cur  = set(df[df["fiscal_year"]==yr]["firm_id"])
        active.append(len(cur))
        if yr > min(all_yrs):
            prev = set(df[df["fiscal_year"]==yr-1]["firm_id"])
            entry.append(len(cur - prev))
            exit_.append(len(prev - cur))
        else:
            entry.append(len(cur)); exit_.append(0)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Panel balance bar
    pct = 100 * bal_counts / bal_counts.sum()
    colors = [ORANGE if k < 9 else BLUE for k in bal_counts.index]
    ax1.bar(bal_counts.index, bal_counts.values, color=colors,
            alpha=0.82, edgecolor="white")
    for k, v in zip(bal_counts.index, bal_counts.values):
        ax1.text(k, v+1, str(v), ha="center", fontsize=7.5)
    ax1.set_xlabel("Years in Panel (out of 11 possible)")
    ax1.set_ylabel("Number of Firms")
    ax1.set_title("Panel Balance: Years per Firm", fontweight="bold")
    ax1.set_xticks(bal_counts.index)
    blue_p  = Patch(facecolor=BLUE,   label="≥9 years (strongly balanced)")
    orange_p= Patch(facecolor=ORANGE, label="<9 years (unbalanced)")
    ax1.legend(handles=[blue_p, orange_p])

    # Entry/exit/active line chart
    ax2.fill_between(all_yrs, active, alpha=0.15, color=BLUE)
    ax2.plot(all_yrs, active, "o-", color=BLUE,   lw=2, ms=6, label="Active firms")
    ax2.bar(all_yrs, entry,   color=GREEN,  alpha=0.65, width=0.3,
            align="edge",  label="Entered")
    ax2.bar([y-0.3 for y in all_yrs], [-e for e in exit_],
            color=ORANGE, alpha=0.65, width=0.3, label="Exited")
    ax2.axhline(0, color=GREY, lw=0.6)
    ax2.set_xlabel("Fiscal Year"); ax2.set_ylabel("Firm Count")
    ax2.set_title("Active Firms + Entry/Exit by Year", fontweight="bold")
    ax2.set_xticks(all_yrs)
    ax2.set_xticklabels([str(y) for y in all_yrs], rotation=45, ha="right")
    ax2.legend()

    fig.suptitle("Figure 14 — Panel Balance and Firm Entry/Exit",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "14_panel_balance.png")

# ---------------------------------------------------------------------------
# Figure 15 — Debt status comparison (grouped bars)
# ---------------------------------------------------------------------------
def fig15_debt_status(df):
    cols   = ["Inv_Rate","P8_ROIC","S1_Leverage","SalesGrowth",
              "Size_ln","Cashflow"]
    labels = ["Inv Rate","P8 ROIC","Leverage","Sales Growth",
              "Size (ln)","Cashflow"]
    grp_means = df.groupby("zero_interest")[cols].mean()
    x = np.arange(len(cols)); w = 0.35

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x - w/2, grp_means.loc[0].values, w,
           color=BLUE2, alpha=0.82, edgecolor="white",
           label="Debt-carrying (InterestExp > 0)")
    ax.bar(x + w/2, grp_means.loc[1].values, w,
           color=ORANGE, alpha=0.82, edgecolor="white",
           label="Zero-interest (InterestExp = 0)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.axhline(0, color=GREY, lw=0.6, ls="--")
    ax.set_ylabel("Mean value")
    ax.set_title("Figure 15 — Key Variable Means: Zero-Interest vs Debt-Carrying Firms",
                 fontsize=11, fontweight="bold")
    ax.legend()
    n_debt = (df["zero_interest"]==0).sum()
    n_zero = (df["zero_interest"]==1).sum()
    ax.text(0.98, 0.97,
            f"Debt-carrying: {n_debt:,} obs\nZero-interest: {n_zero:,} obs",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
    fig.tight_layout()
    save(fig, "15_debt_status_comparison.png")

# ---------------------------------------------------------------------------
# Figure 16 — Sample flags bar
# ---------------------------------------------------------------------------
def fig16_flags(df):
    flags = ["in_model1_sample","in_model3_sample","balanced_subsample",
             "zero_interest","negative_equity","non_june_fye",
             "robustness_excl","post2023"]
    labels = ["Model 1\n& 2","Model 3","Balanced\nsubsample",
              "Zero\ninterest","Negative\nequity","Non-Jun\nFYE",
              "Robustness\nexcl.","Post\n2023"]
    counts  = [df[f].sum() for f in flags if f in df.columns]
    pcts    = [100*c/len(df) for c in counts]
    colors  = [BLUE if l not in ["zero_interest","negative_equity",
                                  "non_june_fye","robustness_excl"]
               else ORANGE for l in flags]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    x = np.arange(len(labels))
    ax1.bar(x, counts, color=colors, alpha=0.82, edgecolor="white")
    for i, v in enumerate(counts):
        ax1.text(i, v+10, f"{v:,}", ha="center", fontsize=8)
    ax1.set_ylabel("Observations (count)")
    ax1.set_title("Observation Count per Sample Flag", fontweight="bold")

    ax2.bar(x, pcts, color=colors, alpha=0.82, edgecolor="white")
    ax2.axhline(100, color=GREY, lw=0.8, ls="--")
    for i, v in enumerate(pcts):
        ax2.text(i, v+0.5, f"{v:.1f}%", ha="center", fontsize=8)
    ax2.set_xticks(x); ax2.set_xticklabels(labels)
    ax2.set_ylabel("% of Panel")
    ax2.set_title("Percentage of Panel per Sample Flag", fontweight="bold")

    blue_p  = Patch(facecolor=BLUE,   label="Estimation sample flags")
    orange_p= Patch(facecolor=ORANGE, label="Exclusion / robustness flags")
    fig.legend(handles=[blue_p, orange_p], loc="upper right", fontsize=8)
    fig.suptitle("Figure 16 — Sample Flag Composition",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "16_sample_flags_bar.png")

# ---------------------------------------------------------------------------
# Figure 17 — Raw financials distributions (log-scale)
# ---------------------------------------------------------------------------
def fig17_raw_financials(df):
    items = [("TotalAssets","Total Assets"),("Sales","Sales"),
             ("EBIT","EBIT"),("InterestExpense","Interest Expense")]
    PKR = 1e-6   # PKR thousands -> PKR billions

    fig, axes = plt.subplots(1, 4, figsize=(14, 5))
    for ax, (col, lab) in zip(axes, items):
        s = (df[col].dropna() * PKR)
        s = s[s > 0]
        ax.hist(np.log10(s), bins=50, color=BLUE2, alpha=0.7,
                edgecolor="white", linewidth=0.3, density=True)
        pd.Series(np.log10(s)).plot.kde(ax=ax, color=ORANGE, lw=1.8)
        ax.axvline(np.log10(s.median()), color=RED, lw=1.3, ls="--",
                   label=f"Median\n{s.median():.1f} bn")
        ax.set_xlabel("log₁₀(PKR Billions)")
        ax.set_title(lab, fontweight="bold")
        ax.legend(fontsize=7)
        # Add PKR bn tick labels
        ticks = ax.get_xticks()
        ax.set_xticklabels([f"10^{t:.0f}" if t==int(t) else ""
                            for t in ticks], fontsize=7)

    fig.suptitle("Figure 17 — Distribution of Raw Financial Items (log₁₀ PKR Billions)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "17_raw_financials_dist.png")

# ---------------------------------------------------------------------------
# Figure 18 — Real CoC violin over time
# ---------------------------------------------------------------------------
def fig18_real_coc_violin(df):
    fig, ax = plt.subplots(figsize=(12, 5))
    yrs = sorted(df["fiscal_year"].unique())
    data_by_yr = [df.loc[df["fiscal_year"]==y, "Real_CoC"].dropna()*100
                  for y in yrs]
    parts = ax.violinplot(data_by_yr, positions=yrs,
                          widths=0.7, showmedians=True,
                          showextrema=True)
    for pc in parts["bodies"]:
        pc.set_facecolor(BLUE2); pc.set_alpha(0.55)
    parts["cmedians"].set_color(RED); parts["cmedians"].set_lw(2)
    parts["cbars"].set_color(GREY)
    parts["cmaxes"].set_color(GREY)
    parts["cmins"].set_color(GREY)
    ax.axhline(0, color=RED, lw=1.5, ls="--", label="Real CoC = 0")

    # Overlay macro real rate
    macro = df.drop_duplicates("fiscal_year").sort_values("fiscal_year")
    real_rate = (macro["r_SBP"] - macro["CPI_inflation"]).values
    ax.plot(yrs, real_rate, "^-", color=ORANGE, lw=1.8, ms=6, zorder=6,
            label="Real policy rate (r_SBP - CPI)")
    ax.set_xlabel("Fiscal Year"); ax.set_ylabel("Real CoC (%)")
    ax.set_xticks(yrs)
    ax.set_title("Figure 18 — Real Cost of Capital Distribution Over Time\n"
                 "(Violin = firm cross-section; Triangle = real policy rate)",
                 fontsize=11, fontweight="bold")
    ax.legend()
    fig.tight_layout()
    save(fig, "18_real_coc_over_time.png")

# ---------------------------------------------------------------------------
# Figure 19 — Inv_Rate sector x year heatmap
# ---------------------------------------------------------------------------
def fig19_inv_heatmap(df):
    pivot = df.pivot_table(values="Inv_Rate", index="sector_short",
                           columns="fiscal_year", aggfunc="mean", observed=True)
    cnt   = df.pivot_table(values="Inv_Rate", index="sector_short",
                           columns="fiscal_year", aggfunc="count", observed=True)
    pivot[cnt < 3] = np.nan
    pivot = pivot.sort_values(pivot.columns[-1], ascending=False)
    pivot_pct = pivot * 100

    fig, ax = plt.subplots(figsize=(12, 6))
    mask = pivot_pct.isna()
    sns.heatmap(pivot_pct, ax=ax, cmap="RdYlGn", center=0, mask=mask,
                annot=True, fmt=".1f", annot_kws={"size": 7},
                linewidths=0.4, linecolor=LGREY,
                cbar_kws={"label": "Mean Investment Rate (%)", "shrink": 0.6})
    ax.set_xlabel("Fiscal Year"); ax.set_ylabel("")
    ax.set_title("Figure 19 — Mean Investment Rate (%) by Sector and Year",
                 fontsize=11, fontweight="bold")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)
    fig.tight_layout()
    save(fig, "19_inv_rate_sector_year_heatmap.png")

# ---------------------------------------------------------------------------
# Figure 20 — delta_r_SBP vs Inv_Rate: identifying variation
# ---------------------------------------------------------------------------
def fig20_delta_r_inv(df):
    yr_means = (df.groupby("fiscal_year")
                  .agg(mean_Inv=("Inv_Rate","mean"),
                       delta_r=("delta_r_SBP","first"),
                       r_SBP=("r_SBP","first"),
                       N=("firm_id","count"))
                  .reset_index())

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Year-level scatter: delta_r vs mean Inv
    ax = axes[0]
    sc = ax.scatter(yr_means["delta_r"], yr_means["mean_Inv"]*100,
                    s=yr_means["N"]/4, c=yr_means["fiscal_year"],
                    cmap="RdYlBu_r", edgecolors=GREY, lw=0.5, zorder=5)
    for _, row in yr_means.iterrows():
        ax.annotate(str(int(row["fiscal_year"])),
                    (row["delta_r"], row["mean_Inv"]*100),
                    xytext=(4, 3), textcoords="offset points", fontsize=7)
    m, b = np.polyfit(yr_means["delta_r"], yr_means["mean_Inv"]*100, 1)
    xr   = np.linspace(yr_means["delta_r"].min(), yr_means["delta_r"].max(), 100)
    ax.plot(xr, m*xr+b, "--", color=RED, lw=1.5, label=f"OLS slope={m:.3f}")
    ax.axhline(0, color=GREY, lw=0.7, ls="--")
    ax.axvline(0, color=GREY, lw=0.7, ls="--")
    ax.set_xlabel("Change in SBP Policy Rate (pp)")
    ax.set_ylabel("Mean Firm Investment Rate (%)")
    ax.set_title("delta_r_SBP vs Mean Inv_Rate\n(year-level aggregates)",
                 fontweight="bold")
    ax.legend()
    fig.colorbar(sc, ax=ax, label="Fiscal Year", shrink=0.7)

    # Year-level: stacked bars — delta_r as identifying variation
    ax = axes[1]
    colors = [GREEN if v > 0 else RED for v in yr_means["delta_r"]]
    ax2 = ax.twinx()
    ax.bar(yr_means["fiscal_year"], yr_means["delta_r"],
           color=colors, alpha=0.5, width=0.5, label="delta_r_SBP (pp)")
    ax2.plot(yr_means["fiscal_year"], yr_means["mean_Inv"]*100,
             "o-", color=BLUE, lw=2, ms=6, label="Mean Inv Rate (%)")
    ax.axhline(0, color=GREY, lw=0.7)
    ax.set_xlabel("Fiscal Year")
    ax.set_ylabel("delta_r_SBP (pp)", color=GREY)
    ax2.set_ylabel("Mean Investment Rate (%)", color=BLUE)
    ax.set_xticks(yr_means["fiscal_year"])
    ax.set_xticklabels(yr_means["fiscal_year"].astype(str),
                       rotation=45, ha="right")
    green_p = Patch(facecolor=GREEN, alpha=0.5, label="Rate increase")
    red_p   = Patch(facecolor=RED,   alpha=0.5, label="Rate decrease")
    ln2 = Line2D([0],[0], color=BLUE, lw=2, marker="o", label="Mean Inv Rate")
    ax.legend(handles=[green_p, red_p, ln2], loc="upper left", fontsize=7.5)
    ax.set_title("Policy Rate Change vs Investment Rate\n(identifying variation)",
                 fontweight="bold")

    fig.suptitle("Figure 20 — Monetary Policy Change and Investment: Year-Level Patterns",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save(fig, "20_delta_r_inv_identification.png")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    apply_style()

    print("=" * 65)
    print("Script 07 -- Pre-Analysis Graphs")
    print(f"Output: {FIGURES_DIR}")
    print("=" * 65)

    df = load()
    print()

    steps = [
        ("01 Distributions",           fig01_distributions),
        ("02 Box plots",               fig02_boxplots),
        ("03 Time series CoC/Inv",     fig03_time_series),
        ("04 Macro series",            fig04_macro),
        ("05 Macro-CoC alignment",     fig05_macro_coc),
        ("06 Sector bars",             fig06_sector_bars),
        ("07 Sector composition",      fig07_sector_composition),
        ("08 Sector-year CoC heatmap", fig08_sector_heatmap),
        ("09 Size quartile profiles",  fig09_size_profiles),
        ("10 Size quartile boxplots",  fig10_size_boxplots),
        ("11 Scatter CoC vs Inv",      fig11_scatter_coc_inv),
        ("12 Scatter lag CoC vs Inv",  fig12_scatter_lag),
        ("13 Correlation heatmap",     fig13_corr_heatmap),
        ("14 Panel balance",           fig14_panel_balance),
        ("15 Debt status",             fig15_debt_status),
        ("16 Sample flags",            fig16_flags),
        ("17 Raw financials",          fig17_raw_financials),
        ("18 Real CoC violin",         fig18_real_coc_violin),
        ("19 Inv heatmap",             fig19_inv_heatmap),
        ("20 delta_r identification",  fig20_delta_r_inv),
    ]

    for label, fn in steps:
        print(f"\n[{label}]")
        try:
            fn(df)
        except Exception as e:
            print(f"  ERROR: {e}")

    print()
    print("=" * 65)
    print(f"All figures saved to: {FIGURES_DIR}")
    print(f"Total: {len(steps)} figures at 300 dpi")
    print("=" * 65)


if __name__ == "__main__":
    run()
