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

## Recommended free setup: Brevo

Brevo's free plan acts as both the lead CRM and the email sender: 100k contacts, 300 emails a day, and
automations included. You sign up with your existing email, and no Google authorization is needed. Each
lead is added to a hot, warm or cold list, and a Brevo automation on each list sends the day 0/1/3/7
sequence. Hot leads also trigger an alert email to you.

Setup takes about 10 minutes. Follow **[integrations/BREVO_SETUP.md](integrations/BREVO_SETUP.md)**.

**Alternatives:**
- `integrations/google_sheets_leads.gs` uses a Google Sheet and Gmail. It needs a Google account that can
  authorize Apps Script.
- `followup.py` sends the sequence through any SMTP server you host yourself.

## Configure

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, or set the same keys as environment
variables or Streamlit Cloud secrets. Every key is optional.

| Key | Purpose |
|---|---|
| `CALENDAR_LINK` | "Book a feasibility review" button. Without it, the button becomes a request form. |
| `BREVO_API_KEY`, `BREVO_LIST_HOT/WARM/COLD`, `BREVO_SENDER_EMAIL` | Brevo CRM + automations (recommended). |
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
| `integrations/BREVO_SETUP.md`, `brevo_setup.py` | Brevo setup guide, email templates, one-time list creator |
| `integrations/google_sheets_leads.gs` | Free Google Sheets CRM + Gmail follow-up sequence |
| `tests/` | pytest suite. `tests/fixtures/` holds synthetic test files only. |
