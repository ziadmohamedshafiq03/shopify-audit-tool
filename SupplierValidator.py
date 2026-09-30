import hashlib
import io
import os
import threading
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import audit_engine as ae
import followup
import leads
from report import build_report

# ============================================================
#  SHOPIFY OVERSELL RISK AUDITOR v10
# ============================================================

st.set_page_config(page_title="Oversell Risk Audit", page_icon=":material/inventory_2:",
                   layout="wide", initial_sidebar_state="collapsed")


def get_setting(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


OPERATOR = get_setting("OPERATOR_NAME", "Ziad")
CALENDAR_LINK = get_setting("CALENDAR_LINK")
WEBHOOK_URL = get_setting("LEAD_WEBHOOK_URL")
HUBSPOT_TOKEN = get_setting("HUBSPOT_TOKEN")
for _k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "FROM_EMAIL", "OWNER_EMAIL", "CALENDAR_LINK"):
    if get_setting(_k) and not os.environ.get(_k):
        os.environ[_k] = get_setting(_k)   # followup.send_email reads env

# ============================================================
#  STYLE
# ============================================================
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--c-bg:#f6f6f7;--c-surface:#fff;--c-surface-sub:#fafbfb;--c-border:#e1e3e5;--c-border-strong:#c9cccf;--c-text:#202223;--c-text-sub:#6d7175;
--c-primary:#008060;--c-primary-hover:#006e52;--c-primary-active:#005e46;--c-primary-surface:#f1f8f5;
--c-critical:#e53935;--c-critical-text:#b3261e;--c-critical-surface:#fff4f4;--c-critical-border:#fbd0cd;
--c-warning:#e8a200;--c-warning-text:#7a5a00;--c-warning-surface:#fff8e6;--c-warning-border:#f5dc9a;
--c-info:#2c6ecb;--c-info-text:#1f5199;--c-info-surface:#ebf3fd;--c-info-border:#c4dbf7;
--c-pass:#008060;--c-pass-text:#00664d;--c-pass-surface:#f1f8f5;--c-pass-border:#b4dfcc;
--radius:8px;--radius-lg:12px;--shadow:0 1px 0 rgba(22,29,37,.05);--font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;--sticky-h:64px;--maxw:1120px}
html,body,[data-testid="stAppViewContainer"],[data-testid="stSidebar"],button,input,textarea,select,label,h1,h2,h3,h4,h5,h6{font-family:var(--font)!important}
h1,h2,h3{letter-spacing:-.01em;color:var(--c-text)}
[data-testid="stIconMaterial"]{font-family:'Material Symbols Rounded'!important}
#MainMenu,footer,[data-testid="stDecoration"],[data-testid="stToolbarActions"]{display:none!important}
[data-testid="stHeader"]{background:transparent}
[data-testid="stMainBlockContainer"],.block-container{max-width:var(--maxw);padding-top:2rem;padding-bottom:4rem}
body:has(.ov-sticky) [data-testid="stMainBlockContainer"],body:has(.ov-sticky) .block-container{padding-bottom:calc(var(--sticky-h) + 48px)!important}
[data-testid="stMain"]{scroll-behavior:smooth}
#get-report,[id="get-report"]{scroll-margin-top:24px}
[class*="st-key-card_"]{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius-lg);padding:20px 24px;box-shadow:var(--shadow)}
.ov-hero h1{font-size:30px;font-weight:700;margin:0 0 6px}
.ov-hero p{font-size:16px;color:var(--c-text-sub);max-width:72ch;margin:0 0 10px;line-height:1.6}
.ov-trust{display:flex;gap:8px;align-items:flex-start;font-size:13px;color:var(--c-text-sub);max-width:80ch}
.ov-trust svg{flex:none;margin-top:2px;color:var(--c-primary)}
.ov-section{margin:28px 0 12px}
.ov-section__title{font-size:18px;font-weight:650;color:var(--c-text);margin:0}
.ov-section__sub{font-size:14px;color:var(--c-text-sub);margin:4px 0 0;line-height:1.5}
.ov-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:8px 0 16px}
.ov-kpi{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius-lg);padding:16px 18px;box-shadow:var(--shadow);min-width:0}
.ov-kpi__label{font-size:12px;font-weight:600;color:var(--c-text-sub);text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px}
.ov-kpi__value{font-size:28px;font-weight:700;line-height:1.15;color:var(--c-text);font-variant-numeric:tabular-nums;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-kpi__meta{font-size:12.5px;color:var(--c-text-sub);margin:4px 0 0}
.ov-kpi--critical{box-shadow:inset 3px 0 0 var(--c-critical)}.ov-kpi--critical .ov-kpi__value{color:var(--c-critical)}
.ov-kpi--warning{box-shadow:inset 3px 0 0 var(--c-warning)}.ov-kpi--warning .ov-kpi__value{color:var(--c-warning-text)}
.ov-kpi--pass{box-shadow:inset 3px 0 0 var(--c-pass)}
.ov-badge{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;line-height:18px;border:1px solid transparent;white-space:nowrap}
.ov-badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.ov-badge--critical{background:var(--c-critical-surface);color:var(--c-critical-text);border-color:var(--c-critical-border)}
.ov-badge--warning{background:var(--c-warning-surface);color:var(--c-warning-text);border-color:var(--c-warning-border)}
.ov-badge--info{background:var(--c-info-surface);color:var(--c-info-text);border-color:var(--c-info-border)}
.ov-badge--pass{background:var(--c-pass-surface);color:var(--c-pass-text);border-color:var(--c-pass-border)}
.ov-score{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.ov-ring{--p:0;--ring:var(--c-pass);width:112px;height:112px;border-radius:50%;flex:none;display:grid;place-items:center;background:conic-gradient(var(--ring) calc(var(--p)*1%),var(--c-border) 0)}
.ov-ring--warning{--ring:var(--c-warning)}.ov-ring--critical{--ring:var(--c-critical)}
.ov-ring__inner{width:90px;height:90px;border-radius:50%;background:var(--c-surface);display:flex;flex-direction:column;align-items:center;justify-content:center}
.ov-ring__value{font-size:30px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;color:var(--c-text)}
.ov-ring__grade{font-size:12px;font-weight:600;color:var(--c-text-sub);margin-top:4px}
.ov-score__label{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--c-text-sub);margin:0}
.ov-score__headline{font-size:20px;font-weight:650;color:var(--c-text);margin:4px 0 0;line-height:1.35;max-width:60ch}
.ov-score__summary{font-size:14.5px;color:var(--c-text-sub);margin:6px 0 0;line-height:1.55;max-width:70ch}
.ov-counts{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.ov-findings{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius-lg);overflow:hidden}
.ov-finding{display:grid;grid-template-columns:88px 1fr auto;gap:8px 16px;align-items:start;padding:14px 18px;border-top:1px solid var(--c-border)}
.ov-finding:first-child{border-top:0}
.ov-finding__title{font-size:14.5px;font-weight:600;color:var(--c-text);margin:0}
.ov-finding__desc{font-size:13.5px;color:var(--c-text-sub);margin:2px 0 0;line-height:1.5}
.ov-sticky{position:fixed;left:0;right:0;bottom:0;z-index:999;background:var(--c-surface);border-top:1px solid var(--c-border);box-shadow:0 -2px 10px rgba(22,29,37,.06)}
.ov-sticky__inner{max-width:var(--maxw);min-height:var(--sticky-h);margin:0 auto;padding:10px 24px;box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:16px}
.ov-sticky__text{font-size:14.5px;color:var(--c-text)}.ov-sticky__text strong{color:var(--c-critical-text)}
a.ov-sticky__btn{background:var(--c-primary);color:#fff!important;text-decoration:none!important;font-weight:600;font-size:14px;padding:9px 16px;border-radius:var(--radius);white-space:nowrap}
a.ov-sticky__btn:hover{background:var(--c-primary-hover)}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"],.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{background:var(--c-primary)!important;border:1px solid var(--c-primary)!important;color:#fff!important;font-weight:600;border-radius:var(--radius);box-shadow:inset 0 -1px 0 rgba(0,0,0,.2)}
[data-testid="stBaseButton-primary"]:hover,[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:var(--c-primary-hover)!important;border-color:var(--c-primary-hover)!important}
[data-testid="stBaseButton-primary"]:active,[data-testid="stBaseButton-primaryFormSubmit"]:active{background:var(--c-primary-active)!important}
[data-testid^="stBaseButton-"]:focus-visible{box-shadow:0 0 0 2px #fff,0 0 0 4px var(--c-primary)!important;outline:none}
[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-secondaryFormSubmit"]{background:var(--c-surface)!important;border:1px solid var(--c-border-strong)!important;color:var(--c-text)!important;font-weight:500;border-radius:var(--radius)}
[data-testid="stBaseButton-secondary"]:hover{background:var(--c-surface-sub)!important;border-color:var(--c-text-sub)!important}
[data-testid="stForm"]{background:var(--c-surface);border:1px solid var(--c-border)!important;border-radius:var(--radius-lg);padding:20px 20px 16px}
[data-testid="stExpander"] details{background:var(--c-surface);border:1px solid var(--c-border);border-radius:var(--radius-lg)}
[data-testid="stExpander"] summary{font-weight:600;padding:12px 16px}
[data-testid="stExpander"] summary:hover{background:var(--c-surface-sub)}
[data-testid="stExpanderDetails"]{border-top:1px solid var(--c-border);padding-top:14px}
[data-testid="stFileUploaderDropzone"]{background:var(--c-surface-sub);border:1.5px dashed var(--c-border-strong);border-radius:var(--radius-lg);padding:24px}
[data-testid="stFileUploaderDropzone"]:hover{border-color:var(--c-primary);background:var(--c-primary-surface)}
[data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid var(--c-border)}
[data-baseweb="tab-border"]{display:none}
button[data-baseweb="tab"]{color:var(--c-text-sub);font-weight:500}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--c-text);font-weight:600}
[data-baseweb="tab-highlight"]{background:var(--c-primary)!important}
[data-testid="stDataFrame"],[data-testid="stPlotlyChart"]{border:1px solid var(--c-border);border-radius:var(--radius);background:var(--c-surface)}
@media (max-width:640px){[data-testid="stMainBlockContainer"],.block-container{padding-left:16px;padding-right:16px}
[class*="st-key-card_"]{padding:16px}.ov-kpi__value{font-size:24px}.ov-finding{grid-template-columns:1fr}
.ov-sticky__inner{padding:8px 16px}.ov-sticky__text{font-size:13px}}
</style>""", unsafe_allow_html=True)

# ============================================================
#  HTML HELPERS  (no indentation: Streamlit markdown turns it into code blocks)
# ============================================================
SEV = {"critical": "Critical", "warning": "Warning", "info": "Info", "pass": "Passed"}


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def usd(x: float, compact: bool = False) -> str:
    """Dollar string safe for HTML (&#36; avoids Streamlit's $...$ LaTeX parsing)."""
    if compact and abs(x) >= 1_000_000:
        s = f"{x / 1_000_000:.1f}M"
    elif compact and abs(x) >= 10_000:
        s = f"{x / 1_000:.1f}K"
    else:
        s = f"{x:,.0f}"
    return "&#36;" + s


def usd_md(x: float) -> str:
    return f"\\${x:,.0f}"


def section(title: str, sub: str = "") -> None:
    s = f'<p class="ov-section__sub">{sub}</p>' if sub else ""
    html(f'<div class="ov-section"><div class="ov-section__title" role="heading" aria-level="2">{title}</div>{s}</div>')


def kpi(label: str, value: str, meta: str = "", tone: str = "") -> str:
    cls = f"ov-kpi ov-kpi--{tone}" if tone else "ov-kpi"
    return (f'<div class="{cls}"><p class="ov-kpi__label">{label}</p><p class="ov-kpi__value">{value}</p>'
            f'<p class="ov-kpi__meta">{meta}</p></div>')


def badge(sev: str, text: str) -> str:
    return f'<span class="ov-badge ov-badge--{sev}">{text}</span>'


def score_block(score: int, grade: str, headline: str, summary: str, counts: dict) -> str:
    tone = "pass" if score >= 80 else "warning" if score >= 60 else "critical"
    chips = "".join(badge(s, f"{n} {SEV[s]}") for s, n in counts.items() if n)
    return (f'<div class="ov-score"><div class="ov-ring ov-ring--{tone}" style="--p:{int(score)}">'
            f'<div class="ov-ring__inner"><span class="ov-ring__value">{int(score)}</span>'
            f'<span class="ov-ring__grade">Grade {grade}</span></div></div>'
            f'<div style="flex:1;min-width:260px"><p class="ov-score__label">Audit Health Score</p>'
            f'<p class="ov-score__headline">{headline}</p><p class="ov-score__summary">{summary}</p>'
            f'<div class="ov-counts">{chips}</div></div></div>')


def sticky(text: str, button: str) -> None:
    html(f'<div class="ov-sticky"><div class="ov-sticky__inner"><span class="ov-sticky__text">{text}</span>'
         f'<a class="ov-sticky__btn" href="#get-report" target="_self">{button}</a></div></div>')


POLARIS_LAYOUT = dict(
    font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=13, color="#202223"),
    paper_bgcolor="#fff", plot_bgcolor="#fff", margin=dict(l=8, r=24, t=44, b=8),
    title=dict(x=0, xanchor="left", font=dict(size=15)),
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#e1e3e5", ticks="", automargin=True),
    yaxis=dict(showgrid=False, zeroline=False, ticks="", automargin=True),
    hoverlabel=dict(bgcolor="#fff", bordercolor="#c9cccf", font=dict(color="#202223")),
    showlegend=False, bargap=0.35, height=320)


def safe_chart(build, fallback_df=None) -> None:
    try:
        fig = build()
        fig.update_layout(**POLARIS_LAYOUT)
        st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
    except Exception:
        st.caption("Chart unavailable. Showing the underlying data instead.")
        if fallback_df is not None:
            st.dataframe(fallback_df, hide_index=True, width="stretch")


def send_report_email(to: str, subject: str, body: str, report_html: str) -> None:
    try:
        followup.send_email(to, subject, body, ("oversell_audit_report.html", report_html.encode(), "text/html"))
    except Exception:
        pass   # the report is already downloadable on screen; the cron sequence continues regardless


@st.cache_data(show_spinner=False, max_entries=8)
def load_file(data: bytes, name: str) -> pd.DataFrame:
    return ae.load_table(data, name)


def read_upload(upload, label: str):
    try:
        return load_file(upload.getvalue(), upload.name)
    except Exception as exc:
        st.error(f"We couldn't read **{upload.name}** ({label}): {exc}  \n"
                 "If it's an Excel file it may be password-protected. Re-export it as CSV (UTF-8) and upload again.")
        st.stop()


# ============================================================
#  SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("**Oversell Risk Audit**")
    st.caption("How it works")
    st.markdown("1. Upload your supplier's inventory feed\n2. Optionally add your Shopify product export\n"
                "3. Review findings and download the cleaned file")
    st.caption("Files are processed in memory and discarded when the session ends. "
               "Only the summary numbers you choose to send are stored.")
    if st.button("Start over", width="stretch"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
    st.divider()
    st.caption(f"Built by {escape(OPERATOR)} · Custom Shopify sync engineering  \nIndependent tool. Not affiliated with Shopify Inc.")

# ============================================================
#  HERO + UPLOAD
# ============================================================
LOCK = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"></rect>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>')
html('<div class="ov-hero"><h1>Find the products you\'re selling that your supplier can\'t ship.</h1>'
     '<p>Upload your supplier\'s inventory feed, and optionally your Shopify product export. In about a minute '
     'you\'ll see which live listings are out of stock at source, where quantities disagree, and what that '
     'exposure is worth each month, with every assumption shown.</p>'
     f'<div class="ov-trust">{LOCK}<span>Files are processed in memory and discarded when the session ends. '
     'No Shopify login or API access needed. We keep only the summary numbers you choose to send.</span></div></div>')

st.write("")
with st.container(key="card_upload"):
    up1, up2 = st.columns(2, gap="large")
    with up1:
        supplier_up = st.file_uploader("Supplier inventory feed (required)", type=["csv", "tsv", "txt", "xlsx", "xls"],
                                       help="CSV, TSV or Excel. Any column names: we detect SKU, quantity and price.")
    with up2:
        shopify_up = st.file_uploader("Shopify product export (optional)", type=["csv", "xlsx"],
                                      help="Shopify admin → Products → Export → CSV. Unlocks the live-listing cross-check.")
        st.caption("Add it to see which out-of-stock products are **still live** on your store.")

# ============================================================
#  EMPTY STATE
# ============================================================
if supplier_up is None:
    section("What the audit checks")
    checks = [
        ("critical", "Live listings your supplier can't fulfil", "Products active on Shopify while out of stock at source."),
        ("critical", "\"Continue selling when out of stock\"", "Variants that keep accepting orders at zero inventory."),
        ("warning", "Stock mismatches", "Shopify showing more (or fewer) units than your supplier has."),
        ("warning", "Selling below cost", "Retail prices lower than the supplier's wholesale cost."),
        ("info", "Feed hygiene", "Missing and duplicate SKUs, unreadable quantities, negative prices."),
    ]
    html('<div class="ov-findings">' + "".join(
        f'<div class="ov-finding">{badge(s, SEV[s])}<div><p class="ov-finding__title">{escape(t)}</p>'
        f'<p class="ov-finding__desc">{escape(d)}</p></div><div></div></div>' for s, t, d in checks) + '</div>')
    st.stop()

# ============================================================
#  LOAD + MAP COLUMNS
# ============================================================
raw_sup = read_upload(supplier_up, "supplier feed")
raw_shop = read_upload(shopify_up, "Shopify export") if shopify_up is not None else None
if raw_shop is not None and not ae.looks_like_shopify_export(raw_shop.columns):
    st.warning("The second file doesn't look like a Shopify product export (no *Handle* / *Variant SKU* columns). "
               "Check the mapping below.")

file_key = hashlib.md5(supplier_up.getvalue()[:200_000] + (shopify_up.getvalue()[:200_000] if shopify_up else b"")).hexdigest()[:10]
map_key = f"mapping_{file_key}"
if map_key not in st.session_state:
    st.session_state[map_key] = {
        "sup": ae.detect_columns(raw_sup.columns),
        "shop": ae.detect_columns(raw_shop.columns, ae.SHOPIFY_ROLES) if raw_shop is not None else None,
    }
mapping = st.session_state[map_key]

ROLE_LABELS = {"sku": "SKU", "qty": "Quantity", "price": "Retail price", "cost": "Cost / wholesale price",
               "title": "Product title", "vendor": "Vendor / brand", "status": "Status",
               "published": "Published", "policy": "Inventory policy"}
NONE = "— not in file —"
needs_attention = not mapping["sup"].get("sku") or not mapping["sup"].get("qty") or (
    mapping["shop"] is not None and not mapping["shop"].get("sku"))

summary = f"**{escape(supplier_up.name)}** · {len(raw_sup):,} rows"
if raw_shop is not None:
    summary += f" · Shopify export: **{escape(shopify_up.name)}** · {len(raw_shop):,} rows"
st.markdown(summary)

with st.expander("Column mapping" + (" — please check" if needs_attention else ""), expanded=needs_attention):
    with st.form(f"map_form_{file_key}", border=False):
        new = {"sup": {}, "shop": {} if mapping["shop"] is not None else None}
        blocks = [("sup", "Supplier feed", raw_sup, ("sku", "qty", "price", "cost", "title", "vendor"))]
        if raw_shop is not None:
            blocks.append(("shop", "Shopify export", raw_shop, ae.SHOPIFY_ROLES))
        for key, label, frame, roles in blocks:
            st.caption(label)
            cols = st.columns(3)
            opts = [NONE] + list(frame.columns)
            for i, role in enumerate(roles):
                cur = mapping[key].get(role)
                choice = cols[i % 3].selectbox(ROLE_LABELS[role], opts, index=opts.index(cur) if cur in opts else 0,
                                               key=f"sel_{file_key}_{key}_{role}")
                new[key][role] = None if choice == NONE else choice
        if st.form_submit_button("Confirm mapping", type="primary"):
            st.session_state[map_key] = new
            st.rerun()

if not mapping["sup"].get("sku"):
    st.error("Map a **SKU** column for the supplier feed to run the audit.")
    st.stop()
if mapping["shop"] is not None and not mapping["shop"].get("sku"):
    st.error("Map the **Variant SKU** column for the Shopify export to run the cross-check.")
    st.stop()

# ============================================================
#  CALIBRATION (doubles as lead qualification)
# ============================================================
section("Calibrate the estimate", "Three inputs turn counts into dollars. Every assumption is shown.")
c1, c2, c3 = st.columns(3)
band = c1.selectbox("Annual store revenue", list(ae.REVENUE_BANDS), index=None, placeholder="Select a range")
aov = c2.number_input("Average order value (\\$)", min_value=1.0, value=75.0, step=5.0)
sync_method = c3.selectbox("How you sync inventory today", list(ae.SYNC_METHODS), index=0)

with st.expander("More assumptions"):
    a1, a2, a3 = st.columns(3)
    stockouts = a1.number_input("Stockouts per at-risk SKU per month", 0.1, 10.0, 1.0, 0.1)
    support_cost = a2.number_input("Support cost per oversold order (\\$)", 0.0, 100.0, 8.0, 1.0)
    ad_spend = a3.number_input("Monthly ad spend (\\$, optional)", 0.0, 10_000_000.0, 0.0, 500.0)
    b1, b2, b3 = st.columns(3)
    low_threshold = b1.number_input("Low-stock threshold (units)", 1, 1000, 5, 1)
    chargeback_rate = b2.number_input("Chargeback rate on oversells (%)", 0.0, 50.0, 2.0, 0.5) / 100
    fee_pct = b3.number_input("Processor fee kept on refunds (%)", 0.0, 10.0, 2.9, 0.1) / 100

A = ae.Assumptions(annual_revenue=ae.REVENUE_BANDS.get(band, 2_500_000), aov=aov, sync_method=sync_method,
                   stockouts_per_month=stockouts, support_cost=support_cost, monthly_ad_spend=ad_spend,
                   low_stock_threshold=int(low_threshold), chargeback_rate=chargeback_rate, fee_pct=fee_pct)

# ============================================================
#  RUN AUDIT
# ============================================================
sup = ae.prepare_supplier(raw_sup, mapping["sup"])
stats = ae.audit_supplier(sup, A)
xref = None
if raw_shop is not None:
    shop = ae.prepare_shopify(raw_shop, mapping["shop"])
    xref = ae.cross_reference(sup, shop)
    if xref["matched"] == 0:
        st.warning("No SKUs matched between the two files. Check that **SKU** and **Variant SKU** are mapped to the "
                   "right columns. The results below use the supplier feed only.")
        xref = None
findings = ae.build_findings(stats, A, xref)
score, grade = ae.health_score(stats, A, xref)
money = ae.money_model(stats, A, xref) if band else None

if xref is not None:
    at_risk = xref["oversell"][[c for c in ("sku", "title", "vendor", "qty", "qty_sup", "price") if c in xref["oversell"]]]
elif stats.get("has_qty"):
    at_risk = sup[sup["qty"] <= 0][["sku", "title", "vendor", "qty", "price"]].dropna(axis=1, how="all")
else:
    at_risk = pd.DataFrame()
at_risk = at_risk.dropna(axis=1, how="all")
if "sku" in at_risk:
    at_risk = at_risk.assign(sku=at_risk["sku"].fillna("(no SKU)"))

oos_active = len(xref["oversell"]) if xref is not None else None
counts = {s: sum(1 for f in findings if f.severity == s) for s in ("critical", "warning", "info")}

# ============================================================
#  SUMMARY
# ============================================================
exposure_txt = usd(money["monthly_total"]) if money else None
if xref is not None and oos_active and score < 80:
    headline = f"{oos_active:,} live products can be ordered but can't be fulfilled."
    sub = "These listings are active on Shopify with zero stock at your supplier."
    if money:
        sub += f" At your stated order volume, that is an estimated {exposure_txt}/month in orders likely to be refunded or delayed."
elif xref is None and stats.get("has_qty") and stats["oos"]:
    headline = f"{stats['oos']:,} SKUs are out of stock at your supplier."
    sub = "Add your Shopify product export to see how many are still live and purchasable."
    if money:
        sub += f" If all of them are live, the exposure is up to {exposure_txt}/month."
elif score >= 80:
    mism = len(xref["overstated"]) + len(xref["missed"]) if xref is not None else stats.get("low", 0)
    headline = f"Health Score {score}/100. Your catalog is in good shape."
    sub = (f"We found {mism:,} minor mismatches. Your remaining exposure is timing: a supplier stockout that "
           "happens between syncs. Save this report as your baseline.")
else:
    headline = f"Health Score {score}/100. Some issues are worth fixing."
    sub = "Review the findings below, starting with anything marked critical."

st.write("")
with st.container(key="card_summary"):
    html(score_block(score, grade, escape(headline), sub, counts))

cards = [kpi("SKUs in feed", f"{stats['total']:,}", f"{stats['missing_sku']:,} without SKU" if stats["missing_sku"] else "")]
if stats.get("has_qty"):
    cards += [kpi("Out of stock at supplier", f"{stats['oos']:,}", f"{stats['oos'] / max(stats['total'], 1):.1%} of feed",
                  "critical" if stats["oos"] else "pass"),
              kpi(f"Low stock (&lt;{A.low_stock_threshold})", f"{stats['low']:,}", "watchlist", "warning" if stats["low"] else "")]
if xref is not None:
    cards.append(kpi("Live on Shopify but OOS", f"{oos_active:,}", f"of {xref['shopify_skus']:,} Shopify SKUs",
                     "critical" if oos_active else "pass"))
if money:
    meta = "upper bound · est. per month" if money["upper_bound"] else "est. per month"
    if money["capped"]:
        meta = "capped at 3% of revenue · verify inputs"
    cards.append(kpi("Est. monthly exposure", usd(money["monthly_total"], compact=True), meta,
                     "critical" if money["monthly_total"] else "pass"))
else:
    cards.append(kpi("Est. monthly exposure", "—", "Select your revenue range above"))
html('<div class="ov-kpis">' + "".join(cards) + "</div>")

# ============================================================
#  DETAIL TABS
# ============================================================
def affected_rows(f: ae.Finding) -> pd.DataFrame | None:
    frames = {}
    if xref is not None:
        frames = {"oversell": xref["oversell"], "continue": xref["continue_oos"], "margin": xref["negative_margin"],
                  "overstated": xref["overstated"], "missed": xref["missed"]}
        frames["orphaned"] = pd.DataFrame({"sku": xref["orphaned"]})
        frames["unlisted"] = pd.DataFrame({"sku": xref["not_in_shopify"]})
    if stats.get("has_qty"):
        frames["oos"] = sup[sup["qty"] <= 0]
        frames["low"] = sup[(sup["qty"] > 0) & (sup["qty"] < A.low_stock_threshold)]
        frames["negative"] = sup[sup["qty"] < 0]
    frames["dupes"] = sup[sup["sku"].notna() & sup["sku"].duplicated(keep=False)]
    df = frames.get(f.key)
    if df is None or df.empty:
        return None
    df = df.assign(sku=df["sku"].fillna("(no SKU)"))
    keep = [c for c in ("sku", "title", "vendor", "qty", "qty_sup", "price", "cost", "cost_sup", "price_sup") if c in df]
    return df[keep].dropna(axis=1, how="all").rename(columns={
        "sku": "SKU", "title": "Product", "vendor": "Vendor", "qty": "Shopify qty" if xref is not None and f.key != "oos" else "Qty",
        "qty_sup": "Supplier qty", "price": "Price", "cost": "Cost", "cost_sup": "Supplier cost", "price_sup": "Supplier price"})


BADGE_COLOR = {"critical": "red", "warning": "orange", "info": "blue", "pass": "green"}
tab_f, tab_c, tab_s, tab_l = st.tabs(["Findings", "Charts", "At-risk SKUs", "Cleaning log"])

with tab_f:
    for f in findings:
        label = f":{BADGE_COLOR[f.severity]}-badge[{SEV[f.severity]}] {f.title}" + (f" · {f.count:,}" if f.count else "")
        with st.expander(label, expanded=f.severity == "critical" and f is findings[0]):
            st.write(f.detail.replace("$", "\\$"))
            rows = affected_rows(f)
            if rows is not None:
                st.dataframe(rows.head(200), hide_index=True, width="stretch")
                if len(rows) > 200:
                    st.caption(f"Showing 200 of {len(rows):,}.")

with tab_c:
    ch1, ch2 = st.columns(2)
    if stats.get("has_qty"):
        dist = pd.DataFrame({"bucket": ["Out of stock (0)", f"Low (1–{A.low_stock_threshold - 1})",
                                        f"Healthy ({A.low_stock_threshold}+)", "Unreadable"],
                             "count": [stats["oos"], stats["low"], stats["healthy"], stats["unparseable_qty"]],
                             "color": ["#e53935", "#e8a200", "#008060", "#8c9196"]})
        dist = dist[dist["count"] > 0]
        with ch1:
            safe_chart(lambda: go.Figure(go.Bar(x=dist["count"], y=dist["bucket"], orientation="h",
                                                marker_color=dist["color"], text=dist["count"], textposition="outside"))
                       .update_layout(title="Supplier stock levels", yaxis=dict(autorange="reversed")), dist)
    with ch2:
        if len(at_risk) and "vendor" in at_risk and at_risk["vendor"].notna().any():
            by_vendor = at_risk["vendor"].fillna("Unknown").value_counts().head(10).sort_values()
            safe_chart(lambda: go.Figure(go.Bar(x=by_vendor.values, y=by_vendor.index, orientation="h",
                                                marker_color="#e53935", text=by_vendor.values, textposition="outside"))
                       .update_layout(title="At-risk SKUs by vendor"), by_vendor.rename("SKUs").reset_index())
        else:
            st.caption("Map a Vendor column to see where at-risk SKUs concentrate.")

with tab_s:
    if len(at_risk):
        st.caption("Live on Shopify and out of stock at your supplier." if xref is not None
                   else "Out of stock at your supplier. Add your Shopify export to see which are live.")
        st.dataframe(at_risk, hide_index=True, width="stretch",
                     column_config={"price": st.column_config.NumberColumn("Price", format="$%.2f")})
    else:
        st.success("No at-risk SKUs found.")

cleaned, clean_log = ae.clean_feed(raw_sup, mapping["sup"])
with tab_l:
    if clean_log:
        for line in clean_log:
            st.markdown(f"- {line}")
    else:
        st.caption("No changes were needed.")
    st.caption(f"Cleaned file: {len(cleaned):,} rows, original columns preserved.")

# ============================================================
#  EXPORT + REPORT GATE
# ============================================================
supplier_count = int(sup["vendor"].nunique()) if sup["vendor"].notna().any() else 0
lead_stats = {
    "health_score": score, "grade": grade,
    "total_skus": stats["total"], "oos_count": stats.get("oos", 0), "low_count": stats.get("low", 0),
    "oos_active_count": oos_active if oos_active is not None else stats.get("oos", 0),
    "shopify_export_uploaded": xref is not None,
    "active_skus": xref["shopify_skus"] if xref is not None else None,
    "mismatch_count": len(xref["overstated"]) + len(xref["missed"]) if xref is not None else None,
    "unmapped_shopify": len(xref["orphaned"]) if xref is not None else None,
    "unmapped_supplier": len(xref["not_in_shopify"]) if xref is not None else None,
    "monthly_exposure": round(money["monthly_total"]) if money else 0,
    "monthly_exposure_conservative": round(money["conservative_total"]) if money else 0,
    "exposure_upper_bound": money["upper_bound"] if money else None,
    "supplier_count": supplier_count,
}

section("Take this with you")
e1, e2 = st.columns([1, 1.25], gap="large")
with e1:
    with st.container(key="card_export"):
        st.markdown("**Cleaned supplier file**")
        st.caption("Empty and duplicate-SKU rows removed, prices and quantities normalised. Original columns kept.")
        buf = io.StringIO()
        cleaned.to_csv(buf, index=False)
        st.download_button("Download cleaned CSV", buf.getvalue(), file_name="cleaned_feed.csv", mime="text/csv",
                           on_click="ignore", width="stretch")
        st.caption("You'll need to repeat this each time your supplier sends a new file.")

with e2:
    with st.container(key="card_report"):
        st.subheader("Get the full audit report", anchor="get-report")
        lead = st.session_state.get("report_lead")
        if not lead:
            st.caption("A report with your Health Score, every at-risk SKU, stock mismatches, unmapped products "
                       "and the assumptions behind each number. Easy to forward to your ops lead or supplier.")
            with st.form("report_gate", border=False):
                g1, g2 = st.columns(2)
                first_name = g1.text_input("First name")
                email = g2.text_input("Work email", placeholder="you@yourstore.com")
                store_url = st.text_input("Store URL", placeholder="yourstore.com")
                go_btn = st.form_submit_button("Email me the report", type="primary", width="stretch")
                st.caption("Sent once, plus up to three short follow-ups. Unsubscribe any time.")
            if go_btn:
                if not first_name.strip():
                    st.error("Please add your first name.")
                elif not leads.valid_email(email):
                    st.error("Please enter a valid email address.")
                elif not store_url.strip():
                    st.error("Please add your store URL.")
                else:
                    record = leads.save_lead({
                        "first_name": first_name.strip(), "email": email, "store_url": store_url,
                        "context": "report_gate", "revenue_band": band or "", "sync_method": sync_method,
                        "aov": aov, "stats": lead_stats,
                    }, WEBHOOK_URL, HUBSPOT_TOKEN)
                    st.session_state["report_lead"] = record
                    st.rerun()
        else:
            report_html = build_report(store_url=lead.get("store_url", ""), supplier_file=supplier_up.name,
                                       shopify_file=shopify_up.name if shopify_up else None, stats=stats, xref=xref,
                                       money=money, findings=findings, score=score, grade=grade, a=A,
                                       at_risk=at_risk, operator=OPERATOR, calendar_link=CALENDAR_LINK)
            if followup.smtp_configured() and not st.session_state.get("report_emailed"):
                subj, body = followup.render(0, lead)
                threading.Thread(target=send_report_email, args=(lead["email"], subj, body, report_html),
                                 daemon=True).start()
                leads.update_followups({lead["email"]: [0]})   # day-0 handled here, cron continues from day 1
                st.session_state["report_emailed"] = True
            sent = st.session_state.get("report_emailed")
            st.success(f"Your report is ready{' and a copy is on its way to ' + lead['email'] if sent else ''}.")
            r1, r2 = st.columns(2)
            r1.download_button("Download report (HTML)", report_html, file_name="oversell_audit_report.html",
                               mime="text/html", type="primary", on_click="ignore", width="stretch")
            r2.download_button("At-risk SKUs (CSV)", at_risk.to_csv(index=False), file_name="at_risk_skus.csv",
                               mime="text/csv", on_click="ignore", width="stretch")
            st.caption("Open the report in your browser and use Print → Save as PDF for a PDF copy.")

            if not st.session_state.get("qualified"):
                with st.form("qualify", border=False):
                    st.markdown("**Two optional questions** so any advice fits your setup:")
                    q1, q2 = st.columns(2)
                    n_sup = q1.number_input("Number of suppliers", 1, 500, max(supplier_count, 1))
                    feed = q2.selectbox("How your supplier sends inventory",
                                        ["Emailed file", "FTP / SFTP", "API", "Portal login only", "Other"])
                    if st.form_submit_button("Save"):
                        leads.save_lead({**lead, "supplier_count": int(n_sup), "feed_delivery": feed}, WEBHOOK_URL, HUBSPOT_TOKEN)
                        st.session_state["qualified"] = True
                        st.rerun()

# ============================================================
#  SERVICE CTA
# ============================================================
lead = st.session_state.get("report_lead")
small_store = band == "Under $250k"
st.write("")
with st.container(key="card_cta"):
    cta1, cta2 = st.columns([1.6, 1], gap="large", vertical_alignment="center")
    with cta1:
        st.markdown("#### Close the gap between your supplier and your storefront")
        st.markdown("I build a dedicated sync engine for your supplier feeds (FTP, API, emailed files or portal "
                    "exports). It updates Shopify inventory every 15 minutes and alerts you when a feed fails. "
                    "**Flat project fee, you own the code, no per-SKU or monthly subscription.**")
        st.caption("We'll go through this audit together, and I'll tell you honestly whether a custom build makes "
                   "sense for you, including when it doesn't.")
    with cta2:
        if small_store:
            st.caption("At your current size an off-the-shelf app is usually enough. Start with the fixes in your "
                       "report: switch off *Continue selling when out of stock* and unpublish the at-risk SKUs.")
        elif CALENDAR_LINK:
            st.link_button("Book a 20-minute feasibility review", CALENDAR_LINK, type="primary", width="stretch")
            st.caption("Prefer email? Reply to your report and tell me how your supplier sends inventory.")
        elif st.session_state.get("review_requested"):
            st.success("Thanks. I'll email you within one business day to find a time.")
        else:
            with st.form("review_request", border=False):
                r_email = st.text_input("Work email", value=lead["email"] if lead else "")
                if st.form_submit_button("Request a feasibility review", type="primary", width="stretch"):
                    if leads.valid_email(r_email):
                        leads.save_lead({**(lead or {}), "email": r_email, "context": "review_request",
                                         "revenue_band": band or "", "sync_method": sync_method, "stats": lead_stats,
                                         "review_requested": True}, WEBHOOK_URL, HUBSPOT_TOKEN)
                        st.session_state["review_requested"] = True
                        st.rerun()
                    else:
                        st.error("Please enter a valid email address.")

# ============================================================
#  STICKY BAR (points to the report gate, not the sales form)
# ============================================================
if not lead:
    if score < 80 and (oos_active or stats.get("oos")):
        n = oos_active if xref is not None else stats["oos"]
        what = "live listings out of stock at supplier" if xref is not None else "SKUs out of stock at supplier"
        exp = f" · est. <strong>{usd(money['monthly_total'])}/mo</strong> exposure" if money else ""
        sticky(f"<strong>{n:,}</strong> {what}{exp}", "Get the full report")
    else:
        sticky(f"Health Score <strong style='color:#00664d'>{score}/100</strong> · Save your baseline report", "Get the report")
