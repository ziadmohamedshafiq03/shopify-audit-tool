# Shopify Oversell Risk Auditor

A free Streamlit audit that finds products a merchant is selling but their supplier can't ship, puts a
defensible dollar figure on it, and converts the merchant into a qualified lead for a custom inventory
sync engine.

## What it does

1. **Upload**: the supplier feed (CSV/TSV/Excel, any encoding or delimiter) is required. The Shopify product
   export is optional and unlocks the cross-check.
2. **Column mapping**: SKU, quantity, price, cost, vendor, status and inventory policy are detected
   automatically, and the merchant can override any of them.
3. **Calibrate**: revenue band, AOV and current sync method. These convert counts into dollars and also
   serve as lead qualification.
4. **Results**: an Audit Health Score (0–100, A–F), KPIs, findings ranked by severity, charts, the
   at-risk SKU list and a cleaning log.
   - Cross-check findings: live-but-OOS listings, *Continue selling when out of stock*, pricing below
     supplier cost, overstated stock, missed sales, orphaned/unlisted SKUs.
5. **Free download**: the cleaned supplier CSV, with the original columns kept.
6. **Email-gated**: a branded, print-ready HTML report and the at-risk SKU CSV. A lead is captured, scored
   hot/warm/cold and routed.
7. **Follow-up**: `followup.py` sends the day 0/1/3/7 sequence by tier.

The money model is conservative, capped at 3% of monthly revenue, and fully explained in the report. See
`audit_engine.money_model`. Dollar figures appear only when a Shopify export is uploaded, because that is the
only way to confirm which out-of-stock products are actually live. A supplier file alone shows counts only.

## Run locally

```bash
pip install -r requirements.txt
streamlit run SupplierValidator.py
python -m pytest -q tests        # engine, report, lead and follow-up tests
```

## Recommended free setup: Google Sheets + Gmail

`integrations/google_sheets_leads.gs` turns a Google Sheet into the lead CRM and sends the follow-up
sequence from your Gmail account. It needs no servers or paid tools, and leads survive Streamlit Cloud
redeploys.

1. Create a Google Sheet. Go to Extensions → Apps Script, paste the file, and edit `CONFIG` at the top.
2. Deploy → New deployment → **Web app**. Set Execute as **Me** and access to **Anyone**. Copy the URL.
3. Set that URL as `LEAD_WEBHOOK_URL` in the app's secrets. Leave the `SMTP_*` keys unset.
4. Run `setup` once in the Apps Script editor. It creates the `Leads` tab and an hourly follow-up trigger.
5. Tick `call_booked` or `unsubscribed` on a row to stop that lead's emails.

The script also emails you when a hot lead arrives. Free Gmail sends about 100 emails a day. `followup.py`
remains available if you'd rather self-host with SMTP.

## Configure

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, or set the same keys as environment
variables or Streamlit Cloud secrets. Every key is optional.

| Key | Purpose |
|---|---|
| `CALENDAR_LINK` | "Book a feasibility review" button. Without it, the button becomes a request form. |
| `LEAD_WEBHOOK_URL` | Posts each lead as JSON to Zapier / Make / n8n / GoHighLevel. |
| `HUBSPOT_TOKEN` | Creates a HubSpot contact. |
| `SMTP_*`, `FROM_EMAIL`, `OWNER_EMAIL` | Self-hosted alternative to the Sheets script: emails the report on capture, runs `followup.py`, and sends hot-lead alerts. |
| `CASE_STUDY` | Optional line in the day-3 email. Use a **real**, anonymised client result only. It's omitted when blank. |

Leads are also written to `captured_leads.json`, which holds summary stats only and is gitignored. On
Streamlit Cloud the filesystem is ephemeral, so configure a webhook or HubSpot for durable storage.

Schedule the sequence hourly:

```bash
python followup.py --dry-run   # preview
python followup.py             # send what's due
```

## Layout

| File | Contents |
|---|---|
| `SupplierValidator.py` | Streamlit UI |
| `audit_engine.py` | File loading, column detection, audit, cross-reference, money model, score (no Streamlit) |
| `report.py` | Email-gated HTML report |
| `leads.py` | Lead storage, scoring, webhook and HubSpot routing |
| `followup.py` | Email sequence templates and sender (self-hosted option) |
| `integrations/google_sheets_leads.gs` | Free Google Sheets CRM + Gmail follow-up sequence |
| `tests/` | pytest suite. `tests/fixtures/` holds synthetic test files only. |
