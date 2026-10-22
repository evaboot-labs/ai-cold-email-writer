"""Builds n8n/ai-cold-email-writer.json. Run: python3 n8n/build_workflow.py

A form takes a Sales Navigator search URL and a lead count. Evaboot exports the leads, Claude writes
one email per lead, a Code node applies the same checks as emails.py, and the emails land in your sheet.
After you mark rows "yes" and approve on the form, the workflow reads the sheet back and adds the
approved, safe rows to your Instantly campaign. Nothing is sent: you launch the campaign.
"""
import json
import uuid
from pathlib import Path

MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
INSTANTLY_CRED = {"httpHeaderAuth": {"id": "", "name": "Instantly API key"}}
MODEL = "claude-sonnet-5-5"

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def mcp_call(name, tool, json_expr, pos):
    node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


FACTS_JS = r"""
// Same as emails.py facts: real fields only, plus the email-domain check.
const LINK_DOMAINS = ['linktr.ee', 'bit.ly', 'beacons.ai', 'lnk.bio', 'linkin.bio', 'carrd.co', 'about.me'];
const num = v => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isNaN(n) ? null : n; };
const words = s => String(s || '').split(/\s+/).join(' ').trim();
function domainNote(email, company) {
  if (!email) return '';
  const d = email.split('@').pop().toLowerCase(); const c = String(company || '').toLowerCase();
  if (LINK_DOMAINS.includes(d)) return `email on ${d}, a link site: do not send`;
  if (c && !(d === c || d.endsWith('.' + c) || c.endsWith('.' + d))) return `email domain ${d} differs from the company's ${c}: check it`;
  return '';
}
const prospects = $json.structuredContent.result.prospects || [];
if (!prospects.length) throw new Error('The export returned no leads. Check the search in Sales Navigator.');
const leads = prospects.map(p => {
  const months = (num(p['Years in Position']) || 0) * 12 + (num(p['Months in Position']) || 0);
  return {
    id: p['Linkedin URL Unique ID'] || p['Linkedin URL Public'] || p['Full Name'],
    first_name: p['First Name'] || '', last_name: p['Last Name'] || '', name: p['Full Name'] || '',
    email: p['Email'] || '', email_status: p['Email Status'] || 'not found',
    email_check: domainNote(p['Email'] || '', p['Company Domain']),
    title: String(p['Current Job'] || '').trim(), company: p['Company Name'] || '',
    months_in_role: months,
    new_in_role: ['true', 'yes', '1'].includes(String(p['Has New Position']).toLowerCase()) || months < 6,
    headline: words(p['Profile Headline']), summary: words(p['Profile Summary']).slice(0, 700),
    company_description: words(p['Company Description']).slice(0, 400),
    company_growth_1y_pct: num(p['Company Employee Growth 1 Year (%)']), sales_team: num(p['Sales Team Size']),
  };
});
return [{ json: { leads } }];
"""

ROWS_JS = r"""
// Same checks as emails.py check: subject length, body length, no link, a hook, the first name.
const leads = $('Lead facts').first().json.leads;
const out = Object.fromEntries($json.output.emails.map(e => [e.id, e]));
return leads.map(l => {
  const e = out[l.id] || { skip: true, reason: 'no email returned' };
  let subject = e.skip ? '' : (e.subject || ''), body = e.skip ? '' : (e.body || '');
  let hook = e.skip ? `SKIP: ${e.reason || 'no reason given'}` : (e.hook || '');
  const n = body.split(/\s+/).filter(Boolean).length;
  const first = String(l.first_name).split(/[\s-]/)[0].toLowerCase();
  const bad = !e.skip && (!e.hook || !subject || subject.length > 60 || n < 40 || n > 110
    || /https?:\/\/|www\./.test(body) || !body.toLowerCase().startsWith('hi ' + first));
  if (bad) { hook = 'SKIP: the email failed the checks'; subject = ''; body = ''; }
  return { json: {
    'Name': l.name, 'Title': l.title, 'Company': l.company, 'Email': l.email, 'Email status': l.email_status,
    'Email check': l.email_check, 'Hook': hook, 'Subject': subject, 'Body': body, 'Send (yes/no)': '',
  } };
});
"""

APPROVED_JS = r"""
// Rows you marked yes, with a safe email that is not on a link site.
return $input.all().filter(r => String(r.json['Send (yes/no)']).trim().toLowerCase() === 'yes'
  && r.json['Body'] && r.json['Email status'] === 'safe' && !String(r.json['Email check']).includes('do not send'));
"""

WRITE_SYSTEM = """You write the first cold email to each lead in the JSON you are given, for the offer below. Use only the facts in the JSON and the offer: never invent a customer, a number or a result.

For each lead return {id, hook, subject, body} or {id, skip: true, reason}.
Rules: skip leads with no email, an email_status other than safe or riskier, or an email_check that says "do not send". Subject: 60 characters at most, lower case, about them. Body: 40 to 110 words; "Hi <first name>," then one short paragraph on them, one on the offer, one line for a low-effort ask; paragraphs separated by a blank line. One real hook, named in "hook": a new role, company growth (always "in a year"), the size of the sales team, or one concrete line of their own headline or summary. No link, no template phrases ("hope this finds you", "quick question"), and vary the first line across the emails.

Offer:
"""

