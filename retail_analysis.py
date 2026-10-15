"""
Retail Database Analysis: SQL + Python
Topics: data type classification | derived metrics | group by | trend analysis | correlation
Stack: SQL (SQLite), Python, pandas, NumPy, Matplotlib, Seaborn
Run: python retail_analysis.py   (creates retail.db, charts in images/, CSVs in powerbi/)
"""
import re, sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
IMG, DB = "images/", "retail.db"
rng = np.random.default_rng(11)

# ------------------------------------------------------------------
# 0. BUILD THE DATABASE (synthetic data loaded into SQLite)
# ------------------------------------------------------------------
con = sqlite3.connect(DB)
con.executescript(open("sql/schema.sql").read())

n_cust, n_prod, n_orders = 1500, 120, 9000
cities = ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Hyderabad"]
customers = pd.DataFrame({
    "customer_id": range(1, n_cust + 1),
    "city": rng.choice(cities, n_cust),
    "segment": rng.choice(["Consumer", "Corporate", "Home Office"], n_cust, p=[.6, .25, .15]),
    "signup_date": (pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, n_cust), unit="D")).strftime("%Y-%m-%d"),
})
cats = {"Electronics": (150, .62), "Furniture": (220, .70), "Clothing": (45, .50),
        "Groceries": (12, .78), "Sports": (60, .58), "Books": (18, .65)}
prod_rows = []
for pid in range(1, n_prod + 1):
    cat = list(cats)[(pid - 1) % len(cats)]
    price, cost_ratio = cats[cat]
    lp = round(float(rng.lognormal(np.log(price), .35)), 2)
    prod_rows.append((pid, f"{cat[:4].upper()}-{pid:03d}", cat, round(lp * float(np.clip(rng.normal(cost_ratio, .04), .4, .9)), 2), lp))
products = pd.DataFrame(prod_rows, columns=["product_id", "product_name", "category", "unit_cost", "list_price"])

# Pareto-style customer activity: a few customers order a lot
weights = rng.pareto(1.6, n_cust) + 1
cust_ids = rng.choice(customers.customer_id, n_orders, p=weights / weights.sum())
days = rng.integers(0, 730, n_orders)
dates = pd.Timestamp("2024-01-01") + pd.to_timedelta(days, unit="D")
orders = pd.DataFrame({"order_id": range(1, n_orders + 1), "customer_id": cust_ids,
                       "order_date": dates.strftime("%Y-%m-%d"),
                       "channel": rng.choice(["Online", "Store", "Mobile App"], n_orders, p=[.5, .3, .2])})
items = []
iid = 1
for oid, d in zip(orders.order_id, dates):
    for _ in range(max(1, rng.poisson(1.3))):
        # seasonality: Nov-Dec boost to gifting categories, higher discounts in sale months
        pid = int(rng.integers(1, n_prod + 1))
        disc = float(rng.choice([0, .05, .10, .15, .20, .30], p=[.35, .2, .2, .12, .08, .05]))
        if d.month in (11, 12): disc = min(.30, disc + .05)
        qty = int(max(1, rng.poisson(1.5 + disc * 6)))
        items.append((iid, oid, pid, qty, disc)); iid += 1
order_items = pd.DataFrame(items, columns=["item_id", "order_id", "product_id", "quantity", "discount"])
for name, frame in [("customers", customers), ("products", products), ("orders", orders), ("order_items", order_items)]:
    frame.to_sql(name, con, if_exists="append", index=False)
con.commit()

# ------------------------------------------------------------------
# Load the named queries from sql/queries.sql
# ------------------------------------------------------------------
sql_text = open("sql/queries.sql").read()
QUERIES = {m.group(1): m.group(2).strip() for m in re.finditer(r"-- name: (\w+)\n(.*?;)", sql_text, re.S)}
q = lambda name: pd.read_sql_query(QUERIES[name], con)

# ------------------------------------------------------------------
# 1. DATA TYPE CLASSIFICATION (from the database schema)
# ------------------------------------------------------------------
def classify(table, col, sql_type):
    if col.endswith("_id") or col == "item_id": return "Identifier"
    if "date" in col: return "Datetime (stored as TEXT)"
    if sql_type == "TEXT": return "Categorical"
    s = pd.read_sql_query(f"SELECT {col} FROM {table}", con)[col]
    return "Numeric - Discrete" if s.nunique() < 15 else "Numeric - Continuous"

rows = []
for t in ["customers", "products", "orders", "order_items"]:
    for _, r in pd.read_sql_query(f"PRAGMA table_info({t})", con).iterrows():
        rows.append((t, r["name"], r["type"], classify(t, r["name"], r["type"])))
