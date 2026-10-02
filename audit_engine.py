"""Pure audit logic for the Shopify Oversell Risk Auditor.

Nothing in here imports Streamlit, so every function can be unit tested and
reused (e.g. by the follow-up email script or a future API).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

# ============================================================
#  FILE LOADING
# ============================================================

def load_table(data: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV/TSV/Excel file into an all-string DataFrame.

    Supplier feeds are messy: BOMs, Windows-1252 encodings, semicolon
    delimiters, upper-case extensions. Handle all of them.
    """
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    else:
        text = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not decode file. Please save it as UTF-8 CSV.")
        sample = text[:20000]
        try:
            sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
        df = pd.read_csv(io.StringIO(text), dtype=str, sep=sep, keep_default_na=False,
                         na_values=[""], skip_blank_lines=True)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    if df.empty or len(df.columns) == 0:
        raise ValueError("The file has no data rows.")
    return df


# ============================================================
#  COLUMN DETECTION
# ============================================================

# Ordered by preference. Exact (normalized) matches win over substring matches,
# and earlier synonyms win over later ones.
COLUMN_SYNONYMS: dict[str, list[str]] = {
    "sku": ["variant sku", "sku", "item sku", "sku code", "product sku", "item number",
            "item no", "part number", "mpn", "product id", "product code", "item code", "item"],
    "qty": ["variant inventory qty", "available", "quantity available", "qty available",
            "available quantity", "on hand", "on_hand", "qty on hand", "stock quantity",
            "inventory quantity", "inventory", "quantity", "qty", "stock level", "stock"],
    "price": ["variant price", "price", "retail price", "msrp", "sale price", "selling price"],
    "cost": ["cost per item", "variant cost", "wholesale price", "wholesale", "cost price",
             "unit cost", "cost", "dealer price", "net price"],
    "title": ["title", "product title", "product name", "name", "description", "item name"],
    "vendor": ["vendor", "brand", "supplier", "manufacturer"],
    "status": ["status", "product status"],
    "published": ["published", "published on online store"],
    "policy": ["variant inventory policy", "inventory policy", "continue selling when out of stock"],
}

# Substrings that disqualify a header from a role even if a synonym matches.
COLUMN_EXCLUDES: dict[str, list[str]] = {
    "qty": ["min", "max", "reorder", "incoming", "committed", "policy", "tracker", "status",
            "location", "unavailable", "price", "date"],
    "price": ["compare", "cost", "wholesale", "unit price per", "currency"],
    "cost": ["shipping", "freight"],
    "sku": ["barcode", "count", "qty"],
    "title": ["seo", "variant", "image", "option"],
    "status": ["stock status", "inventory status"],
    "vendor": ["id", "sku"],
}


def _norm(header: str) -> str:
    return re.sub(r"[\s_\-\.]+", " ", str(header).strip().lower())


def detect_column(columns, role: str, taken: Optional[set] = None) -> Optional[str]:
    taken = taken or set()
    excludes = COLUMN_EXCLUDES.get(role, [])
    candidates = [c for c in columns if c not in taken
                  and not any(x in _norm(c) for x in excludes)]
    norm = {c: _norm(c) for c in candidates}
    for syn in COLUMN_SYNONYMS[role]:
        for c in candidates:
            if norm[c] == syn:
                return c
    for syn in COLUMN_SYNONYMS[role]:
        for c in candidates:
            if re.search(rf"\b{re.escape(syn)}\b", norm[c]):
                return c
    return None


def detect_columns(columns, roles=("sku", "qty", "price", "cost", "title", "vendor")) -> dict:
    """Map each role to one column, never assigning a column twice."""
    mapping, taken = {}, set()
    for role in roles:
        col = detect_column(columns, role, taken)
        mapping[role] = col
        if col:
            taken.add(col)
    return mapping


SHOPIFY_ROLES = ("sku", "qty", "price", "cost", "title", "vendor", "status", "published", "policy")