node("Search to email", "n8n-nodes-base.formTrigger", 2.2, {
    "formTitle": "Write AI cold emails",
    "formDescription": "Paste a Sales Navigator people search. Evaboot exports the leads (1 credit per lead), Claude writes one email per lead into your sheet, and you approve before anything reaches Instantly.",
    "formFields": {"values": [
        {"fieldLabel": "Sales Navigator search URL", "fieldType": "textarea", "requiredField": True},
        {"fieldLabel": "Leads to export", "fieldType": "number", "requiredField": True, "placeholder": "20"},
    ]},
    "responseMode": "lastNode", "options": {},
}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "sheet_url", "type": "string", "value": "PASTE_YOUR_GOOGLE_SHEET_URL_WITH_GID"},
    {"id": str(uuid.uuid4()), "name": "instantly_campaign_id", "type": "string", "value": "PASTE_YOUR_CAMPAIGN_ID"},
    {"id": str(uuid.uuid4()), "name": "offer", "type": "string",
     "value": "Evaboot exports a LinkedIn Sales Navigator search to a clean spreadsheet with verified professional emails, for sales leaders who build prospect lists. Ask: a low-effort question such as 'Worth a look?'"},
]}, "includeOtherFields": True, "options": {}}, [220, 0])
mcp_call("Export with Evaboot", "export_sn_search_or_list",
         "={{ JSON.stringify({ linkedin_url: $('Search to email').first().json['Sales Navigator search URL'].trim(), "
         "max_results: Number($('Search to email').first().json['Leads to export']) || 20, "
         "search_name: 'Cold emails ' + $now.toFormat('yyyy-MM-dd') }) }}", [440, 0])
node("Wait 30 s", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [660, 0])
mcp_call("Check the export", "get_export",
         "={{ JSON.stringify({ extraction_id: $('Export with Evaboot').first().json.structuredContent.result.extraction_id }) }}",
         [880, 0])
node("Done?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json.structuredContent.result.status }}",
                    "rightValue": "EXECUTED", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [1100, 0])
code("Lead facts", FACTS_JS, [1320, -100])
node("Write the emails", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "text": "={{ JSON.stringify($json.leads) }}", "hasOutputParser": True,
    "options": {"systemMessage": "=" + WRITE_SYSTEM + "{{ $('Your settings').first().json.offer }}",
                "maxIterations": 3},
}, [1560, -100], retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 12000},
}, [1520, 120], ANTHROPIC_CRED)
node("Emails", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["emails"], "properties": {"emails": {
        "type": "array", "items": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}, "hook": {"type": "string"}, "subject": {"type": "string"},
            "body": {"type": "string"}, "skip": {"type": "boolean"}, "reason": {"type": "string"}}}}}}, indent=2),
}, [1680, 120])
code("Check each email", ROWS_JS, [1880, -100])
node("Add to the approval sheet", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "append",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
    "options": {},
}, [2100, -100], SHEETS_CRED)
node("Approve", "n8n-nodes-base.form", 2.3, {
    "formFields": {"values": [{"fieldLabel": "Load the rows marked yes into Instantly?", "fieldType": "dropdown",
                               "fieldOptions": {"values": [{"option": "Yes, load them"}, {"option": "No, stop here"}]},
                               "requiredField": True}]},
    "options": {"formTitle": "Read and approve the emails",
                "formDescription": "Open your sheet, edit any email you want, and write yes in Send for the ones to load. Only safe emails are loaded. Nothing is sent: you launch the campaign in Instantly."},
}, [2320, -100], executeOnce=True)
node("Approved?", "n8n-nodes-base.if", 2.2, {"conditions": {
    "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
    "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ $json['Load the rows marked yes into Instantly?'] }}",
                    "rightValue": "Yes, load them", "operator": {"type": "string", "operation": "equals"}}],
    "combinator": "and"}, "options": {}}, [2540, -100])
node("Read the sheet", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "read",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "options": {},
}, [2760, -200], SHEETS_CRED)
code("Approved rows", APPROVED_JS, [2980, -200])
node("Add to Instantly", "n8n-nodes-base.httpRequest", 4.2, {
    "method": "POST", "url": "https://api.instantly.ai/api/v2/leads",
    "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
    "sendBody": True, "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ campaign: $('Your settings').first().json.instantly_campaign_id, email: $json.Email, "
                "first_name: $json.Name.split(' ')[0], last_name: $json.Name.split(' ').slice(1).join(' '), "
                "company_name: $json.Company, personalization: $json.Body, custom_variables: { ai_subject: $json.Subject }, "
                "skip_if_in_campaign: true }) }}",
    "options": {},
}, [3200, -200], INSTANTLY_CRED)
node("Loaded", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Emails loaded",
                                            "completionMessage": "Preview a few leads in your Instantly campaign, then launch it when you are ready.",
                                            "options": {}}, [3420, -200], executeOnce=True)
node("Stopped", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Nothing loaded",
                                             "completionMessage": "The emails stay in your sheet.", "options": {}}, [2760, 0])

for a, b in [("Search to email", "Your settings"), ("Your settings", "Export with Evaboot"),
             ("Export with Evaboot", "Wait 30 s"), ("Wait 30 s", "Check the export"), ("Check the export", "Done?"),
             ("Lead facts", "Write the emails"), ("Write the emails", "Check each email"),
             ("Check each email", "Add to the approval sheet"), ("Add to the approval sheet", "Approve"),
             ("Approve", "Approved?"), ("Read the sheet", "Approved rows"), ("Approved rows", "Add to Instantly"),
             ("Add to Instantly", "Loaded")]:
    link(a, b)
link("Done?", "Lead facts", out=0)
link("Done?", "Wait 30 s", out=1)
link("Approved?", "Read the sheet", out=0)
link("Approved?", "Stopped", out=1)
link("Claude", "Write the emails", "ai_languageModel")
link("Emails", "Write the emails", "ai_outputParser")

workflow = {"name": "AI cold email writer (Evaboot MCP + Claude + Instantly)", "nodes": nodes,
            "connections": connections, "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("ai-cold-email-writer.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
