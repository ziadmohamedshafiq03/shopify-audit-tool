"""Standalone, print-ready HTML audit report (the email-gated lead magnet).

Open in a browser and use Print -> Save as PDF for a PDF copy.
"""
from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd

from audit_engine import Assumptions, Finding

SEV_LABEL = {"critical": "Critical", "warning": "Warning", "info": "Info", "pass": "Passed"}

CSS = """
*{box-sizing:border-box}body{font-family:Inter,-apple-system,'Segoe UI',sans-serif;color:#202223;background:#f6f6f7;margin:0;padding:32px 16px;line-height:1.5}
.page{max-width:860px;margin:0 auto;background:#fff;border:1px solid #e1e3e5;border-radius:12px;padding:40px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:18px;margin:32px 0 12px;padding-top:20px;border-top:1px solid #e1e3e5}
.sub{color:#6d7175;font-size:14px;margin:0}
.score{display:flex;gap:20px;align-items:center;margin:24px 0}
.ring{width:96px;height:96px;border-radius:50%;display:grid;place-items:center;flex:none}
.ring div{width:76px;height:76px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center}
.ring b{font-size:26px;line-height:1}.ring span{font-size:11px;color:#6d7175}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{border:1px solid #e1e3e5;border-radius:8px;padding:12px 14px}.kpi p{margin:0}
.kpi .l{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:#6d7175}
.kpi .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}.crit .v{color:#e53935}
.f{display:grid;grid-template-columns:84px 1fr;gap:12px;padding:12px 0;border-top:1px solid #e1e3e5}
.f:first-child{border-top:0}.f p{margin:0}.f .t{font-weight:600}.f .d{color:#6d7175;font-size:13.5px}
.f .s{font-size:12px;color:#6d7175;font-family:ui-monospace,monospace;margin-top:4px}
.b{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid}
.b-critical{background:#fff4f4;color:#b3261e;border-color:#fbd0cd}.b-warning{background:#fff8e6;color:#7a5a00;border-color:#f5dc9a}
.b-info{background:#ebf3fd;color:#1f5199;border-color:#c4dbf7}.b-pass{background:#f1f8f5;color:#00664d;border-color:#b4dfcc}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e1e3e5}
th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6d7175}td.n{text-align:right;font-variant-numeric:tabular-nums}
.note{font-size:12.5px;color:#6d7175}.cta{background:#f1f8f5;border:1px solid #b4dfcc;border-radius:8px;padding:16px 20px;margin-top:28px}
.cta a{color:#008060;font-weight:600}
@media print{body{background:#fff;padding:0}.page{border:0;padding:0}h2{break-after:avoid}.f,tr{break-inside:avoid}}
"""


def _money(x: float) -> str:
    return f"${x:,.0f}"


def _ring_color(score: int) -> str:
    return "#008060" if score >= 80 else "#e8a200" if score >= 60 else "#e53935"


