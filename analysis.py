"""
analysis.py
-----------
Single source of truth for all cleaning and metric calculations used in this
assignment. Both `run_analysis.py` (prints the numbers behind BUSINESS_ANSWERS.md)
and `app.py` (the Streamlit dashboard) import from here, so the numbers you see
in the dashboard are guaranteed to match the numbers written up in the answers.

Design choice: movements with status == 'Cancelled' never actually executed,
so they are excluded from every stock-accuracy calculation (they are kept in
the raw data, just filtered out per-metric where relevant).
"""

import pandas as pd
import numpy as np

DIRECTIONAL_TYPES = {"Inbound": 1, "Return": 1, "Outbound": -1, "Transfer": -1}


def load_clean(path: str = "inventory_movements.csv") -> pd.DataFrame:
    """Load the raw CSV and apply the minimal, documented cleaning steps.

    Cleaning steps (see BUSINESS_ANSWERS.md Q4 for the full write-up):
      1. Drop exact full-row duplicates (15 found).
      2. Parse movement_date / expected_date as dates (74-75 unparseable ->
         become NaT and are excluded from date-based calcs, not dropped from
         the table, since we still need the rows for non-date metrics).
      3. No values are invented or imputed anywhere below - every "handling"
         step is a filter or a flag, never a guess.
    """
    df = pd.read_csv(path)
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    dupes_dropped = before - len(df)

    df["movement_date"] = pd.to_datetime(df["movement_date"], errors="coerce")
    df["expected_date"] = pd.to_datetime(df["expected_date"], errors="coerce")

    df.attrs["dupes_dropped"] = dupes_dropped
    return df


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the derived flag columns used throughout the analysis."""
    df = df.copy()
    df["is_cancelled"] = df["status"] == "Cancelled"
    df["is_discrepancy_label"] = df["status"] == "Discrepancy"
    df["missing_stock_after"] = df["stock_after"].isna() & ~df["is_cancelled"]
    df["neg_stock_after"] = df["stock_after"] < 0

    is_directional = df["movement_type"].isin(DIRECTIONAL_TYPES)
    signed_qty = df["movement_type"].map(DIRECTIONAL_TYPES).fillna(0) * df["quantity"]
    expected_after = df["stock_before"] + signed_qty
    df["math_mismatch"] = (
        is_directional
        & df["stock_after"].notna()
        & ~df["is_cancelled"]
        & ((expected_after - df["stock_after"]).abs() > 1e-6)
    )

    out_or_transfer = df["movement_type"].isin(["Outbound", "Transfer"])
    df["oversell"] = out_or_transfer & (df["quantity"] > df["stock_before"])
    df["issue_event"] = df["neg_stock_after"] | df["oversell"]
    return df


# ---------------------------------------------------------------------------
# Q1 - warehouse discrepancy rate
# ---------------------------------------------------------------------------
def warehouse_discrepancy_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["warehouse_id", "warehouse_city"]).agg(
        total_movements=("movement_id", "count"),
        labeled_discrepancies=("is_discrepancy_label", "sum"),
        neg_stock_events=("neg_stock_after", "sum"),
        math_mismatches=("math_mismatch", "sum"),
        missing_stock_after=("missing_stock_after", "sum"),
    ).reset_index()
    g["discrepancy_rate_pct"] = (g["labeled_discrepancies"] / g["total_movements"] * 100).round(2)
    g["missing_stock_after_pct"] = (g["missing_stock_after"] / g["total_movements"] * 100).round(1)
    return g.sort_values("discrepancy_rate_pct", ascending=False)


def warehouse_x_movement_type_rate(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["warehouse_id", "movement_type"]).agg(
        total=("movement_id", "count"), disc=("is_discrepancy_label", "sum")
    )
    g["rate_pct"] = (g["disc"] / g["total"] * 100).round(1)
    return g.reset_index().pivot(index="warehouse_id", columns="movement_type", values="rate_pct")


def discrepancy_label_vs_math_check(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-tab: does the status=='Discrepancy' label line up with an actual
    computable stock-math error (stock_after != stock_before +/- quantity)?"""
    sub = df[~df["is_cancelled"] & df["stock_after"].notna()]
    return pd.crosstab(sub["status"], sub["math_mismatch"])


# ---------------------------------------------------------------------------
# Q2 - unit cost vs quantity across suppliers
# ---------------------------------------------------------------------------
def supplier_cost_table(df: pd.DataFrame) -> pd.DataFrame:
    inb = df[df["movement_type"] == "Inbound"].copy()
    corr = inb.groupby("supplier_id").apply(lambda d: d["unit_cost"].corr(d["quantity"]))
    g = inb.groupby("supplier_id").agg(
        n_movements=("movement_id", "count"),
        avg_unit_cost=("unit_cost", "mean"),
        median_unit_cost=("unit_cost", "median"),
        avg_quantity=("quantity", "mean"),
    )
    g["cost_qty_corr"] = corr.round(2)
    g = g.round(2).sort_values("avg_unit_cost", ascending=False)
    return g.reset_index()


