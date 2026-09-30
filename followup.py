"""Automated follow-up sequence for captured leads.

Run on a schedule (e.g. hourly cron / GitHub Action / Render cron job):
    python followup.py            # send whatever is due
    python followup.py --dry-run  # print what would be sent

Cadence by tier (see leads.score_lead):
    hot  -> day 0 only, plus an alert to the owner for personal outreach within 4 business hours
    warm -> day 0, 1, 3, 7
    cold -> day 0, 7
Leads with "call_booked": true or "unsubscribed": true are skipped.

SMTP settings (env): SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD,
FROM_EMAIL, OWNER_EMAIL, CALENDAR_LINK, OPERATOR_NAME.
"""
from __future__ import annotations

import argparse
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

import leads as leads_mod

OPERATOR = os.environ.get("OPERATOR_NAME", "Ziad")

TEMPLATES = {
    0: ("Your oversell audit for {store_url} (score {health_score}/100)",
        """Hi {first_name},

Your audit report for {store_url} is attached.

The headline: {oos_active_count} products are live on Shopify but out of stock at your supplier. At the inputs you gave, that is an estimated {monthly_exposure}/month in at-risk orders.

The report lists every assumption, so you can adjust it to your real numbers. If anything looks wrong, reply and I'll check it.

— {operator}"""),
    1: ("Which of the {oos_active_count} listings to fix first",
        """{first_name},

A quick way to triage: sort the at-risk SKU list by 30-day sales and handle the top 20 today. Set them to "Don't sell when out of stock", or unpublish them.

Then check that "Continue selling when out of stock" isn't switched on across your catalog. It's the most common cause of silent overselling.

That fixes today's list. The underlying problem is that tomorrow's list will be different.

— {operator}"""),
    3: ("How long does {store_url} sell stock it doesn't have?",
        """{first_name},

Your exposure is roughly the time between a supplier stockout and your next sync. With a daily import that's up to 24 hours per stockout; with a 15-minute sync it's about 15 minutes. That gap is what drives the {monthly_exposure} figure in your report.

If you'd like to see what closing that gap would take for your feeds: {calendar_link}

— {operator}"""),
    7: ("Closing the loop on your audit",
        """{first_name},

This is my last follow-up. If syncing supplier inventory is on your list this quarter, a 20-minute review will tell you whether a flat-fee custom build is worth it, or whether an off-the-shelf app is enough: {calendar_link}

Either way, you can re-run the auditor any time to compare against your {health_score}/100 baseline.

— {operator}"""),
}

CADENCE = {"hot": [0], "warm": [0, 1, 3, 7], "cold": [0, 7]}


def merge_fields(lead: dict) -> dict:
    s = lead.get("stats", {})
    return {
        "first_name": (lead.get("first_name") or "there").split()[0].title(),
        "store_url": lead.get("store_url") or "your store",
        "health_score": s.get("health_score", "–"),
        "oos_active_count": s.get("oos_active_count", s.get("oos_count", 0)),
        "monthly_exposure": f"${s.get('monthly_exposure', 0):,.0f}",
        "calendar_link": os.environ.get("CALENDAR_LINK", "[calendar link]"),
        "operator": OPERATOR,
    }


def render(day: int, lead: dict) -> tuple[str, str]:
    subject, body = TEMPLATES[day]
    fields = merge_fields(lead)
    return subject.format(**fields), body.format(**fields)


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("FROM_EMAIL"))


def send_email(to: str, subject: str, body: str, attachment: tuple[str, bytes, str] | None = None) -> None:
    msg = EmailMessage()
    msg["From"] = os.environ["FROM_EMAIL"]
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = os.environ.get("OWNER_EMAIL", os.environ["FROM_EMAIL"])
    msg.set_content(body + "\n\n—\nReply \"unsubscribe\" and I won't email again.")
    if attachment:
        name, data, mime = attachment
        maintype, subtype = mime.split("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)), timeout=15) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.send_message(msg)


def due_steps(lead: dict, now: datetime) -> list[int]:
    if lead.get("call_booked") or lead.get("unsubscribed"):
        return []
    start = datetime.fromisoformat(lead.get("first_captured_at") or lead["captured_at"])
    age_days = (now - start).total_seconds() / 86400
    sent = set(lead.get("followups_sent", []))
    return [d for d in CADENCE.get(lead.get("tier", "warm"), CADENCE["warm"])
            if d <= age_days and d not in sent]


def run(dry_run: bool = False) -> int:
    now = datetime.now(timezone.utc)
    all_leads = leads_mod.load_leads()
    sent_count = 0
    for lead in all_leads:
        steps = due_steps(lead, now)
        if not steps:
            continue
        day = max(steps)            # never send a backlog burst; jump to the latest due step
        subject, body = render(day, lead)
        if dry_run:
            print(f"--- [{lead.get('tier')}] {lead['email']} day {day}\n{subject}\n\n{body}\n")
        else:
            send_email(lead["email"], subject, body)
            if lead.get("tier") == "hot" and day == 0 and os.environ.get("OWNER_EMAIL"):
                send_email(os.environ["OWNER_EMAIL"], f"HOT lead: {lead['email']} ({lead.get('store_url')})",
                           "Reach out personally within 4 business hours.\n\n" + str(lead))
        lead["followups_sent"] = sorted(set(lead.get("followups_sent", [])) | set(steps))
        sent_count += 1
    if not dry_run:
        leads_mod.update_followups({l["email"]: l.get("followups_sent", []) for l in all_leads})
    return sent_count


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dry_run and not smtp_configured():
        raise SystemExit("Set SMTP_HOST and FROM_EMAIL (or use --dry-run).")
    print(f"{run(args.dry_run)} lead(s) processed.")
