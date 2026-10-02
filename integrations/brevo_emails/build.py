"""Build the four Brevo follow-up emails as email-safe HTML.

    python integrations/brevo_emails/build.py

Writes day0.html … day7.html next to this file. Paste each into Brevo:
Automations → Send an email → Create from scratch → HTML custom code.

Email-client rules followed: table layout, inline styles, 600px max width, no web fonts
required, no background images, bulletproof button, hidden preheader. Brevo fills
{{ contact.X }} placeholders; {{ unsubscribe }} is Brevo's unsubscribe link.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CALENDAR = "https://YOUR-CALENDAR-LINK"   # replace before building, or edit in Brevo
SENDER = "Ziad"

GREEN, RED, INK, SUB, LINE, BG = "#008060", "#e53935", "#202223", "#6d7175", "#e1e3e5", "#f6f6f7"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Helvetica,Arial,sans-serif"


def p(text: str, style: str = "") -> str:
    return (f'<p style="margin:0 0 16px;font-family:{FONT};font-size:15px;line-height:1.6;'
            f'color:{INK};{style}">{text}</p>')


def button(label: str, href: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px;">
<tr><td bgcolor="{GREEN}" style="border-radius:8px;">
<a href="{href}" target="_blank" style="display:inline-block;padding:12px 22px;font-family:{FONT};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;">{label}</a>
</td></tr></table>"""


def stat(number: str, label: str, color: str = RED) -> str:
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 24px;border:1px solid {LINE};border-left:4px solid {color};border-radius:8px;">
<tr><td style="padding:18px 20px;">
<div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:{SUB};">{label}</div>
<div style="font-family:{FONT};font-size:34px;font-weight:700;line-height:1.2;color:{color};">{number}</div>
</td></tr></table>"""


def steps(items: list[tuple[str, str]]) -> str:
    rows = ""
    for i, (title, text) in enumerate(items, 1):
        rows += f"""<tr>
<td valign="top" width="36" style="padding:0 12px 16px 0;"><div style="width:28px;height:28px;line-height:28px;border-radius:14px;background:#f1f8f5;color:{GREEN};font-family:{FONT};font-size:14px;font-weight:700;text-align:center;">{i}</div></td>
<td valign="top" style="padding:0 0 16px;font-family:{FONT};font-size:15px;line-height:1.55;color:{INK};"><strong>{title}</strong><br><span style="color:{SUB};">{text}</span></td>
</tr>"""
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 8px;">{rows}</table>'


def bars() -> str:
    def bar(label, width_pct, color, note):
        return f"""<tr><td style="padding:0 0 4px;font-family:{FONT};font-size:13px;color:{SUB};">{label}</td></tr>
<tr><td style="padding:0 0 14px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="{width_pct}%" bgcolor="{color}" style="height:12px;border-radius:6px;font-size:0;line-height:0;">&nbsp;</td>
<td style="padding-left:10px;font-family:{FONT};font-size:13px;font-weight:600;color:{INK};white-space:nowrap;">{note}</td>
</tr></table></td></tr>"""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:4px 0 24px;border:1px solid {LINE};border-radius:8px;"><tr><td style="padding:18px 20px 6px;">
<div style="font-family:{FONT};font-size:12px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:{SUB};padding-bottom:12px;">Time a stockout stays live on your store</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{bar("Daily CSV import", 80, RED, "up to 24 hours")}
{bar("Typical sync app", 40, "#e8a200", "up to 12 hours")}
{bar("15-minute sync engine", 2, GREEN, "15 minutes")}
</table></td></tr></table>"""