def build_report(*, store_url: str, supplier_file: str, shopify_file: str | None, stats: dict,
                 xref: dict | None, money: dict | None, findings: list[Finding], score: int, grade: str,
                 a: Assumptions, at_risk: pd.DataFrame, operator: str, calendar_link: str = "") -> str:
    e = escape
    ring = _ring_color(score)
    kpis = [("SKUs in feed", f"{stats['total']:,}", "")]
    if stats.get("has_qty"):
        kpis += [("Out of stock at supplier", f"{stats['oos']:,}", "crit"), ("Low stock", f"{stats['low']:,}", "")]
    if xref is not None:
        kpis += [("Live on Shopify but OOS", f"{len(xref['oversell']):,}", "crit"),
                 ("Stock mismatches", f"{len(xref['overstated']):,}", "")]
    if money:
        kpis.append(("Est. monthly exposure", _money(money["monthly_total"]), "crit"))
    kpi_html = "".join(f'<div class="kpi {c}"><p class="l">{e(l)}</p><p class="v">{v}</p></div>' for l, v, c in kpis)

    f_html = ""
    for f in findings:
        samples = f'<p class="s">e.g. {e(", ".join(map(str, f.samples[:8])))}</p>' if f.samples else ""
        f_html += (f'<div class="f"><div><span class="b b-{f.severity}">{SEV_LABEL[f.severity]}</span></div>'
                   f'<div><p class="t">{e(f.title)}</p><p class="d">{e(f.detail)}</p>{samples}</div></div>')

    table = ""
    if at_risk is not None and len(at_risk):
        cols = [c for c in ("sku", "title", "vendor", "qty", "qty_sup", "price") if c in at_risk.columns]
        heads = {"sku": "SKU", "title": "Product", "vendor": "Vendor", "qty": "Shopify qty",
                 "qty_sup": "Supplier qty", "price": "Price"}
        if xref is None:
            heads["qty"] = "Supplier qty"
        rows = ""
        for _, r in at_risk[cols].head(200).iterrows():
            cells = ""
            for c in cols:
                v = r[c]
                if pd.isna(v):
                    cells += "<td>—</td>"
                elif c in ("qty", "qty_sup"):
                    cells += f'<td class="n">{float(v):,.0f}</td>'
                elif c == "price":
                    cells += f'<td class="n">${float(v):,.2f}</td>'
                else:
                    cells += f"<td>{e(str(v))}</td>"
            rows += f"<tr>{cells}</tr>"
        more = f'<p class="note">Showing 200 of {len(at_risk):,}. The full list is in the CSV download.</p>' if len(at_risk) > 200 else ""
        table = (f"<h2>At-risk SKUs ({len(at_risk):,})</h2><table><thead><tr>"
                 + "".join(f"<th>{heads[c]}</th>" for c in cols) + f"</tr></thead><tbody>{rows}</tbody></table>{more}")

    money_html = ""
    if money:
        bound = ("<p class='note'><b>Upper bound:</b> no Shopify export was provided, so every SKU that is out of stock "
                 "at the supplier is assumed to be live on the store.</p>") if money["upper_bound"] else ""
        capped = "<p class='note'>Revenue at risk was capped at 3% of monthly revenue. Verify your inputs.</p>" if money["capped"] else ""
        ad = (f"<tr><td>Ad spend on unfulfillable listings</td><td class='n'>{_money(money['ad_waste'])}</td></tr>"
              if a.monthly_ad_spend else "")
        money_html = f"""<h2>Estimated 30-day exposure</h2>
<table><tbody>
<tr><td>Orders likely to be oversold</td><td class="n">{money['oversold_orders']:,.1f}</td></tr>
<tr><td>Revenue likely to be refunded</td><td class="n">{_money(money['revenue_at_risk'])}</td></tr>
<tr><td>Direct cost (fees, support, chargebacks)</td><td class="n">{_money(money['direct_cost'])}</td></tr>{ad}
<tr><th>Total (base) / conservative</th><th class="n">{_money(money['monthly_total'])} / {_money(money['conservative_total'])}</th></tr>
</tbody></table>{bound}{capped}
<h2>Methodology &amp; assumptions</h2>
<p class="note">Orders per SKU per day <i>v</i> = (monthly revenue ÷ AOV) ÷ active SKUs ÷ 30.
At-risk SKUs <i>N</i> = live-but-OOS SKUs + {a.overstated_weight:g} × stock-mismatch SKUs.
Oversold orders = N × v × exposure window × stockouts per month.
Direct cost per oversold order = {a.fee_pct:.1%} × AOV + ${a.fee_fixed:.2f} + ${a.support_cost:.0f} support + {a.chargeback_rate:.0%} × (${a.chargeback_fee:.0f} + AOV).
Conservative = base × 0.5.</p>
<table><tbody>
<tr><td>Annual revenue (band midpoint)</td><td class="n">{_money(a.annual_revenue)}</td></tr>
<tr><td>Average order value</td><td class="n">{_money(a.aov)}</td></tr>
<tr><td>Current sync method → exposure window</td><td class="n">{e(a.sync_method)} → {a.window_days:g} day(s)</td></tr>
<tr><td>Stockouts per at-risk SKU per month</td><td class="n">{a.stockouts_per_month:g}</td></tr>
<tr><td>Monthly ad spend</td><td class="n">{_money(a.monthly_ad_spend) if a.monthly_ad_spend else "not provided"}</td></tr>
</tbody></table>"""

    cta_link = f' <a href="{e(calendar_link)}">Book a 20-minute feasibility review →</a>' if calendar_link else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oversell Risk Audit — {e(store_url or supplier_file)}</title><style>{CSS}</style></head><body><div class="page">
<h1>Oversell Risk Audit</h1>
<p class="sub">{e(store_url or "Your store")} · {date.today():%d %B %Y} · Supplier feed: {e(supplier_file)}{" · Shopify export: " + e(shopify_file) if shopify_file else ""}</p>
<div class="score"><div class="ring" style="background:conic-gradient({ring} {score}%,#e1e3e5 0)"><div><b>{score}</b><span>Grade {grade}</span></div></div>
<div><p class="note" style="margin:0;text-transform:uppercase;font-weight:600;letter-spacing:.04em">Audit Health Score</p>
<p style="margin:4px 0 0">{"Critical issues need attention before your next sync." if score < 60 else "Some issues are worth fixing." if score < 80 else "Your catalog is in good shape."}</p></div></div>
<div class="kpis">{kpi_html}</div>
<h2>Findings</h2>{f_html}
{money_html}
{table}
<div class="cta"><b>Close the gap between your supplier and your storefront.</b><br>
<span class="note">A dedicated sync engine updates Shopify inventory from your supplier feeds every 15 minutes and alerts you when a feed fails.
Flat project fee, you own the code.</span>{cta_link}</div>
<p class="note" style="margin-top:24px">Prepared by {e(operator)} · Independent tool, not affiliated with Shopify Inc. · Estimates are based on the inputs above and are not financial advice.</p>
</div></body></html>"""
