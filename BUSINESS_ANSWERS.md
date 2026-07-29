# Business Answers

Candidate name: [YOUR NAME]
Date: [DATE]

All figures below are reproducible by running `python analysis.py` in this repo, which prints every table referenced here. The same functions power the dashboard (`app.py`), so the numbers on-screen and the numbers in this document are guaranteed to match.

---

## Q1. Which warehouse has the highest stock discrepancy rate, and what's actually driving it?

**Answer:**

WH_06 (Pune) has the highest labeled discrepancy rate at 11.34% (89 of 785 movements), just ahead of WH_01 Bengaluru (10.08%) and WH_05 Hyderabad (9.70%). WH_03 Delhi is the cleanest at 8.15%.

What's driving Pune's number isn't one weak workflow - discrepancies there are elevated fairly evenly across movement types (Transfer 14.2%, Adjustment 13.8%, Outbound 11.0%, Inbound 10.2%), which reads more like a site-level process or handling issue than a single broken integration.

There's a more important caveat, though: I cross-checked the `status = Discrepancy` label against an independent stock-math test (`stock_after` should equal `stock_before ± quantity` for directional movement types). The two don't agree well - of the 71 rows where the math genuinely doesn't add up, 66 are labeled "Completed" and only 5 are labeled "Discrepancy." So the status field looks like a manually-assigned flag (probably from a cycle count or exception process) rather than something derived from the stock ledger itself, and I wouldn't treat "discrepancy rate" as a fully trustworthy accuracy metric on its own.

That matters because WH_04 (Kolkata) tells a different and arguably more serious story: its labeled discrepancy rate looks unremarkable (8.64%), but 83.8% of its non-cancelled movements have no `stock_after` value recorded at all, consistently across all six months and every movement type, versus 0% missing everywhere else. You simply cannot verify inventory accuracy for the large majority of WH_04's activity. If I had to flag one warehouse for immediate operational attention, it would be Kolkata - not because its discrepancy number is bad, but because the number can't be trusted in the first place.

**How you checked it (query/method):**
`analysis.warehouse_discrepancy_table()` and `warehouse_x_movement_type_rate()` compute discrepancy rate as labeled discrepancies ÷ total movements per warehouse (and per warehouse × movement type). `discrepancy_label_vs_math_check()` builds an independent expected-stock calculation (`stock_before + quantity` for Inbound/Return, `stock_before - quantity` for Outbound/Transfer) and cross-tabs mismatches against the `status` column. The WH_04 missing-data figure comes from `data_quality_summary()`, computed on non-cancelled rows only.

---

## Q2. Is there a relationship between unit cost and quantity across suppliers? Which supplier(s) deviate, and by how much?

**Answer:**

No. Across all inbound movements, the correlation between `unit_cost` and `quantity` is -0.021 - essentially zero - and it stays close to zero within every individual supplier too (correlations range from -0.05 to +0.23 across the 12 suppliers). Buying more of something isn't associated with paying less (or more) per unit anywhere in this data.

SUP_09 is the clear outlier, but on price level, not on the cost/quantity relationship. Its average unit cost is ₹10,559.84 versus a tight ₹957–₹1,127 band for all 11 other suppliers - roughly 10x higher. It's not a flat markup either: SUP_09's own costs are spread almost continuously from ₹529.89 to ₹22,554.84, and the same SKU sourced from SUP_09 vs. another supplier can differ by 10-15x (e.g. SKU_0113 costs ₹15,521.84 from SUP_09 on one movement and ₹1,289.04 on another, while other suppliers price it at ₹998-₹1,838). That internal inconsistency makes me suspect a currency or unit-of-measure mismatch (per-case vs. per-unit cost, or a different currency entirely) or a data-entry issue in whatever feed SUP_09 comes from, rather than a genuine, consistent 10x price premium. I'd flag this to procurement/finance to verify against the actual PO/invoice before acting on it - it's too clean an outlier to be "real" pricing and too large to ignore.

**How you checked it (query/method):**
`analysis.supplier_cost_table()` groups Inbound movements (the only rows with a populated `supplier_id`) by supplier and computes mean/median unit cost, mean quantity, and the per-supplier Pearson correlation between `unit_cost` and `quantity`. `overall_cost_qty_corr()` computes the same correlation across all inbound rows. The SKU-level cross-check on SUP_09 compares its per-SKU unit costs directly against the same SKU's costs from other suppliers.

---

## Q3. Which SKU(s) show signs of frequent stockouts or inventory imbalance? What would you recommend doing about it?

**Answer:**

I flagged two independent signals of imbalance: (1) `stock_after` recorded as negative, which is physically impossible, and (2) an outbound/transfer `quantity` that exceeds the recorded `stock_before` - an oversell, whether or not the resulting `stock_after` was captured. Combining the two into an "issue rate" per SKU, the worst repeat offenders are SKU_0056 (40.0% of its 15 movements), SKU_0127 (38.5% of 13), SKU_0033 and SKU_0172 (33.3%, of 15 and 21 movements respectively), and SKU_0070 (28.6% of 21). The full top-15 list is in the dashboard and in `analysis.py`'s output.

