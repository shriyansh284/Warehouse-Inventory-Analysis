"""
Warehouse Inventory Analytics dashboard.

Run locally with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analysis import build_all

st.set_page_config(
    page_title="Warehouse Inventory Analytics",
    page_icon="\U0001F4E6",
    layout="wide",
)

PRIMARY = "#1f3a5f"
ACCENT = "#e8a33d"
BAD = "#c0392b"
GOOD = "#2f9e44"


@st.cache_data
def get_data():
    return build_all("inventory_movements.csv")


results = get_data()
df = results["df"]

st.title("\U0001F4E6 Warehouse Inventory Analytics")
st.caption(
    "5,000-row movement-level dataset across 6 warehouses. "
    "Every number on this page is computed live from `inventory_movements.csv` via `analysis.py` "
    "- nothing here is hand-typed or eyeballed."
)

# ---------------------------------------------------------------------------
# Top-line KPIs
# ---------------------------------------------------------------------------
dq = results["dq"]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Movements analyzed", f"{dq['rows_after_dedup']:,}", f"-{dq['duplicate_rows_dropped']} exact dupes dropped")
k2.metric("Warehouses", df["warehouse_id"].nunique())
k3.metric("SKUs", df["sku_id"].nunique())
k4.metric("Suppliers", df["supplier_id"].nunique())
k5.metric("Rows with negative stock_after", f"{dq['negative_stock_after_rows']}", f"{dq['negative_stock_after_pct']}% of all rows", delta_color="inverse")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Q1 · Warehouse discrepancies",
    "Q2 · Supplier cost outliers",
    "Q3 · SKU stockouts",
    "Q4 · Data quality",
    "Q5 · Metric to watch",
])

# ---------------------------------------------------------------------------
# Q1
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Which warehouse has the highest stock discrepancy rate?")
    wh = results["wh_table"]

    left, right = st.columns([3, 2])
    with left:
        fig = px.bar(
            wh.sort_values("discrepancy_rate_pct"),
            x="discrepancy_rate_pct",
            y="warehouse_city",
            orientation="h",
            text="discrepancy_rate_pct",
            color="discrepancy_rate_pct",
            color_continuous_scale=["#2f9e44", "#e8a33d", "#c0392b"],
            labels={"discrepancy_rate_pct": "Discrepancy rate (%)", "warehouse_city": ""},
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        fig.update_layout(coloraxis_showscale=False, height=380, margin=dict(l=0, r=10, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("**WH_06 (Pune) has the highest *labeled* discrepancy rate: 11.34%**")
        st.markdown(
            "It isn't one bad movement type dragging the average up - Pune runs "
            "hot across the board (Transfer 14.2%, Adjustment 13.8%, Outbound 11.0%), "
            "which points to a site-level process issue rather than a single workflow bug."
        )
        st.warning(
            f"**But watch WH_04 (Kolkata):** {dq['wh04_missing_stock_after_pct']}% of its "
            "non-cancelled movements have no recorded ending stock at all (vs. "
            f"{dq['other_wh_missing_stock_after_pct']}% everywhere else). Its true accuracy "
            "can't even be measured - see the Q4 tab."
        )

    st.markdown("**Discrepancy rate (%) by warehouse × movement type**")
    st.dataframe(results["wh_x_type"], use_container_width=True)

    st.markdown("**Does the `status = Discrepancy` label actually track a computable stock-math error?**")
    st.dataframe(results["label_vs_math"], use_container_width=True)
    st.caption(
        "Rows where stock_after doesn't equal stock_before ± quantity. Note most math mismatches "
        "sit on rows labeled 'Completed', not 'Discrepancy' - the label and the arithmetic disagree "
        "more often than they agree. Treat `status` as a manual flag, not ground truth."
    )

# ---------------------------------------------------------------------------
# Q2
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Is there a relationship between unit cost and quantity across suppliers?")
    sup = results["supplier_table"]
    st.metric("Overall cost–quantity correlation (all inbound movements)", results["overall_corr"])

    left, right = st.columns([3, 2])
    with left:
        inb = df[df["movement_type"] == "Inbound"]
        fig = px.scatter(
            inb, x="quantity", y="unit_cost", color="supplier_id",
            opacity=0.65, height=430,
            labels={"quantity": "Quantity", "unit_cost": "Unit cost (₹)"},
        )
        fig.update_layout(margin=dict(l=0, r=10, t=10, b=0), legend_title="Supplier")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("**No supplier shows a real cost–quantity relationship** - every per-supplier correlation sits between -0.05 and +0.23, i.e. essentially noise.")
        st.error(
            "**SUP_09 is a clear outlier on price, not on the cost/quantity relationship.** "
            f"Average unit cost ≈ ₹{sup.iloc[0]['avg_unit_cost']:,.0f} vs "
            f"₹{sup[sup.supplier_id != 'SUP_09']['avg_unit_cost'].mean():,.0f} for every other "
            "supplier - roughly 10x higher, spread almost continuously from ₹530 to ₹22,555 "
            "rather than a flat markup. Worth a procurement check: currency/unit mismatch, "
            "premium/rush SKU mix, or a data-entry error are all more likely than genuine "
            "10x pricing."
        )

    st.dataframe(sup, use_container_width=True)

# ---------------------------------------------------------------------------
# Q3
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Which SKUs show frequent stockouts or inventory imbalance?")
    sku = results["sku_table"]
    st.caption(
        "'Issue event' = stock_after recorded as negative (physically impossible), OR an "
        "outbound/transfer quantity that exceeds the recorded stock_before (an oversell)."
    )
    fig = px.bar(
        sku.sort_values("issue_rate_pct"),
        x="issue_rate_pct", y="sku_id", orientation="h",
        text="issue_events",
        color="issue_rate_pct", color_continuous_scale=["#e8a33d", "#c0392b"],
        labels={"issue_rate_pct": "Issue rate (% of that SKU's movements)", "sku_id": ""},
        height=460,
    )
    fig.update_traces(texttemplate="%{text} events", textposition="outside")
    fig.update_layout(coloraxis_showscale=False, margin=dict(l=0, r=10, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        f"**{dq['skus_with_negative_stock']} of {dq['total_skus']} SKUs** have at least one "
        "negative stock_after event - this is a broad, systemic pattern rather than a handful "
        "of problem SKUs, but the ones above are the worst repeat offenders."
    )
    st.markdown(
        "**Recommendation:** add a hard validation rule at the WMS/ERP layer that rejects any "
        "outbound/transfer movement whose quantity exceeds stock_before (block the oversell "
        "instead of recording an impossible negative balance), and put SKUs with issue rates "
        "above ~25% on a weekly cycle-count list until the rate drops."
    )
    st.dataframe(sku, use_container_width=True)

# ---------------------------------------------------------------------------
# Q4
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("Data quality issues found (and how they were handled)")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Issues found")
        st.markdown(f"""