schema = pd.DataFrame(rows, columns=["table", "column", "sql_type", "classification"])
print("=== 1. DATA TYPE CLASSIFICATION ===\n", schema.to_string(index=False))
counts = pd.read_sql_query("SELECT 'customers' t, COUNT(*) n FROM customers UNION ALL SELECT 'products', COUNT(*) FROM products "
                           "UNION ALL SELECT 'orders', COUNT(*) FROM orders UNION ALL SELECT 'order_items', COUNT(*) FROM order_items", con)
print("\nRow counts:\n", counts.to_string(index=False))

fig, ax = plt.subplots(figsize=(9, 5))
piv = schema.groupby(["table", "classification"]).size().unstack(fill_value=0)
piv.plot.barh(stacked=True, ax=ax, colormap="tab20")
ax.set_title("Database Columns by Data Type Classification", fontweight="bold"); ax.set_xlabel("Number of columns"); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(IMG + "1_data_types.png", dpi=200); plt.close()

# ------------------------------------------------------------------
# 2. DERIVED METRICS (computed in SQL)
# ------------------------------------------------------------------
kpi = q("kpis"); print("\n=== 2. KPIs (SQL) ===\n", kpi.T)
cust = q("customer_value")
print("\nBuyer types:\n", cust["buyer_type"].value_counts())

# ------------------------------------------------------------------
# 3. GROUP BY
# ------------------------------------------------------------------
cat = q("revenue_by_category"); print("\n=== 3. REVENUE BY CATEGORY ===\n", cat)
cc = q("revenue_by_city_channel"); topprod = q("top_product_per_category"); print("\nTop product per category:\n", topprod)
heat = cc.pivot(index="city", columns="channel", values="revenue")

fig, axes = plt.subplots(1, 3, figsize=(17, 5), width_ratios=[1.2, 1, 1.1])
x = np.arange(len(cat)); axes[0].bar(x - .2, cat["revenue"] / 1e3, .4, label="Revenue", color="#264653")
axes[0].bar(x + .2, cat["profit"] / 1e3, .4, label="Profit", color="#2A9D8F")
axes[0].set_xticks(x); axes[0].set_xticklabels(cat["category"], rotation=25); axes[0].set_ylabel("Thousands"); axes[0].legend()
axes[0].set_title("Revenue vs Profit by Category", fontweight="bold")
bb = axes[1].bar(cat["category"], cat["margin_pct"], color="#E9C46A"); axes[1].bar_label(bb, fmt="%.1f%%", padding=2)
axes[1].tick_params(axis="x", rotation=25); axes[1].set_title("Profit Margin % by Category", fontweight="bold")
sns.heatmap(heat / 1e3, annot=True, fmt=".0f", cmap="YlGnBu", ax=axes[2], cbar_kws={"label": "Revenue (thousands)"})
axes[2].set_title("Revenue: City x Channel", fontweight="bold")
plt.tight_layout(); plt.savefig(IMG + "2_group_by.png", dpi=200); plt.close()

# ------------------------------------------------------------------
# 4. TREND ANALYSIS (window functions: moving average, LAG)
# ------------------------------------------------------------------
tr = q("monthly_trend"); tr["month"] = pd.to_datetime(tr["month"]); tr.loc[:1, "moving_avg_3m"] = np.nan
print("\n=== 4. TREND (last 6 months) ===\n", tr.tail(6))

fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True, height_ratios=[3, 1.6])
ax[0].plot(tr["month"], tr["revenue"], marker="o", color="#B0B8C4", label="Monthly revenue")
ax[0].plot(tr["month"], tr["moving_avg_3m"], lw=3, color="#E76F51", label="3-month moving average (SQL window function)")
ax[0].set_title("Monthly Revenue Trend", fontweight="bold"); ax[0].legend()
g = tr["mom_growth_pct"]; ax[1].bar(tr["month"], g, width=20, color=np.where(g.fillna(0) >= 0, "#2A9D8F", "#E76F51"))
ax[1].axhline(0, color="black", lw=.8); ax[1].set_ylabel("MoM growth %")
plt.tight_layout(); plt.savefig(IMG + "3_trend.png", dpi=200); plt.close()

# ------------------------------------------------------------------
# 5. CUSTOMER VALUE (Pareto) + CORRELATION
# ------------------------------------------------------------------
cs = cust.sort_values("total_spend", ascending=False).reset_index(drop=True)
cs["cum_share"] = cs["total_spend"].cumsum() / cs["total_spend"].sum() * 100
cs["cust_pct"] = (cs.index + 1) / len(cs) * 100
top20 = cs.loc[cs["cust_pct"] <= 20, "total_spend"].sum() / cs["total_spend"].sum() * 100
q_share = cust.groupby("spend_quintile")["total_spend"].sum() / cust["total_spend"].sum() * 100
print(f"\n=== 5. PARETO ===\nTop 20% of customers = {top20:.1f}% of revenue")