Worth noting: this isn't a problem isolated to a handful of SKUs. 146 of the 300 SKUs in the dataset (about half) have at least one negative-stock event. That breadth suggests a systemic gap in how outbound/transfer quantities are validated against on-hand stock, on top of whatever SKU-specific demand-volatility issues exist for the worst offenders above.

Recommendation: put a hard validation rule at the WMS/ERP layer that rejects (or holds for review) any outbound/transfer movement whose requested quantity exceeds `stock_before`, instead of letting it post and produce an impossible negative balance - this fixes the systemic half of the problem immediately. For the SKUs with issue rates above ~25%, add them to a weekly cycle-count list and check whether it's a true demand/reorder-point problem (frequent genuine stockouts) versus a recording problem (stock counts not being decremented/incremented correctly) before changing safety-stock levels.

**How you checked it (query/method):**
`analysis.sku_issue_table()` groups by `sku_id` and counts negative-`stock_after` rows and oversell rows (`quantity > stock_before` on Outbound/Transfer movements), then ranks by combined issue count and issue rate (issue events ÷ that SKU's total movements) to avoid just surfacing high-volume SKUs.

---

## Q4. What data quality issues did you find, and how did you handle them?

**Answer:**

- **15 exact full-row duplicates** (same `movement_id`, identical across every column) - dropped before any analysis. Confirmed they were true duplicates and not two different events sharing an ID.
- **`stock_after` missing on 915 of 5,000 rows overall.** 100% of `Cancelled` movements have no `stock_after`, which makes sense - a cancelled movement never executed, so there's nothing to record. I excluded `Cancelled` rows from every stock-accuracy calculation rather than treating this as missing data.
- **WH_04 (Kolkata) is a separate, much bigger issue:** even after excluding cancelled rows, 83.8% of WH_04's movements have no `stock_after`, flat across all six months and every movement type, versus 0% at the other five warehouses. This looks like a systemic feed/integration gap specific to that site, not random missingness - I called it out explicitly in Q1 rather than let it quietly make WH_04 look "clean."
- **201 rows (4.0%) have a negative `stock_after`** - physically impossible for on-hand inventory - spread across 146 of 300 SKUs and all six warehouses. I didn't drop these; I treated them as a genuine signal and used them directly in Q3.
- **The `status = Discrepancy` label doesn't reliably track computable stock-math errors** - see Q1. I built an independent math check rather than trusting the label at face value, and I'd recommend the business do the same before using `status` for reporting.
- **`supplier_id` is populated only on `Inbound` rows, `customer_id` only on `Outbound` rows** - by design, since only those movement types have an external counterparty. Not an error, but worth documenting so nobody "fixes" it by imputing values.
- **73-75 rows have unparseable/missing `movement_date` or `expected_date`.** Parsed with `errors='coerce'` and excluded only from date-based calculations (none of the 5 core questions here needed date arithmetic, but I flagged it since a real weekly-tracking exercise would).

General approach: every fix above is a filter, an exclusion, or a flag - I didn't impute or guess a single value anywhere in this analysis. Where a "clean" number would have hidden a real issue (WH_04's missing data, the status/math mismatch), I surfaced the underlying problem instead of the tidier-looking headline number.

---

## Q5. If you could track exactly one metric weekly to catch inventory problems early, what would it be and why?

**Answer:**

The **oversell / negative-stock rate**: the % of outbound + transfer movements in a given week where the requested quantity exceeds `stock_before`. I'd track it overall and broken out by warehouse and SKU.

I picked this over the `status`-based discrepancy rate because Q1 shows that label doesn't reliably track real stock-math errors - it would be tracking a manual flag, not the underlying problem. I picked it over a pure data-completeness metric (e.g., % of movements with a valid `stock_after`) because completeness measures our ability to *see* the problem, while oversell rate measures the problem itself - a stockout that gets recorded perfectly is still a stockout. That said, completeness is a close second: without it, WH_04-style gaps mean you can't even trust the oversell number in the warehouses where it matters most, so in practice I'd want both, with completeness gating the primary metric (i.e., "oversell rate, warehouses with unreliable ending-stock data flagged separately").

**How you checked it (query/method):**
Reasoning + the same fields used in Q3 (`quantity` vs. `stock_before` on Outbound/Transfer rows), extended conceptually to a weekly cadence using `movement_date`.

---

## Anything else you'd flag if this were a real dataset at FreightFox?

Two things I'd want answered before trusting this data operationally: (1) what actually sets `status = Discrepancy` today, since it doesn't line up with the stock ledger - if it's a manual cycle-count flag, that's fine, but it should be labeled as such rather than implied to be a computed accuracy metric; and (2) what changed at WH_04 (a system migration, a new WMS integration, a reporting outage) that would explain an 84% gap in ending-stock capture that's been flat for six straight months - that's an operational blind spot, not a rounding error.