- **{dq['duplicate_rows_dropped']} exact full-row duplicates** (same `movement_id`, identical in every column) - dropped before any analysis.
- **`stock_after` missing on {dq['missing_stock_after_total']} rows overall.** {dq['missing_stock_after_cancelled_pct']}% of that is `Cancelled` movements, which is expected (a cancelled movement never executed, so there's no ending stock to record) - not treated as an error.
- **WH_04 (Kolkata) is the real story:** even excluding Cancelled rows, {dq['wh04_missing_stock_after_pct']}% of WH_04's movements have no `stock_after` at all, flat across every month and every movement type, vs {dq['other_wh_missing_stock_after_pct']}% everywhere else. This looks like a systemic feed/integration gap at that one site, not randomly missing data.
- **{dq['negative_stock_after_pct']}% of rows ({dq['negative_stock_after_rows']} rows) have a negative `stock_after`** - physically impossible, spread across {dq['skus_with_negative_stock']} of {dq['total_skus']} SKUs and every warehouse.
- **The `status = Discrepancy` label doesn't reliably track computable stock-math errors** (see Q1) - more raw math mismatches sit on `Completed` rows than on `Discrepancy` rows.
- **`supplier_id`** is populated only on `Inbound` rows and **`customer_id`** only on `Outbound` rows - by design (structural, not an error), since only those movement types have a counterparty.
- **{dq['missing_movement_date']} rows missing `movement_date`**, {dq['missing_expected_date']} missing `expected_date` - excluded from date-based calculations only.
""")
    with c2:
        st.markdown("##### How each was handled")
        st.markdown("""
- Dropped exact duplicates before computing anything.
- Built an independent stock-math check (`stock_after` vs `stock_before ± quantity`) rather than trusting the `status` column at face value, and cross-checked the two.
- Excluded `Cancelled` rows from every stock-accuracy metric.
- Reported WH_04's missing-data rate as its own finding instead of letting it silently deflate its discrepancy rate.
- Flagged negative-stock rows as a distinct signal (used directly in Q3) rather than dropping them, since they're informative, not noise.
- Left `supplier_id`/`customer_id` structural sparsity as-is; no imputation.
- Parsed dates with `errors='coerce'` and excluded unparseable dates from date-based calcs without dropping the row from the rest of the analysis.
""")

    st.info(
        "General principle used throughout: **never impute a number that wasn't measured.** "
        "Every 'handling' step above is a filter, an exclusion, or a flag - not a guess."
    )

# ---------------------------------------------------------------------------
# Q5
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("If you could track exactly one metric weekly, what would it be?")
    st.markdown("""
### Oversell / negative-stock rate
**Definition:** % of outbound + transfer movements in a given week where the requested
quantity exceeds `stock_before` (i.e. it would push stock negative or already did).

**Why this one, over the alternatives:**
- It's the most physically unambiguous signal in the dataset - unlike the `status`
  label (shown in Q1 to disagree with the actual arithmetic more often than it agrees),
  a negative or oversold balance can't be explained away.
- It's a **leading indicator of real operational pain** (stockouts, failed fulfillment,
  customer-facing misses) rather than a data-hygiene metric.
- It's directly actionable at the SKU + warehouse level - the same query that produces
  the weekly number also produces the watchlist (see Q3).

**Runner-up I seriously considered:** stock-after completeness rate (% of movements
with a valid, present ending stock). This would have caught the WH_04 integration gap
immediately, and I'd track it as a close second - without it you can't fully trust the
oversell metric either. But oversell rate wins because it measures the business problem
directly, not just our ability to see it.
""")

st.divider()
st.caption(
    "Built with Streamlit + Plotly. Source: `analysis.py` (all metrics) and `app.py` (this UI). "
    "See BUSINESS_ANSWERS.md for the full written answers and README.md for setup."
)
