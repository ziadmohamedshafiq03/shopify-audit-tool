/**
 * Free lead CRM + follow-up sequence for the Shopify Oversell Risk Auditor.
 *
 * Google Sheet = lead database. Gmail = sender. No servers, no paid tools.
 *
 * SETUP (5 minutes):
 *  1. Create a Google Sheet. Extensions -> Apps Script. Paste this whole file. Edit CONFIG below. Save.
 *  2. Deploy -> New deployment -> type "Web app" -> Execute as: Me, Who has access: Anyone -> Deploy.
 *     Copy the Web app URL and set it as LEAD_WEBHOOK_URL in the Streamlit app's secrets.
 *  3. In the Apps Script editor, run `setup` once (approve the permissions). It creates the
 *     "Leads" tab and an hourly trigger for `sendFollowups`.
 *  4. Tick the "call_booked" or "unsubscribed" checkbox on a row to stop that lead's sequence.
 *
 * Gmail limits: ~100 emails/day on a free account, 1,500 on Google Workspace.
 * Leave SMTP unset in the Streamlit app when using this, so the day-0 email is only sent from here.
 */

const CONFIG = {
  OPERATOR_NAME: 'Ziad',
  OWNER_EMAIL: 'you@yourdomain.com',          // hot-lead alerts go here
  CALENDAR_LINK: 'https://cal.com/your-handle/feasibility-review',
  // A REAL, anonymised client result for the day-3 email. Leave '' until you have one.
  CASE_STUDY: '',
};

const SHEET_NAME = 'Leads';
const COLUMNS = [
  'email', 'first_name', 'store_url', 'tier', 'score', 'revenue_band', 'sync_method',
  'health_score', 'grade', 'oos_active_count', 'monthly_exposure', 'monthly_exposure_conservative',
  'total_skus', 'active_skus', 'mismatch_count', 'supplier_count', 'feed_delivery', 'context',
  'review_requested', 'report_emailed_by_app', 'first_captured_at', 'captured_at',
  'followups_sent', 'call_booked', 'unsubscribed',
];
const CADENCE = { hot: [0], warm: [0, 1, 3, 7], cold: [0, 7] };

function setup() {
  const sheet = getSheet_();
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'sendFollowups')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('sendFollowups').timeBased().everyHours(1).create();
  sheet.getRange(2, COLUMNS.indexOf('call_booked') + 1, sheet.getMaxRows() - 1, 2).insertCheckboxes();
}

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(COLUMNS);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, COLUMNS.length).setFontWeight('bold');
  }
  return sheet;
}

/** Webhook: the Streamlit app POSTs each lead as JSON. Upserts by email. */
function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const lead = JSON.parse(e.postData.contents);
    const stats = lead.stats || {};
    const flat = Object.assign({}, lead, stats);
    const sheet = getSheet_();
    const emails = sheet.getRange(1, 1, sheet.getLastRow(), 1).getValues().map(r => String(r[0]).toLowerCase());
    let row = emails.indexOf(String(lead.email).toLowerCase()) + 1;
    const isNew = row === 0;
    if (isNew) row = sheet.getLastRow() + 1;
    const existing = isNew ? [] : sheet.getRange(row, 1, 1, COLUMNS.length).getValues()[0];

    const values = COLUMNS.map((col, i) => {
      // never overwrite state that lives in the sheet
      if (['followups_sent', 'call_booked', 'unsubscribed', 'first_captured_at'].includes(col) && !isNew) {
        return existing[i];
      }
      if (col === 'followups_sent') return lead.report_emailed_by_app ? '0' : '';
      if (col === 'call_booked' || col === 'unsubscribed') return false;
      if (col === 'first_captured_at') return lead.first_captured_at || lead.captured_at || new Date().toISOString();
      const v = flat[col];
      return v === undefined || v === null ? (isNew ? '' : existing[i]) : v;
    });
    sheet.getRange(row, 1, 1, COLUMNS.length).setValues([values]);
    sheet.getRange(row, COLUMNS.indexOf('call_booked') + 1, 1, 2).insertCheckboxes();

    if (isNew && lead.tier === 'hot' && CONFIG.OWNER_EMAIL) {
      MailApp.sendEmail(CONFIG.OWNER_EMAIL, `HOT lead: ${lead.email} (${lead.store_url || ''})`,
        `Reach out personally within 4 business hours.\n\n${JSON.stringify(flat, null, 2)}`);
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: true }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