def looks_like_shopify_export(columns) -> bool:
    norm = {_norm(c) for c in columns}
    return "handle" in norm and ("variant sku" in norm or "sku" in norm)


# ============================================================
#  VALUE PARSING
# ============================================================

_TEXT_ZERO = {"out of stock", "oos", "no", "false", "sold out", "discontinued", "n/a", "na", "none", "-"}
_TEXT_IN = {"in stock", "yes", "true", "available"}


def parse_numeric(series: pd.Series) -> pd.Series:
    """Parse prices/quantities like '$1,234.50', '12 units', '€9,99'."""
    s = series.astype("string").str.strip()
    # European decimal comma: "9,99" (no dot, exactly 2 decimals)
    euro = s.str.fullmatch(r"-?[^\d-]*\d+,\d{2}[^\d]*", na=False)
    s = s.where(~euro, s.str.replace(",", ".", regex=False))
    s = s.str.replace(r"[^\d\.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def parse_quantity(series: pd.Series) -> pd.Series:
    """Quantities; textual flags ('Out of stock') become 0, 'In stock' stays NaN (unknown count)."""
    lower = series.astype("string").str.strip().str.lower()
    q = parse_numeric(series)
    q = q.mask(lower.isin(_TEXT_ZERO), 0)
    return q


def normalize_sku(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.upper()
    s = s.str.replace(r"^'+", "", regex=True)          # Excel text-prefix
    s = s.str.replace(r"\.0$", "", regex=True)         # 12345.0 from Excel numerics
    return s.mask(s.isin(["", "NAN", "NONE", "NULL"]))


# ============================================================
#  RESULT TYPES
# ============================================================

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "pass": 3}


@dataclass
class Finding:
    severity: str          # critical | warning | info | pass
    title: str
    detail: str
    count: int = 0
    samples: list = field(default_factory=list)
    key: str = ""


REVENUE_BANDS = {
    "Under $250k": 150_000,
    "$250k - $1M": 600_000,
    "$1M - $5M": 2_500_000,
    "$5M - $20M": 10_000_000,
    "$20M+": 25_000_000,
}

# Exposure window in days: how long a supplier stockout stays live on the store.
SYNC_METHODS = {
    "Manual CSV import": 1.0,
    "Shopify app": 0.5,
    "Supplier's own app/integration": 0.5,
    "Custom script (hourly or faster)": 0.1,
    "No sync / ad hoc": 2.0,
}


@dataclass
class Assumptions:
    """Inputs for the money model. Every number shown to a merchant traces back here."""
    annual_revenue: float = 2_500_000
    aov: float = 75.0
    sync_method: str = "Manual CSV import"
    stockouts_per_month: float = 1.0        # how often each at-risk SKU re-enters stockout
    support_cost: float = 8.0               # support time per oversold order
    fee_pct: float = 0.029                  # processor fee kept on refunds
    fee_fixed: float = 0.30
    chargeback_rate: float = 0.02
    chargeback_fee: float = 15.0
    monthly_ad_spend: float = 0.0           # 0 = ad waste hidden
    low_stock_threshold: int = 5
    overstated_weight: float = 0.25         # a stock mismatch is a partial oversell risk
    exposure_cap_pct: float = 0.03          # never show > 3% of monthly revenue

    @property
    def window_days(self) -> float:
        return SYNC_METHODS.get(self.sync_method, 1.0)


# ============================================================
#  SUPPLIER AUDIT
# ============================================================

def prepare_supplier(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["sku"] = normalize_sku(df[mapping["sku"]]) if mapping.get("sku") else pd.NA
    out["title"] = df[mapping["title"]] if mapping.get("title") else pd.NA
    out["vendor"] = df[mapping["vendor"]] if mapping.get("vendor") else pd.NA
    nan = pd.Series(float("nan"), index=df.index, dtype="float64")
    out["qty"] = parse_quantity(df[mapping["qty"]]) if mapping.get("qty") else nan
    out["price"] = parse_numeric(df[mapping["price"]]) if mapping.get("price") else nan
    out["cost"] = parse_numeric(df[mapping["cost"]]) if mapping.get("cost") else nan
    for col in ("qty", "price", "cost"):
        out[col] = out[col].astype("float64")
    return out


def prepare_shopify(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = prepare_supplier(df, mapping)
    if mapping.get("status"):
        st = df[mapping["status"]].astype("string").str.strip().str.lower()
        out["active"] = st.eq("active") | st.isna()
    elif mapping.get("published"):
        pub = df[mapping["published"]].astype("string").str.strip().str.lower()
        out["active"] = pub.isin(["true", "yes", "1"]) | pub.isna()
    else:
        out["active"] = True
    if mapping.get("policy"):
        out["continue_selling"] = df[mapping["policy"]].astype("string").str.strip().str.lower().eq("continue")
    else:
        out["continue_selling"] = False
    # Shopify exports put the product-level Status/Title/Vendor only on the first
    # row of each product; variant rows inherit from it.
    for col in ("title", "vendor"):
        if out[col].notna().any():
            out[col] = out[col].ffill()
    return out[out["sku"].notna()].copy()


def audit_supplier(sup: pd.DataFrame, a: Assumptions) -> dict:
    total = len(sup)
    qty = sup["qty"]
    has_qty = qty.notna().any()
    stats = {"total": total, "has_qty": bool(has_qty)}
    if has_qty:
        stats["oos"] = int((qty <= 0).sum())
        stats["low"] = int(((qty > 0) & (qty < a.low_stock_threshold)).sum())
        stats["negative"] = int((qty < 0).sum())
        stats["unparseable_qty"] = int(qty.isna().sum())
        stats["healthy"] = total - stats["oos"] - stats["low"] - stats["unparseable_qty"]
    sku = sup["sku"]
    stats["missing_sku"] = int(sku.isna().sum())
    dup_mask = sku.notna() & sku.duplicated(keep=False)
    stats["duplicate_sku_rows"] = int(dup_mask.sum())
    stats["duplicate_sku_samples"] = sku[dup_mask].drop_duplicates().head(5).tolist()
    for col in ("price", "cost"):
        s = sup[col]
        if s.notna().any():
            stats[f"{col}_negative"] = int((s < 0).sum())
            stats[f"{col}_zero"] = int((s == 0).sum())
    return stats


# ============================================================
#  CROSS REFERENCE (Supplier feed x Shopify export)
# ============================================================

def cross_reference(sup: pd.DataFrame, shop: pd.DataFrame) -> dict:
    s = sup[sup["sku"].notna()].drop_duplicates("sku", keep="first").set_index("sku")
    p = shop.drop_duplicates("sku", keep="first").set_index("sku")
    for frame in (s, p):
        for col in ("qty", "price", "cost"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    joined = p.join(s[["qty", "cost", "price"]], how="left", rsuffix="_sup")
    in_both = joined["qty_sup"].notna() | joined.index.isin(s.index)

    sup_oos = joined["qty_sup"] <= 0
    shop_qty = joined["qty"]
    shop_sells = shop_qty.isna() | (shop_qty > 0) | joined["continue_selling"]
    oversell = joined[in_both & joined["active"] & sup_oos & shop_sells]
    continue_oos = joined[in_both & joined["continue_selling"] & sup_oos]
    overstated = joined[in_both & shop_qty.notna() & joined["qty_sup"].notna()
                        & (shop_qty > joined["qty_sup"]) & ~sup_oos]
    missed = joined[in_both & joined["active"] & shop_qty.notna() & (shop_qty <= 0)
                    & (joined["qty_sup"] > 0)]
    supplier_cost = joined["cost_sup"].fillna(joined["price_sup"])
    negative_margin = joined[in_both & joined["price"].notna() & supplier_cost.notna()
                             & (joined["price"] > 0) & (joined["price"] < supplier_cost)]
    not_in_shopify = s.index.difference(p.index)
    orphaned = p.index.difference(s.index)

    def sample(frame, n=8):
        return frame.reset_index().head(n).to_dict("records")

    return {
        "matched": int(in_both.sum()),
        "shopify_skus": len(p),
        "supplier_skus": len(s),
        "oversell": oversell.reset_index(),
        "continue_oos": continue_oos.reset_index(),
        "overstated": overstated.reset_index(),
        "overstated_units": float((overstated["qty"] - overstated["qty_sup"]).sum()) if len(overstated) else 0.0,
        "missed": missed.reset_index(),
        "negative_margin": negative_margin.reset_index(),
        "not_in_shopify": list(not_in_shopify),
        "orphaned": list(orphaned),
        "samples": {"oversell": sample(oversell), "missed": sample(missed)},
    }


# ============================================================
#  MONEY MODEL (conservative, every input exposed)
# ============================================================

def money_model(stats: dict, a: Assumptions, xref: Optional[dict] = None) -> dict:
    """30-day exposure estimate.

    v  = (R/12 / AOV) / S / 30            orders per SKU per day (uniform spread)
    N  = oversell SKUs + overstated SKUs x overstated_weight
    O  = N x v x W x E                    oversold orders per month
    revenue_at_risk = O x AOV             revenue likely to be refunded (not lost profit)
    direct_cost     = O x (fee% x AOV + fee_fixed + support + cb_rate x (cb_fee + AOV))
    ad_waste        = A x (N/S) x (W x E / 30)

    Without a Shopify export we treat every supplier-OOS SKU as live, which is an
    upper bound and is labelled as such (`upper_bound`).
    """
    monthly_rev = a.annual_revenue / 12
    if xref is not None:
        S = max(xref["shopify_skus"], 1)
        N = len(xref["oversell"]) + len(xref["overstated"]) * a.overstated_weight
        upper_bound = False
    else:
        S = max(stats["total"], 1)
        N = stats.get("oos", 0) if stats.get("has_qty") else 0
        upper_bound = True
    v = (monthly_rev / max(a.aov, 1)) / S / 30
    W, E = a.window_days, a.stockouts_per_month
    orders = N * v * W * E
    revenue_at_risk = orders * a.aov
    per_order = (a.fee_pct * a.aov + a.fee_fixed + a.support_cost
                 + a.chargeback_rate * (a.chargeback_fee + a.aov))
    direct_cost = orders * per_order
    ad_waste = a.monthly_ad_spend * (N / S) * min(W * E / 30, 1.0)

    cap = monthly_rev * a.exposure_cap_pct
    capped = revenue_at_risk > cap
    if capped:
        scale = cap / revenue_at_risk
        revenue_at_risk, direct_cost, orders = cap, direct_cost * scale, orders * scale
    total = revenue_at_risk + direct_cost + ad_waste
    return {
        "at_risk_skus": N,
        "orders_per_sku_day": v,
        "oversold_orders": orders,
        "revenue_at_risk": revenue_at_risk,
        "direct_cost": direct_cost,
        "ad_waste": ad_waste,
        "monthly_total": total,
        "conservative_total": total * 0.5,
        "annual_total": total * 12,
        "capped": capped,
        "upper_bound": upper_bound,
    }


# ============================================================
#  FINDINGS + HEALTH SCORE
# ============================================================

def build_findings(stats: dict, a: Assumptions, xref: Optional[dict] = None) -> list[Finding]:
    f: list[Finding] = []
    total = max(stats["total"], 1)

    if xref is not None:
        n = len(xref["oversell"])
        if n:
            f.append(Finding("critical", "Live products your supplier can't fulfil",
                             f"{n:,} SKUs are active and purchasable on Shopify but out of stock at your supplier. "
                             "Every order on these is an oversell.", n,
                             xref["oversell"]["sku"].head(8).tolist(), "oversell"))
        n = len(xref["continue_oos"])
        if n:
            f.append(Finding("critical", "\"Continue selling when out of stock\" is on",
                             f"{n:,} variant(s) out of stock at the supplier have inventory policy set to 'continue', so Shopify "
                             "will keep taking orders at zero stock.", n,
                             xref["continue_oos"]["sku"].head(8).tolist(), "continue"))
        n = len(xref["negative_margin"])
        if n:
            f.append(Finding("critical", "Selling below supplier cost",
                             f"{n:,} SKUs are priced on Shopify below the supplier's cost.", n,
                             xref["negative_margin"]["sku"].head(8).tolist(), "margin"))
        n = len(xref["overstated"])
        if n:
            f.append(Finding("warning", "Shopify shows more stock than your supplier has",
                             f"{n:,} SKUs overstate inventory by {xref['overstated_units']:,.0f} units in total.", n,
                             xref["overstated"]["sku"].head(8).tolist(), "overstated"))
        n = len(xref["missed"])
        if n:
            f.append(Finding("warning", "Sold out on Shopify, in stock at supplier",
                             f"{n:,} SKUs show 0 on your store while your supplier has stock — lost sales.", n,
                             xref["missed"]["sku"].head(8).tolist(), "missed"))
        n = len(xref["orphaned"])
        if n:
            f.append(Finding("warning", "Shopify SKUs missing from the supplier feed",
                             f"{n:,} SKUs on your store don't appear in this feed (discontinued or SKU mismatch).",
                             n, xref["orphaned"][:8], "orphaned"))
        n = len(xref["not_in_shopify"])
        if n:
            f.append(Finding("info", "Supplier products not listed on your store",
                             f"{n:,} supplier SKUs aren't on Shopify — potential catalogue expansion.", n,
                             xref["not_in_shopify"][:8], "unlisted"))
    elif stats.get("has_qty") and stats["oos"]:
        f.append(Finding("critical", "Out-of-stock products at supplier",
                         f"{stats['oos']:,} SKUs ({stats['oos'] / total:.0%} of the feed) have zero stock. If they are "
                         "still live on Shopify, each order is an oversell. Upload your Shopify export to confirm.",
                         stats["oos"], key="oos"))

    if stats.get("has_qty"):
        if stats["low"]:
            f.append(Finding("warning", f"Low stock (under {a.low_stock_threshold} units)",
                             f"{stats['low']:,} SKUs can sell out between two manual syncs.", stats["low"], key="low"))
        if stats["negative"]:
            f.append(Finding("warning", "Negative inventory values",
                             f"{stats['negative']:,} rows report negative stock — a sign of supplier data errors.",
                             stats["negative"], key="negative"))
        if stats["unparseable_qty"]:
            f.append(Finding("warning", "Unreadable quantities",
                             f"{stats['unparseable_qty']:,} rows have a stock value we couldn't read as a number.",
                             stats["unparseable_qty"], key="unparseable"))
    else:
        f.append(Finding("warning", "No stock column detected",
                         "We couldn't find a quantity column. Map it manually under 'Column mapping'.", key="noqty"))

    if stats["missing_sku"]:
        f.append(Finding("warning", "Rows without a SKU",
                         f"{stats['missing_sku']:,} rows have no SKU and can't be matched to Shopify.",
                         stats["missing_sku"], key="nosku"))
    if stats["duplicate_sku_rows"]:
        f.append(Finding("warning", "Duplicate SKUs",
                         f"{stats['duplicate_sku_rows']:,} rows share a SKU with another row — imports will overwrite each other.",
                         stats["duplicate_sku_rows"], stats["duplicate_sku_samples"], "dupes"))
    for col, label in (("price", "prices"), ("cost", "costs")):
        if stats.get(f"{col}_negative"):
            f.append(Finding("warning", f"Negative {label}", f"{stats[f'{col}_negative']:,} rows.",
                             stats[f"{col}_negative"], key=f"{col}neg"))
        if stats.get(f"{col}_zero"):
            f.append(Finding("info", f"Zero {label}", f"{stats[f'{col}_zero']:,} rows have a $0 {col}.",
                             stats[f"{col}_zero"], key=f"{col}zero"))

    if not any(x.severity in ("critical", "warning") for x in f):
        f.append(Finding("pass", "No critical issues found", "This feed is in good shape.", key="pass"))
    f.sort(key=lambda x: (SEVERITY_ORDER[x.severity], -x.count))
    return f


def health_score(stats: dict, a: Assumptions, xref: Optional[dict] = None) -> tuple[int, str]:
    """Start at 100 and subtract capped penalties proportional to the share of catalogue affected.

    OOS-active 40 | mismatch 25 | unmapped 15 | data quality 10 | sync method 10
    """
    total = max(stats["total"], 1)
    score = 100.0

    def pen(share, weight, cap):
        return min(share * weight, cap)

    if xref is not None:
        base = max(xref["shopify_skus"], 1)
        score -= pen((len(xref["oversell"]) + len(xref["continue_oos"])) / base, 300, 40)
        score -= pen((len(xref["overstated"]) + len(xref["missed"]) + len(xref["negative_margin"])) / base, 60, 25)
        unmapped = len(xref["orphaned"]) / base + len(xref["not_in_shopify"]) / max(xref["supplier_skus"], 1)
        score -= pen(unmapped, 30, 15)
    elif stats.get("has_qty"):
        score -= pen(stats["oos"] / total, 200, 40)      # proxy: assume OOS SKUs are live
    if stats.get("has_qty"):
        if xref is None:                                 # with a Shopify export, mismatches cover this
            score -= pen(stats["low"] / total, 50, 10)
        dq = stats["missing_sku"] + stats["duplicate_sku_rows"] + stats["unparseable_qty"] + stats["negative"]
    else:
        score -= 25
        dq = stats["missing_sku"] + stats["duplicate_sku_rows"]
    score -= pen(dq / total, 100, 10)
    score -= {1.0: 10, 2.0: 10, 0.5: 5}.get(a.window_days, 0)
    score = int(round(max(0, min(100, score))))
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
    return score, grade


# ============================================================
#  CLEAN EXPORT
# ============================================================

def clean_feed(df: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, list[str]]:
    """Return a cleaned copy of the ORIGINAL columns plus a log of what changed."""
    out = df.copy()
    log = []
    for c in out.columns:
        if out[c].dtype == object or str(out[c].dtype).startswith("string"):
            out[c] = out[c].astype("string").str.strip()
    if mapping.get("sku"):
        skus = normalize_sku(out[mapping["sku"]])
        n = int(skus.isna().sum())
        if n:
            out = out[skus.notna()]
            log.append(f"Removed {n:,} rows with no SKU.")
        before = len(out)
        out = out[~normalize_sku(out[mapping["sku"]]).duplicated(keep="first")]
        if before - len(out):
            log.append(f"Removed {before - len(out):,} duplicate-SKU rows (kept first occurrence).")
    for role in ("price", "cost"):
        col = mapping.get(role)
        if col:
            parsed = parse_numeric(out[col])
            changed = int((parsed.astype("string") != out[col]).fillna(False).sum())
            out[col] = parsed.round(2)
            if changed:
                log.append(f"Normalised {changed:,} values in '{col}' (currency symbols, separators).")
    col = mapping.get("qty")
    if col:
        parsed = parse_quantity(out[col])
        neg = int((parsed < 0).sum())
        parsed = parsed.clip(lower=0)
        out[col] = parsed.astype("Int64")
        if neg:
            log.append(f"Clamped {neg:,} negative quantities to 0.")
    return out.reset_index(drop=True), log


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(x) for x in findings]
