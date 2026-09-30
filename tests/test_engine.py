import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import audit_engine as ae
import followup
import leads
from report import build_report

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return ae.load_table(f.read(), name)


@pytest.fixture
def audit():
    raw = _load("sample_supplier_feed.csv")
    shop_raw = _load("sample_shopify_export.csv")
    a = ae.Assumptions()
    sup = ae.prepare_supplier(raw, ae.detect_columns(raw.columns))
    shop = ae.prepare_shopify(shop_raw, ae.detect_columns(shop_raw.columns, ae.SHOPIFY_ROLES))
    stats = ae.audit_supplier(sup, a)
    return raw, sup, shop, stats, ae.cross_reference(sup, shop), a


# --- loading & detection -------------------------------------------------

def test_load_semicolon_cp1252_uppercase_ext():
    data = "Référence;Quantité;Prix\nA1;3;9,99\nA2;0;12,50\n".encode("cp1252")
    df = ae.load_table(data, "FEED.CSV")
    assert list(df.columns) == ["Référence", "Quantité", "Prix"]
    assert ae.parse_numeric(df["Prix"]).tolist() == [9.99, 12.5]


def test_detection_prefers_exact_and_skips_traps():
    cols = ["Item Name", "Compare At Price", "Price", "Stock Status", "Qty Available", "SKU", "Shipping Cost"]
    m = ae.detect_columns(cols)
    assert m["sku"] == "SKU"
    assert m["qty"] == "Qty Available"
    assert m["price"] == "Price"
    assert m["cost"] is None


def test_detection_on_shopify_export(audit):
    shop_raw = _load("sample_shopify_export.csv")
    m = ae.detect_columns(shop_raw.columns, ae.SHOPIFY_ROLES)
    assert m["sku"] == "Variant SKU" and m["qty"] == "Variant Inventory Qty"
    assert m["price"] == "Variant Price" and m["policy"] == "Variant Inventory Policy"
    assert ae.looks_like_shopify_export(shop_raw.columns)


def test_parse_quantity_text_flags():
    q = ae.parse_quantity(pd.Series(["Out of stock", "12 units", "-3", "In stock", None]))
    assert q.iloc[0] == 0 and q.iloc[1] == 12 and q.iloc[2] == -3
    assert pd.isna(q.iloc[3]) and pd.isna(q.iloc[4])


def test_normalize_sku():
    s = ae.normalize_sku(pd.Series([" ab-1 ", "12345.0", "'00123", "", None]))
    assert s.iloc[0] == "AB-1" and s.iloc[1] == "12345" and s.iloc[2] == "00123"
    assert s.iloc[3:].isna().all()


# --- audit logic -----------------------------------------------------------

def test_supplier_stats_do_not_double_count(audit):
    _, sup, _, stats, _, _ = audit
    assert stats["oos"] + stats["low"] + stats["healthy"] + stats["unparseable_qty"] == stats["total"]
    assert stats["missing_sku"] == 3
    assert stats["duplicate_sku_rows"] == 2


def test_cross_reference_buckets(audit):
    _, sup, shop, _, x, _ = audit
    assert x["matched"] > 0
    assert len(x["oversell"]) > 0
    # every oversell SKU is active on Shopify and OOS at the supplier
    sup_q = sup.dropna(subset=["sku"]).drop_duplicates("sku").set_index("sku")["qty"]
    for sku in x["oversell"]["sku"]:
        assert sup_q[sku] <= 0
    assert set(x["orphaned"]) >= {f"HG-OLD-{i}" for i in range(1, 6)}
    assert {f"HG-NEW-{i}" for i in range(1, 9)} <= set(x["not_in_shopify"])
    assert len(x["negative_margin"]) > 0


def test_draft_products_are_not_oversell():
    sup = pd.DataFrame({"sku": ["A", "B"], "title": None, "vendor": None, "qty": [0.0, 0.0], "price": None, "cost": None})
    shop = pd.DataFrame({"sku": ["A", "B"], "title": None, "vendor": None, "qty": [5.0, 5.0], "price": [10.0, 10.0],
                         "cost": None, "active": [True, False], "continue_selling": [False, False]})
    x = ae.cross_reference(sup, shop)
    assert x["oversell"]["sku"].tolist() == ["A"]


def test_money_model_is_bounded_and_labelled(audit):
    _, _, _, stats, x, a = audit
    m = ae.money_model(stats, a, x)
    assert not m["upper_bound"]
    assert m["revenue_at_risk"] <= a.annual_revenue / 12 * a.exposure_cap_pct + 1e-6
    assert m["conservative_total"] == pytest.approx(m["monthly_total"] / 2)
    assert m["ad_waste"] == 0          # hidden until ad spend is entered
    assert ae.money_model(stats, a)["upper_bound"]