item = q("item_level")
corr = item[["quantity", "discount", "list_price", "unit_cost", "line_revenue", "margin_pct"]].corr()
print("\nCorrelation matrix:\n", corr.round(2))

fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
axes[0].plot(cs["cust_pct"], cs["cum_share"], color="#264653", lw=3); axes[0].plot([0, 100], [0, 100], ls="--", color="gray")
axes[0].axvline(20, color="#E76F51", ls=":"); axes[0].axhline(top20, color="#E76F51", ls=":")
axes[0].annotate(f"Top 20% of customers\n= {top20:.0f}% of revenue", (20, top20), (35, top20 - 25), arrowprops=dict(arrowstyle="->"), fontsize=11)
axes[0].set_xlabel("% of customers (ranked by spend)"); axes[0].set_ylabel("Cumulative % of revenue"); axes[0].set_title("Customer Revenue Concentration (Pareto)", fontweight="bold")
sns.heatmap(corr, mask=np.triu(np.ones_like(corr, dtype=bool), 1), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=axes[1])
axes[1].set_title("Correlation Matrix (order line items)", fontweight="bold")
plt.tight_layout(); plt.savefig(IMG + "4_pareto_correlation.png", dpi=200); plt.close()

# ------------------------------------------------------------------
# 6. LINKEDIN DASHBOARD
# ------------------------------------------------------------------
fig = plt.figure(figsize=(16, 9))
fig.suptitle("Retail Database Analysis  |  SQL + Python", fontsize=20, fontweight="bold", y=.98)
gs = fig.add_gridspec(2, 2, hspace=.4, wspace=.28)
a1 = fig.add_subplot(gs[0, 0]); a1.barh(cat["category"][::-1], cat["revenue"][::-1] / 1e3, color="#264653")
a1.set_title("SQL GROUP BY: Revenue by Category (thousands)", fontweight="bold")
a2 = fig.add_subplot(gs[0, 1]); bb = a2.bar(cat["category"], cat["margin_pct"], color="#E9C46A"); a2.bar_label(bb, fmt="%.0f%%", padding=2)
a2.tick_params(axis="x", rotation=20); a2.set_title("Derived Metric: Profit Margin % by Category", fontweight="bold")
a3 = fig.add_subplot(gs[1, 0]); a3.plot(tr["month"], tr["revenue"], color="#B0B8C4"); a3.plot(tr["month"], tr["moving_avg_3m"], color="#E76F51", lw=3)
a3.set_title("Trend: Revenue + 3M Moving Average (SQL window)", fontweight="bold")
a4 = fig.add_subplot(gs[1, 1]); a4.plot(cs["cust_pct"], cs["cum_share"], color="#264653", lw=3); a4.plot([0, 100], [0, 100], ls="--", color="gray")
a4.set_title(f"Pareto: Top 20% of Customers = {top20:.0f}% of Revenue", fontweight="bold"); a4.set_xlabel("% of customers"); a4.set_ylabel("Cumulative % revenue")
plt.savefig(IMG + "0_linkedin_dashboard.png", dpi=200, bbox_inches="tight"); plt.close()

# ------------------------------------------------------------------
# INSIGHTS + EXPORTS
# ------------------------------------------------------------------
repeat = (cust["buyer_type"] == "Repeat").mean() * 100
print("\n=== KEY INSIGHTS ===")
print(f"- Revenue {kpi.revenue[0]:,.0f} | Profit {kpi.profit[0]:,.0f} | Orders {kpi.orders[0]:,} | AOV {kpi.avg_order_value[0]:,.0f}")
print(f"- Top category: {cat.category[0]} | Highest margin: {cat.sort_values('margin_pct').category.iloc[-1]} ({cat.margin_pct.max()}%) | Lowest: {cat.sort_values('margin_pct').category.iloc[0]} ({cat.margin_pct.min()}%)")
print(f"- Top 20% of customers = {top20:.1f}% of revenue | Repeat buyers: {repeat:.1f}% of customers")
print(f"- Corr discount vs margin: {corr.loc['discount','margin_pct']:.2f} | discount vs quantity: {corr.loc['discount','quantity']:.2f}")
q("sales_detail").to_csv("powerbi/sales_detail.csv", index=False)
cust.to_csv("powerbi/customer_value.csv", index=False)
print("\nExported powerbi/sales_detail.csv and powerbi/customer_value.csv")
con.close()
