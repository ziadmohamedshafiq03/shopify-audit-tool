"""Lead capture, qualification scoring and routing.

Only summary numbers are stored — never the uploaded files.
Routing targets are configured with env vars or .streamlit/secrets.toml:
  LEAD_WEBHOOK_URL   Zapier / Make / n8n / GoHighLevel inbound webhook (JSON POST)
  HUBSPOT_TOKEN      HubSpot private-app token (creates/updates a contact)
  BREVO_API_KEY      Brevo (free CRM + email automation). Also BREVO_LIST_HOT/WARM/COLD list ids,
                     and BREVO_SENDER_EMAIL + OWNER_EMAIL for hot-lead alerts.
                     Run `python integrations/brevo_setup.py` once to create the lists/attributes.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone

import requests

LEADS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured_leads.json")
_lock = threading.Lock()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com",
                      "live.com", "proton.me", "protonmail.com", "gmx.com", "yandex.com", "mail.com"}


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match((email or "").strip()))


def normalize_store_url(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://", "", url).split("/")[0]
    return url


def score_lead(lead: dict) -> tuple[int, str]:
    """Hot / warm / cold scoring from audit stats + qualification answers."""
    pts = 0
    band = lead.get("revenue_band", "")
    pts += {"$250k - $1M": 10, "$1M - $5M": 30, "$5M - $20M": 40, "$20M+": 40}.get(band, 0)
    stats = lead.get("stats", {})
    oos_active = stats.get("oos_active_count", 0) or 0
    if stats.get("shopify_export_uploaded"):
        pts += 15
    pts += 15 if oos_active >= 20 else 8 if oos_active >= 5 else 0
    if (stats.get("active_skus") or stats.get("total_skus") or 0) >= 1000:
        pts += 10
    suppliers = stats.get("supplier_count") or lead.get("supplier_count") or 0
    pts += 10 if suppliers >= 3 else 5 if suppliers == 2 else 0
    sync = lead.get("sync_method", "")
    pts += 15 if "Manual" in sync or "No sync" in sync else 8 if "app" in sync.lower() else 0
    feed = lead.get("feed_delivery", "")
    pts += 5 if feed in ("FTP / SFTP", "API") else -5 if feed == "Portal login only" else 0
    domain = (lead.get("email", "").split("@")[-1]).lower()
    if domain and domain not in FREE_EMAIL_DOMAINS:
        pts += 5

    big = band in ("$1M - $5M", "$5M - $20M", "$20M+")
    if pts >= 70 or (big and oos_active >= 10):
        tier = "hot"
    elif band == "Under $250k" or pts < 40:
        tier = "cold"
    else:
        tier = "warm"
    return pts, tier


def _post_webhook(url: str, lead: dict) -> None:
    try:
        requests.post(url, json=lead, timeout=4)
    except requests.RequestException:
        pass


def _post_hubspot(token: str, lead: dict) -> None:
    props = {
        "email": lead["email"],
        "firstname": lead.get("first_name", ""),
        "website": lead.get("store_url", ""),
        "hs_lead_status": "NEW",
    }
    try:
        requests.post("https://api.hubapi.com/crm/v3/objects/contacts",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"properties": props}, timeout=4)
    except requests.RequestException:
        pass


BREVO_API = "https://api.brevo.com/v3"

# Lead fields -> Brevo contact attributes (created by integrations/brevo_setup.py).
BREVO_ATTRIBUTES = {
    "FIRSTNAME": ("first_name", "text"),
    "STORE_URL": ("store_url", "text"),
    "TIER": ("tier", "text"),
    "LEAD_SCORE": ("score", "float"),
    "REVENUE_BAND": ("revenue_band", "text"),
    "SYNC_METHOD": ("sync_method", "text"),
    "HEALTH_SCORE": ("stats.health_score", "float"),
    "OOS_ACTIVE": ("stats.oos_active_count", "float"),
    "MONTHLY_EXPOSURE": ("stats.monthly_exposure", "float"),
    "TOTAL_SKUS": ("stats.total_skus", "float"),
    "SUPPLIER_COUNT": ("supplier_count", "float"),
    "FEED_DELIVERY": ("feed_delivery", "text"),
}


def brevo_attributes(lead: dict) -> dict:
    out = {}
    for attr, (path, kind) in BREVO_ATTRIBUTES.items():
        value = lead
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value is None and path == "supplier_count":
            value = lead.get("stats", {}).get("supplier_count")
        if value in (None, ""):
            continue
        out[attr] = float(value) if kind == "float" else str(value)
    return out


def _post_brevo(lead: dict) -> None:
    key = os.environ.get("BREVO_API_KEY", "")
    lists = {t: os.environ.get(f"BREVO_LIST_{t.upper()}", "") for t in ("hot", "warm", "cold")}
    headers = {"api-key": key, "accept": "application/json", "content-type": "application/json"}
    try:
        target = int(lists[lead["tier"]]) if lists.get(lead["tier"]) else None
        body = {"email": lead["email"], "attributes": brevo_attributes(lead), "updateEnabled": True}
        if target:
            body["listIds"] = [target]
        r = requests.post(f"{BREVO_API}/contacts", headers=headers, json=body, timeout=6)
        if r.status_code == 400 and "attribute" in r.text.lower():
            # First run without integrations/brevo_setup.py: create the custom fields, then retry once.
            for attr, (_, kind) in BREVO_ATTRIBUTES.items():
                requests.post(f"{BREVO_API}/contacts/attributes/normal/{attr}", headers=headers,
                              json={"type": kind}, timeout=6)
            r = requests.post(f"{BREVO_API}/contacts", headers=headers, json=body, timeout=6)
        if r.status_code == 204 and target:
            # Existing contact whose tier changed: leave the other tier lists so only one sequence runs.
            others = [int(v) for t, v in lists.items() if v and int(v) != target]
            if others:
                requests.put(f"{BREVO_API}/contacts/{requests.utils.quote(lead['email'])}", headers=headers,
                             json={"unlinkListIds": others}, timeout=6)
        sender, owner = os.environ.get("BREVO_SENDER_EMAIL"), os.environ.get("OWNER_EMAIL")
        if r.status_code == 201 and lead["tier"] == "hot" and sender and owner:
            s = lead.get("stats", {})
            requests.post(f"{BREVO_API}/smtp/email", headers=headers, timeout=6, json={
                "sender": {"email": sender, "name": "Oversell Auditor"},
                "to": [{"email": owner}],
                "subject": f"HOT lead: {lead['email']} ({lead.get('store_url', '')})",
                "textContent": (f"Reach out personally within 4 business hours.\n\n"
                                f"Name: {lead.get('first_name', '')}\nStore: {lead.get('store_url', '')}\n"
                                f"Revenue: {lead.get('revenue_band', '')}\nSync: {lead.get('sync_method', '')}\n"
                                f"Health score: {s.get('health_score')}\nLive-but-OOS: {s.get('oos_active_count')}\n"
                                f"Est. exposure/mo: ${s.get('monthly_exposure', 0):,}\nLead score: {lead.get('score')}"),
            })
    except (requests.RequestException, ValueError, KeyError):
        pass


def save_lead(lead: dict, webhook_url: str = "", hubspot_token: str = "") -> dict:
    """Persist + route a lead. Returns the enriched record. Never raises on routing errors."""
    lead = dict(lead)
    lead["email"] = lead.get("email", "").strip().lower()
    lead["store_url"] = normalize_store_url(lead.get("store_url", ""))
    lead["captured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lead["score"], lead["tier"] = score_lead(lead)
    lead.setdefault("followups_sent", [])

    with _lock:
        leads = load_leads()
        # Upsert by email so a second audit updates the same lead instead of duplicating it.
        existing = next((l for l in leads if l.get("email") == lead["email"]), None)
        if existing:
            lead["followups_sent"] = existing.get("followups_sent", [])
            lead["first_captured_at"] = existing.get("first_captured_at", existing.get("captured_at"))
            leads[leads.index(existing)] = {**existing, **lead}
        else:
            lead["first_captured_at"] = lead["captured_at"]
            leads.append(lead)
        _write(leads)

    if webhook_url:
        threading.Thread(target=_post_webhook, args=(webhook_url, lead), daemon=True).start()
    if hubspot_token:
        threading.Thread(target=_post_hubspot, args=(hubspot_token, lead), daemon=True).start()
    if os.environ.get("BREVO_API_KEY"):
        threading.Thread(target=_post_brevo, args=(lead,), daemon=True).start()
    return lead


def load_leads(path: str | None = None) -> list:
    path = path or LEADS_FILE
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write(leads: list, path: str | None = None) -> None:
    path = path or LEADS_FILE
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(leads, f, indent=2, default=str)
    os.replace(tmp, path)


def update_followups(sent_by_email: dict, path: str | None = None) -> None:
    """Re-read under the lock so leads captured while the sequence ran aren't lost."""
    with _lock:
        leads = load_leads(path)
        for lead in leads:
            if lead.get("email") in sent_by_email:
                lead["followups_sent"] = sent_by_email[lead["email"]]
        _write(leads, path)