def test_money_cap_applies():
    stats = {"total": 10, "has_qty": True, "oos": 10}
    m = ae.money_model(stats, ae.Assumptions(annual_revenue=12_000_000, aov=50))
    assert m["capped"] and m["revenue_at_risk"] == pytest.approx(30_000)


def test_faster_sync_improves_score_and_exposure(audit):
    _, _, _, stats, x, a = audit
    fast = ae.Assumptions(sync_method="Custom script (hourly or faster)")
    assert ae.health_score(stats, fast, x)[0] > ae.health_score(stats, a, x)[0]
    assert ae.money_model(stats, fast, x)["monthly_total"] < ae.money_model(stats, a, x)["monthly_total"]


def test_clean_feed_perfect_score_path():
    df = pd.DataFrame({"SKU": ["A", "B"], "Qty": ["10", "20"], "Price": ["$5.00", "$6.00"]})
    m = ae.detect_columns(df.columns)
    sup = ae.prepare_supplier(df, m)
    stats = ae.audit_supplier(sup, ae.Assumptions())
    score, grade = ae.health_score(stats, ae.Assumptions(sync_method="Custom script (hourly or faster)"))
    assert (score, grade) == (100, "A")
    f = ae.build_findings(stats, ae.Assumptions())
    assert f[0].severity == "pass"


def test_clean_feed(audit):
    raw = audit[0]
    m = ae.detect_columns(raw.columns)
    cleaned, log = ae.clean_feed(raw, m)
    assert list(cleaned.columns) == list(raw.columns)
    assert cleaned[m["sku"]].notna().all()
    assert not cleaned[m["sku"]].duplicated().any()
    assert (cleaned[m["qty"]].dropna() >= 0).all()
    assert any("no SKU" in line for line in log)


def test_findings_ranked(audit):
    _, _, _, stats, x, a = audit
    f = ae.build_findings(stats, a, x)
    ranks = [ae.SEVERITY_ORDER[i.severity] for i in f]
    assert ranks == sorted(ranks)
    assert f[0].severity == "critical"


def test_report_escapes_and_renders(audit):
    _, sup, _, stats, x, a = audit
    x["oversell"].loc[0, "title"] = "<script>alert(1)</script>"
    html = build_report(store_url="shop.com", supplier_file="f.csv", shopify_file="s.csv", stats=stats, xref=x,
                        money=ae.money_model(stats, a, x), findings=ae.build_findings(stats, a, x), score=50,
                        grade="F", a=a, at_risk=x["oversell"], operator="Ziad", calendar_link="https://cal.com/x")
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "Methodology" in html and "https://cal.com/x" in html


# --- leads & follow-ups ------------------------------------------------------

def test_lead_scoring():
    hot = {"email": "ops@brand.com", "revenue_band": "$5M - $20M", "sync_method": "Manual CSV import",
           "stats": {"oos_active_count": 25, "shopify_export_uploaded": True}}
    cold = {"email": "a@gmail.com", "revenue_band": "Under $250k", "stats": {"oos_active_count": 40}}
    assert leads.score_lead(hot)[1] == "hot"
    assert leads.score_lead(cold)[1] == "cold"


def test_save_lead_upserts(tmp_path, monkeypatch):
    monkeypatch.setattr(leads, "LEADS_FILE", str(tmp_path / "leads.json"))
    leads.save_lead({"email": "A@x.com ", "store_url": "https://Shop.com/products", "stats": {}})
    leads.update_followups({"a@x.com": [0]})
    leads.save_lead({"email": "a@x.com", "store_url": "shop.com", "stats": {"health_score": 40}})
    data = leads.load_leads()
    assert len(data) == 1
    assert data[0]["store_url"] == "shop.com" and data[0]["stats"]["health_score"] == 40
    assert data[0]["followups_sent"] == [0]


def test_followup_cadence_and_render():
    now = datetime.now(timezone.utc)
    lead = {"email": "a@b.com", "tier": "warm", "first_name": "sam lee", "store_url": "shop.com",
            "first_captured_at": (now - timedelta(days=3, hours=1)).isoformat(), "followups_sent": [0],
            "stats": {"health_score": 42, "oos_active_count": 13, "monthly_exposure": 1234}}
    assert followup.due_steps(lead, now) == [1, 3]
    subject, body = followup.render(3, lead)
    assert "shop.com" in subject and "$1,234" in body and body.startswith("Sam,")
    assert followup.due_steps({**lead, "call_booked": True}, now) == []
    assert followup.due_steps({**lead, "tier": "cold"}, now) == []
