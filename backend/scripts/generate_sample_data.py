"""Generates realistic sample CSVs for the Hive demo dataset.

Produces dim_customers, dim_products, and fact_sales covering 24 months
across 4 regions so the NL pipeline has meaningful data to query:
sales by region, declining-revenue products, top customer growth, margin
trends, etc.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).resolve().parents[1] / "sample_data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
CATEGORIES = {
    "Cloud Storage": (15, 60),
    "Analytics Suite": (80, 300),
    "Security Add-on": (20, 90),
    "Collaboration Tools": (10, 40),
    "API Platform": (50, 200),
}

PRODUCT_NAMES = {
    "Cloud Storage": ["StoreX Basic", "StoreX Pro", "StoreX Archive"],
    "Analytics Suite": ["InsightBoard", "InsightBoard Plus", "MetricStream"],
    "Security Add-on": ["ShieldGuard", "AccessLock", "ThreatScan"],
    "Collaboration Tools": ["TeamSync", "BoardRoom", "NoteHive"],
    "API Platform": ["ConnectAPI", "GatewayPro", "IntegrateHub"],
}


def gen_customers(n: int = 220) -> list[dict]:
    customers = []
    start = date(2023, 1, 1)
    for i in range(1, n + 1):
        signup = start + timedelta(days=random.randint(0, 700))
        customers.append({
            "customer_id": i,
            "customer_name": f"Customer {i:04d}",
            "region": random.choices(REGIONS, weights=[35, 30, 25, 10])[0],
            "segment": random.choices(SEGMENTS, weights=[20, 35, 45])[0],
            "signup_date": signup.isoformat(),
        })
    return customers


def gen_products() -> list[dict]:
    products = []
    pid = 1
    for category, (low, high) in CATEGORIES.items():
        for name in PRODUCT_NAMES[category]:
            products.append({
                "product_id": pid,
                "product_name": name,
                "category": category,
                "unit_price": round(random.uniform(low, high), 2),
            })
            pid += 1
    return products


def gen_sales(customers: list[dict], products: list[dict]) -> list[dict]:
    rows = []
    order_id = 1
    start = date(2024, 1, 1)
    months = 24

    # give a subset of products a declining trend and one region a Q2 margin dip
    declining_products = {p["product_id"] for p in random.sample(products, 3)}
    growth_customers = {c["customer_id"] for c in random.sample(customers, 25)}

    for month_offset in range(months):
        month_start = date(start.year + (start.month - 1 + month_offset) // 12,
                            (start.month - 1 + month_offset) % 12 + 1, 1)
        days_in_month = 28
        base_orders = random.randint(140, 220)

        for _ in range(base_orders):
            customer = random.choice(customers)
            product = random.choice(products)
            order_day = month_start + timedelta(days=random.randint(0, days_in_month - 1))
            quantity = random.randint(1, 12)

            trend_factor = 1.0
            if product["product_id"] in declining_products:
                trend_factor = max(0.35, 1.15 - 0.035 * month_offset)
            if customer["customer_id"] in growth_customers:
                trend_factor *= 1.0 + 0.03 * month_offset

            unit_price = product["unit_price"]
            amount = round(unit_price * quantity * trend_factor, 2)

            cost_ratio = random.uniform(0.45, 0.65)
            if order_day.month in (4, 5, 6) and order_day.year == 2024:
                # margin compression in Q2 2024 in APAC
                if customer["region"] == "APAC":
                    cost_ratio += 0.18
            cost = round(amount * cost_ratio, 2)

            rows.append({
                "order_id": order_id,
                "order_date": order_day.isoformat(),
                "customer_id": customer["customer_id"],
                "product_id": product["product_id"],
                "region": customer["region"],
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
                "cost": cost,
                "margin": round(amount - cost, 2),
            })
            order_id += 1
    return rows


def write_csv(rows: list[dict], filename: str) -> None:
    path = OUT_DIR / filename
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        for row in rows:
            writer.writerow(row)
    print(f"wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    customers = gen_customers()
    products = gen_products()
    sales = gen_sales(customers, products)

    write_csv(customers, "dim_customers.csv")
    write_csv(products, "dim_products.csv")
    write_csv(sales, "fact_sales.csv")