def overall_cost_qty_corr(df: pd.DataFrame) -> float:
    inb = df[df["movement_type"] == "Inbound"]
    return round(inb["unit_cost"].corr(inb["quantity"]), 3)


# ---------------------------------------------------------------------------
# Q3 - SKU stockouts / inventory imbalance
# ---------------------------------------------------------------------------
def sku_issue_table(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    g = df.groupby("sku_id").agg(
        total_movements=("movement_id", "count"),
        neg_stock_events=("neg_stock_after", "sum"),
        oversell_events=("oversell", "sum"),
        labeled_discrepancies=("is_discrepancy_label", "sum"),
    )
    g["issue_events"] = g["neg_stock_events"] + g["oversell_events"]
    g["issue_rate_pct"] = (g["issue_events"] / g["total_movements"] * 100).round(1)
    g = g.sort_values(["issue_events", "issue_rate_pct"], ascending=False)
    return g.reset_index().head(top_n)


# ---------------------------------------------------------------------------
# Q4 - data quality summary (numbers referenced in BUSINESS_ANSWERS.md)
# ---------------------------------------------------------------------------
def data_quality_summary(raw_df: pd.DataFrame, df: pd.DataFrame) -> dict:
    total = len(raw_df) + raw_df.attrs.get("dupes_dropped", 0)
    return {
        "raw_rows": total,
        "duplicate_rows_dropped": raw_df.attrs.get("dupes_dropped", 0),
        "rows_after_dedup": len(df),
        "missing_movement_date": int(df["movement_date"].isna().sum()),
        "missing_expected_date": int(df["expected_date"].isna().sum()),
        "missing_stock_after_total": int(df["stock_after"].isna().sum()),
        "missing_stock_after_cancelled_pct": round(
            df.loc[df["status"] == "Cancelled", "stock_after"].isna().mean() * 100, 1
        ),
        "missing_stock_after_noncancelled": int(df["missing_stock_after"].sum()),
        "wh04_missing_stock_after_pct": round(
            df.loc[
                (df["warehouse_id"] == "WH_04") & (df["status"] != "Cancelled"), "stock_after"
            ].isna().mean()
            * 100,
            1,
        ),
        "other_wh_missing_stock_after_pct": round(
            df.loc[
                (df["warehouse_id"] != "WH_04") & (df["status"] != "Cancelled"), "stock_after"
            ].isna().mean()
            * 100,
            1,
        ),
        "negative_stock_after_rows": int(df["neg_stock_after"].sum()),
        "negative_stock_after_pct": round(df["neg_stock_after"].mean() * 100, 1),
        "skus_with_negative_stock": int(df.loc[df["neg_stock_after"], "sku_id"].nunique()),
        "total_skus": int(df["sku_id"].nunique()),
        "supplier_id_only_on_inbound": bool(
            (df.groupby("movement_type")["supplier_id"].apply(lambda s: s.notna().mean()))
            .drop("Inbound")
            .eq(0)
            .all()
        ),
        "customer_id_only_on_outbound": bool(
            (df.groupby("movement_type")["customer_id"].apply(lambda s: s.notna().mean()))
            .drop("Outbound")
            .eq(0)
            .all()
        ),
    }


# ---------------------------------------------------------------------------
# Convenience: build everything needed by the app / CLI in one call
# ---------------------------------------------------------------------------
def build_all(path: str = "inventory_movements.csv"):
    raw = load_clean(path)
    df = add_flags(raw)
    return {
        "df": df,
        "wh_table": warehouse_discrepancy_table(df),
        "wh_x_type": warehouse_x_movement_type_rate(df),
        "label_vs_math": discrepancy_label_vs_math_check(df),
        "supplier_table": supplier_cost_table(df),
        "overall_corr": overall_cost_qty_corr(df),
        "sku_table": sku_issue_table(df),
        "dq": data_quality_summary(raw, df),
    }


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    results = build_all()

    print("=" * 70)
    print("Q1 - Warehouse discrepancy table")
    print("=" * 70)
    print(results["wh_table"].to_string(index=False))
    print("\nDiscrepancy rate % by warehouse x movement_type:")
    print(results["wh_x_type"])
    print("\nLabeled status 'Discrepancy' vs actual stock-math mismatch (rows, non-cancelled, stock_after present):")
    print(results["label_vs_math"])

    print("\n" + "=" * 70)
    print("Q2 - Supplier cost table (Inbound movements only)")
    print("=" * 70)
    print(results["supplier_table"].to_string(index=False))
    print("\nOverall unit_cost vs quantity correlation (all inbound):", results["overall_corr"])

    print("\n" + "=" * 70)
    print("Q3 - Top SKUs by stockout / imbalance issue events")
    print("=" * 70)
    print(results["sku_table"].to_string(index=False))

    print("\n" + "=" * 70)
    print("Q4 - Data quality summary")
    print("=" * 70)
    for k, v in results["dq"].items():
        print(f"{k}: {v}")