def wrap(preheader: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting"><title>Oversell Risk Audit</title></head>
<body style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{BG}"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:12px;">
<tr><td style="padding:18px 28px;border-bottom:1px solid {LINE};font-family:{FONT};font-size:14px;font-weight:700;color:{INK};">
<span style="display:inline-block;width:8px;height:8px;border-radius:4px;background:{GREEN};margin-right:8px;"></span>Oversell Risk Audit</td></tr>
<tr><td style="padding:28px 28px 8px;">
{body}
<p style="margin:8px 0 24px;font-family:{FONT};font-size:15px;line-height:1.5;color:{INK};">— {SENDER}<br><span style="color:{SUB};font-size:13px;">Custom Shopify inventory sync · I read every reply myself</span></p>
</td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;"><tr><td style="padding:16px 28px;font-family:{FONT};font-size:12px;line-height:1.5;color:{SUB};text-align:center;">
You received this because you ran the Oversell Risk Audit for {{{{ contact.STORE_URL }}}}.<br>
<a href="{{{{ unsubscribe }}}}" style="color:{SUB};">Unsubscribe</a> · Independent tool, not affiliated with Shopify Inc.
</td></tr></table>
</td></tr></table></body></html>
"""


NAME = '{{ contact.FIRSTNAME | default : "there" }}'
STORE = "{{ contact.STORE_URL }}"

EMAILS = {
    "day0": ("Your oversell audit for {{ contact.STORE_URL }}",
             "The headline from your audit, and what to look at first.",
             p(f"Hi {NAME},")
             + p(f"Thanks for running the audit on <strong>{STORE}</strong>. Here's the headline:")
             + stat("{{ contact.OOS_ACTIVE }}", "Live products out of stock at your supplier")
             + p("Every order on these listings is an order you can't ship — a refund, a support ticket, "
                 "and sometimes a chargeback.")
             + p("Your report lists each SKU and every assumption behind the numbers, so you can adjust them "
                 "to your real figures. If anything looks off, just reply and I'll check it.")),
    "day1": ("Which listings to fix first",
             "A 15-minute triage you can do today.",
             p(f"Hi {NAME},")
             + p("A quick way to cut today's risk on <strong>" + STORE + "</strong>:")
             + steps([
                 ("Sort your at-risk SKUs by 30-day sales",
                  "Start with the top 20 — that's where most oversells come from."),
                 ("Switch them to “Don't sell when out of stock”",
                  "Or unpublish them until your supplier restocks."),
                 ("Check the store-wide setting",
                  "“Continue selling when out of stock” is the most common cause of silent overselling."),
             ])
             + p("That fixes today's list. The catch: tomorrow's list will be different.")),
    "day3": ("How long does {{ contact.STORE_URL }} sell stock it doesn't have?",
             "The gap between a supplier stockout and your next sync.",
             p(f"Hi {NAME},")
             + p("Your oversell risk is really a timing problem: the gap between your supplier running out and "
                 "your store finding out.")
             + bars()
             + p("Closing that gap is exactly what a dedicated sync engine does. Flat project fee, you own the "
                 "code, no monthly subscription.")
             + p("If you'd like to see what it would take for your feeds:", "margin-bottom:8px;")
             + button("Book a 20-minute feasibility review", CALENDAR)),
    "day7": ("Closing the loop on your audit",
             "Last note from me — plus your baseline score.",
             p(f"Hi {NAME},")
             + p("This is my last follow-up. Your audit baseline:")
             + stat("{{ contact.HEALTH_SCORE }}/100", "Audit Health Score", GREEN)
             + p("If syncing supplier inventory is on your list this quarter, a 20-minute review will tell you "
                 "whether a custom build is worth it — or whether an off-the-shelf app is enough. I'll be honest "
                 "either way.", "margin-bottom:8px;")
             + button("Book a 20-minute review", CALENDAR)
             + p("You can re-run the audit any time to compare against this baseline.",
                 f"color:{SUB};font-size:14px;")),
}

if __name__ == "__main__":
    for name, (subject, preheader, body) in EMAILS.items():
        with open(os.path.join(HERE, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(wrap(preheader, body))
        print(f"{name}.html  |  Subject: {subject}")
