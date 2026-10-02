"""Regenerate the test fixtures: python tests/fixtures/generate.py"""
import csv
import os
import random

random.seed(7)
HERE = os.path.dirname(os.path.abspath(__file__))
vendors = ["Northwind Supply", "Harbor Wholesale", "Crest Distribution"]
kinds = ["Linen Throw", "Ceramic Mug", "Oak Serving Board", "Canvas Tote", "Wool Blanket",
         "Glass Carafe", "Cotton Apron", "Brass Candle Holder", "Stoneware Bowl", "Jute Rug"]
colors = ["Sand", "Slate", "Olive", "Ivory", "Rust", "Navy"]

rows = []
for i in range(1, 181):
    sku = f"HG-{1000 + i}"
    title = f"{random.choice(colors)} {random.choice(kinds)}"
    cost = round(random.uniform(6, 60), 2)
    r = random.random()
    qty = 0 if r < 0.10 else random.randint(1, 4) if r < 0.22 else random.randint(5, 250)
    rows.append({"sku": sku, "title": title, "vendor": random.choice(vendors), "cost": cost, "qty": qty})

# Supplier feed: messy on purpose
with open(os.path.join(HERE, "sample_supplier_feed.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Item SKU", "Product Name", "Brand", "Wholesale Price", "Qty On Hand"])
    for i, r in enumerate(rows):
        qty = r["qty"]
        if i % 47 == 0:
            qty = "Out of stock"
        w.writerow([r["sku"] if i % 61 else "", r["title"], r["vendor"], f"${r['cost']:,.2f}", qty])
    w.writerow([rows[3]["sku"], rows[3]["title"], rows[3]["vendor"], f"${rows[3]['cost']}", rows[3]["qty"]])
    for i in range(1, 9):   # supplier products not yet listed
        w.writerow([f"HG-NEW-{i}", f"{random.choice(colors)} {random.choice(kinds)}", vendors[0], "$12.00", 40])

# Shopify export: listed products, stale quantities
with open(os.path.join(HERE, "sample_shopify_export.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Handle", "Title", "Vendor", "Status", "Variant SKU", "Variant Inventory Qty",
                "Variant Inventory Policy", "Variant Price", "Cost per item"])
    for i, r in enumerate(rows[:170]):
        stale = r["qty"] + random.choice([0, 0, 0, 0, 3, 8]) if r["qty"] else random.choice([0, 0, 6, 14])
        if i % 29 == 5:
            stale = 0
        price = round(r["cost"] * random.uniform(1.8, 2.6), 2) if i % 53 else round(r["cost"] * 0.9, 2)
        policy = "continue" if i % 37 == 2 else "deny"
        status = "draft" if i % 41 == 0 else "active"
        w.writerow([r["title"].lower().replace(" ", "-") + f"-{i}", r["title"], r["vendor"], status,
                    r["sku"], stale, policy, price, r["cost"]])
    for i in range(1, 6):   # on the store but gone from the feed
        w.writerow([f"legacy-item-{i}", f"Legacy Item {i}", vendors[1], "active", f"HG-OLD-{i}", 3, "deny", 29.0, 11.0])
print("ok")
