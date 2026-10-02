# Brevo setup: free lead CRM + automatic follow-ups

Brevo's free plan stores up to 100,000 contacts and sends 300 emails a day, including automations.
You sign up with your existing email. No Google account or authorization is involved.

## 1. Create the account and API key

1. Sign up at **brevo.com** (free plan).
2. Add a sender: **Senders, Domains & Dedicated IPs → Senders → Add a sender**, then confirm the email Brevo
   sends you. An address on your own domain delivers best. A Gmail address works, but more messages may land
   in spam.
3. Create a key: **profile menu → SMTP & API → API Keys → Generate a new API key**. Copy it; it starts with
   `xkeysib-`.

## 2. Create three lists

Go to **Contacts → Lists → Create a list** and make:

- `Auditor - Hot leads`
- `Auditor - Warm leads`
- `Auditor - Cold leads`

Each list shows an **ID** number. Write the three IDs down.

(Or run `BREVO_API_KEY=xkeysib-... python integrations/brevo_setup.py`, which creates the lists and prints
the IDs.)

The custom contact fields (TIER, HEALTH_SCORE, OOS_ACTIVE, MONTHLY_EXPOSURE, …) are created automatically
when the first lead arrives.

## 3. Add the secrets to the app

In Streamlit Cloud, go to **App → Settings → Secrets**. Locally, use `.streamlit/secrets.toml`.

```toml
BREVO_API_KEY = "xkeysib-..."
BREVO_LIST_HOT = "3"
BREVO_LIST_WARM = "4"
BREVO_LIST_COLD = "5"
BREVO_SENDER_EMAIL = "you@yourdomain.com"   # the sender you verified in step 1
OWNER_EMAIL = "you@yourdomain.com"          # hot-lead alerts go here
CALENDAR_LINK = "https://cal.com/your-handle/feasibility-review"
```

Test it: run one audit on the live app and unlock the report with your own email. The contact appears
under **Contacts** within a few seconds.

## 4. Create the follow-up automations

Go to **Automations → Create an automation → Custom automation**. Build three workflows. For each, the
entry point is **"Contact added to list"**, using the matching list.

| Workflow | Steps |
|---|---|
| **Warm** | Email Day 0 → wait 1 day → Email Day 1 → wait 2 days → Email Day 3 → wait 4 days → Email Day 7 |
| **Cold** | Email Day 0 → wait 7 days → Email Day 7 |
| **Hot**  | Email Day 0 only. The app emails you an alert so you can follow up personally. |

Set an **exit condition** on each workflow so it stops when you tag a contact. For example, stop when
contact attribute `TIER` equals `booked`: edit the contact and set TIER to `booked` once they book a call.

Create each email with **"Send an email"**. For designed emails, choose **Create from scratch → HTML custom code** and paste `integrations/brevo_emails/day0.html` … `day7.html`. For plain-text emails, paste in the templates below. Brevo fills in
`{{ contact.X }}` for each lead and adds the unsubscribe link automatically. Use **Preview** with a real
contact to check the numbers.

### Day 0 — Your oversell audit for {{ contact.STORE_URL }}

```
Hi {{ contact.FIRSTNAME | default : "there" }},

Thanks for running the audit on {{ contact.STORE_URL }}. The headline: {{ contact.OOS_ACTIVE | floatformat : 0 }} products are live on Shopify but out of stock at your supplier.{% if contact.MONTHLY_EXPOSURE > 0 %} At the inputs you gave, that is an estimated ${{ contact.MONTHLY_EXPOSURE | floatformat : 0 }}/month in at-risk orders.{% endif %}

The report you downloaded lists every assumption, so you can adjust it to your real numbers. If anything looks wrong, reply and I'll check it.

— Ziad
```

### Day 1 — Which listings to fix first

```
{{ contact.FIRSTNAME | default : "Hi" }},

A quick way to triage: sort the at-risk SKU list by 30-day sales and handle the top 20 today. Set them to "Don't sell when out of stock", or unpublish them.

Then check that "Continue selling when out of stock" isn't switched on across your catalog. It's the most common cause of silent overselling.

That fixes today's list. The underlying problem is that tomorrow's list will be different.

— Ziad
```

### Day 3 — How long does {{ contact.STORE_URL }} sell stock it doesn't have?

```
{{ contact.FIRSTNAME | default : "Hi" }},

Your exposure is roughly the time between a supplier stockout and your next sync. With a daily import that's up to 24 hours per stockout; with a 15-minute sync it's about 15 minutes.

[Optional: one REAL, anonymised client result. Delete this line until you have one.]

If you'd like to see what closing that gap would take for your feeds: [your calendar link]

— Ziad
```

### Day 7 — Closing the loop on your audit

```
{{ contact.FIRSTNAME | default : "Hi" }},

This is my last follow-up. If syncing supplier inventory is on your list this quarter, a 20-minute review will tell you whether a flat-fee custom build is worth it, or whether an off-the-shelf app is enough: [your calendar link]

Either way, you can re-run the auditor any time to compare against your {{ contact.HEALTH_SCORE | floatformat : 0 }}/100 baseline.

— Ziad
```

Activate the three workflows when they're ready. Every lead the app captures from then on enters the
right sequence automatically.