/** Hourly trigger: sends whichever sequence step is due for each lead. */
function sendFollowups() {
  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const idx = Object.fromEntries(COLUMNS.map((c, i) => [c, i]));
  const now = Date.now();
  let quota = MailApp.getRemainingDailyQuota();

  for (let r = 1; r < data.length && quota > 0; r++) {
    const row = data[r];
    if (!row[idx.email] || row[idx.call_booked] === true || row[idx.unsubscribed] === true) continue;
    const sent = String(row[idx.followups_sent] || '').split(',').filter(String).map(Number);
    const ageDays = (now - new Date(row[idx.first_captured_at]).getTime()) / 86400000;
    const due = (CADENCE[row[idx.tier]] || CADENCE.warm).filter(d => d <= ageDays && !sent.includes(d));
    if (!due.length) continue;

    const day = Math.max(...due);                  // never send a backlog burst
    const msg = render_(day, row, idx);
    GmailApp.sendEmail(row[idx.email], msg.subject,
      msg.body + '\n\n—\nReply "unsubscribe" and I won\'t email again.',
      { name: CONFIG.OPERATOR_NAME, replyTo: CONFIG.OWNER_EMAIL });
    quota--;
    const newSent = Array.from(new Set(sent.concat(due))).sort((a, b) => a - b).join(',');
    sheet.getRange(r + 1, idx.followups_sent + 1).setValue(newSent);
  }
}

function render_(day, row, idx) {
  const firstName = String(row[idx.first_name] || 'there').split(' ')[0];
  const f = {
    first_name: firstName.charAt(0).toUpperCase() + firstName.slice(1).toLowerCase(),
    store_url: row[idx.store_url] || 'your store',
    health_score: row[idx.health_score] === '' ? '–' : row[idx.health_score],
    oos_active_count: row[idx.oos_active_count] || 0,
    monthly_exposure: '$' + Number(row[idx.monthly_exposure] || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
    calendar_link: CONFIG.CALENDAR_LINK,
    operator: CONFIG.OPERATOR_NAME,
    case_study: CONFIG.CASE_STUDY ? `\n${CONFIG.CASE_STUDY}\n` : '',
  };
  const exposureLine = Number(row[idx.monthly_exposure]) > 0
    ? ` At the inputs you gave, that is an estimated ${f.monthly_exposure}/month in at-risk orders.` : '';
  const T = {
    0: [`Your oversell audit for ${f.store_url} (score ${f.health_score}/100)`,
`Hi ${f.first_name},

Thanks for running the audit on ${f.store_url}. The headline: ${f.oos_active_count} products are live on Shopify but out of stock at your supplier.${exposureLine}

The report you downloaded lists every assumption, so you can adjust it to your real numbers. If anything looks wrong, reply and I'll check it.

— ${f.operator}`],
    1: [`Which of the ${f.oos_active_count} listings to fix first`,
`${f.first_name},

A quick way to triage: sort the at-risk SKU list by 30-day sales and handle the top 20 today. Set them to "Don't sell when out of stock", or unpublish them.

Then check that "Continue selling when out of stock" isn't switched on across your catalog. It's the most common cause of silent overselling.

That fixes today's list. The underlying problem is that tomorrow's list will be different.

— ${f.operator}`],
    3: [`How long does ${f.store_url} sell stock it doesn't have?`,
`${f.first_name},

Your exposure is roughly the time between a supplier stockout and your next sync. With a daily import that's up to 24 hours per stockout; with a 15-minute sync it's about 15 minutes.
${f.case_study}
If you'd like to see what closing that gap would take for your feeds: ${f.calendar_link}

— ${f.operator}`],
    7: [`Closing the loop on your audit`,
`${f.first_name},

This is my last follow-up. If syncing supplier inventory is on your list this quarter, a 20-minute review will tell you whether a flat-fee custom build is worth it, or whether an off-the-shelf app is enough: ${f.calendar_link}

Either way, you can re-run the auditor any time to compare against your ${f.health_score}/100 baseline.

— ${f.operator}`],
  };
  return { subject: T[day][0], body: T[day][1] };
}
