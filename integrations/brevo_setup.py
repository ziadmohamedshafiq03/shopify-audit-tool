"""One-time Brevo setup: creates the contact attributes and the hot/warm/cold lists.

    BREVO_API_KEY=xkeysib-... python integrations/brevo_setup.py

Prints the secrets to paste into .streamlit/secrets.toml (or Streamlit Cloud secrets).
Safe to run more than once: existing attributes and lists are reused.
"""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from leads import BREVO_API, BREVO_ATTRIBUTES  # noqa: E402

FOLDER = "Oversell Auditor"
LISTS = {"hot": "Auditor - Hot leads", "warm": "Auditor - Warm leads", "cold": "Auditor - Cold leads"}


def main() -> None:
    key = os.environ.get("BREVO_API_KEY") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not key:
        raise SystemExit("Usage: BREVO_API_KEY=xkeysib-... python integrations/brevo_setup.py")
    h = {"api-key": key, "accept": "application/json", "content-type": "application/json"}

    r = requests.get(f"{BREVO_API}/account", headers=h, timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"Brevo rejected the API key ({r.status_code}): {r.text}")
    print(f"Connected to Brevo account: {r.json().get('email')}")

    existing = {a["name"] for a in requests.get(f"{BREVO_API}/contacts/attributes", headers=h, timeout=15)
                .json().get("attributes", [])}
    for name, (_, kind) in BREVO_ATTRIBUTES.items():
        if name in existing:
            continue
        resp = requests.post(f"{BREVO_API}/contacts/attributes/normal/{name}", headers=h,
                             json={"type": kind}, timeout=15)
        print(f"  attribute {name}: {'created' if resp.ok else resp.text}")

    folders = requests.get(f"{BREVO_API}/contacts/folders?limit=50", headers=h, timeout=15).json().get("folders", [])
    folder_id = next((f["id"] for f in folders if f["name"] == FOLDER), None)
    if folder_id is None:
        folder_id = requests.post(f"{BREVO_API}/contacts/folders", headers=h, json={"name": FOLDER},
                                  timeout=15).json()["id"]

    all_lists = requests.get(f"{BREVO_API}/contacts/lists?limit=50", headers=h, timeout=15).json().get("lists", [])
    ids = {}
    for tier, name in LISTS.items():
        found = next((l["id"] for l in all_lists if l["name"] == name), None)
        if found is None:
            found = requests.post(f"{BREVO_API}/contacts/lists", headers=h,
                                  json={"name": name, "folderId": folder_id}, timeout=15).json()["id"]
        ids[tier] = found

    print("\nDone. Add these to .streamlit/secrets.toml (or Streamlit Cloud → Settings → Secrets):\n")
    print(f'BREVO_API_KEY = "{key[:12]}..."   # paste your full key')
    for tier in ("hot", "warm", "cold"):
        print(f'BREVO_LIST_{tier.upper()} = "{ids[tier]}"')
    print('BREVO_SENDER_EMAIL = "you@yourdomain.com"   # a sender verified in Brevo → Senders')
    print('OWNER_EMAIL = "you@yourdomain.com"          # where hot-lead alerts go')


if __name__ == "__main__":
    main()
