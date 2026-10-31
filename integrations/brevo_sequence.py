"""Run the day 0/1/3/7 follow-up sequence for Brevo contacts. Replaces Brevo's automations.

Runs hourly on GitHub Actions (.github/workflows/followups.yml), or by hand:

    BREVO_API_KEY=xkeysib-... python integrations/brevo_sequence.py --dry-run

Each run, for every contact in the hot/warm/cold lists:
  * skips anyone unsubscribed in Brevo (emailBlacklisted) or with TIER = "booked";
  * works out which steps of their tier's cadence are due since they were added;
  * sends only the latest due step (never a backlog burst) through Brevo's transactional API,
    using the HTML emails in integrations/brevo_emails/;
  * records what was sent in the FOLLOWUPS_SENT contact attribute, so nothing is sent twice.

Config (env): BREVO_API_KEY (required), BREVO_LIST_HOT/WARM/COLD, BREVO_SENDER_EMAIL,
SENDER_NAME, REPLY_TO.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import requests

API = "https://api.brevo.com/v3"
HERE = os.path.dirname(os.path.abspath(__file__))
CADENCE = {"hot": [0], "warm": [0, 1, 3, 7], "cold": [0, 7]}


def _load_templates() -> dict:
    spec = importlib.util.spec_from_file_location("brevo_email_build", os.path.join(HERE, "brevo_emails", "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {int(name[3:]): (subject, mod.wrap(pre, body)) for name, (subject, pre, body) in mod.EMAILS.items()}


TEMPLATES = _load_templates()


def _fmt(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render(step: int, attrs: dict, unsubscribe_href: str) -> tuple[str, str]:
    """Fill Brevo-style {{ contact.X }} placeholders from the contact's attributes."""
    subject, html = TEMPLATES[step]

    def sub(match: re.Match) -> str:
        name, default = match.group(1), match.group(2)
        value = _fmt(attrs.get(name))
        return value if value else (default or "")

    pattern = re.compile(r'\{\{\s*contact\.([A-Z_]+)(?:\s*\|\s*default\s*:\s*"([^"]*)")?\s*\}\}')
    html = html.replace("{{ unsubscribe }}", unsubscribe_href)
    return pattern.sub(sub, subject), pattern.sub(sub, html)


def due_step(tier: str, added_at: datetime, sent: set[int], now: datetime) -> int | None:
    age_days = (now - added_at).total_seconds() / 86400
    due = [d for d in CADENCE.get(tier, []) if d <= age_days and d not in sent]
    return max(due) if due else None


def parse_sent(raw) -> set[int]:
    return {int(x) for x in str(raw or "").split(",") if x.strip().isdigit()}


class Brevo:
    def __init__(self, key: str):
        self.h = {"api-key": key, "accept": "application/json", "content-type": "application/json"}

    def ensure_attribute(self, name: str) -> None:
        requests.post(f"{API}/contacts/attributes/normal/{name}", headers=self.h, json={"type": "text"}, timeout=15)

    def list_contacts(self, list_id: str):
        offset = 0
        while True:
            r = requests.get(f"{API}/contacts/lists/{list_id}/contacts", headers=self.h,
                             params={"limit": 500, "offset": offset}, timeout=30)
            r.raise_for_status()
            contacts = r.json().get("contacts", [])
            yield from contacts
            if len(contacts) < 500:
                return
            offset += 500

    def send(self, payload: dict) -> None:
        r = requests.post(f"{API}/smtp/email", headers=self.h, json=payload, timeout=30)
        r.raise_for_status()

    def mark_sent(self, email: str, sent: set[int]) -> None:
        r = requests.put(f"{API}/contacts/{quote(email)}", headers=self.h, timeout=15,
                         json={"attributes": {"FOLLOWUPS_SENT": ",".join(map(str, sorted(sent)))}})
        r.raise_for_status()


def run(dry_run: bool = False, now: datetime | None = None, client: Brevo | None = None) -> list[tuple[str, int]]:
    now = now or datetime.now(timezone.utc)
    client = client or Brevo(os.environ["BREVO_API_KEY"])
    sender = os.environ.get("BREVO_SENDER_EMAIL", "")
    name = os.environ.get("SENDER_NAME", "Ziad")
    reply_to = os.environ.get("REPLY_TO") or sender
    lists = {t: os.environ.get(f"BREVO_LIST_{t.upper()}", "") for t in CADENCE}
    if not dry_run:
        if not sender:
            raise SystemExit("Set BREVO_SENDER_EMAIL (a sender verified in Brevo).")
        client.ensure_attribute("FOLLOWUPS_SENT")

    done, seen = [], set()
    for tier in ("hot", "warm", "cold"):       # a contact on several lists follows its hottest tier
        if not lists[tier]:
            continue
        for c in client.list_contacts(lists[tier]):
            email = c.get("email", "").lower()
            attrs = c.get("attributes", {}) or {}
            if not email or email in seen:
                continue
            seen.add(email)
            if c.get("emailBlacklisted") or str(attrs.get("TIER", "")).lower() == "booked":
                continue
            added = datetime.fromisoformat(str(c["createdAt"]).replace("Z", "+00:00"))
            sent = parse_sent(attrs.get("FOLLOWUPS_SENT"))
            step = due_step(tier, added, sent, now)
            if step is None:
                continue
            unsubscribe = f"mailto:{reply_to}?subject=Unsubscribe"
            subject, html = render(step, attrs, unsubscribe)
            if dry_run:
                print(f"[dry-run] {tier:<4} {email:<35} day {step}: {subject}")
            else:
                client.send({
                    "sender": {"email": sender, "name": name},
                    "to": [{"email": email}],
                    "replyTo": {"email": reply_to, "name": name},
                    "subject": subject,
                    "htmlContent": html,
                    "headers": {"List-Unsubscribe": f"<{unsubscribe}>"},
                    "tags": ["oversell-followup", f"day{step}"],
                })
                # Earlier steps that were skipped are marked too, so they never go out late.
                client.mark_sent(email, sent | {d for d in CADENCE[tier] if d <= step})
                print(f"sent {tier:<4} {email:<35} day {step}")
            done.append((email, step))
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not os.environ.get("BREVO_API_KEY"):
        sys.exit("Set BREVO_API_KEY.")
    print(f"{len(run(args.dry_run))} email(s) {'due' if args.dry_run else 'sent'}.")
