# Run it in n8n

[`n8n/ai-cold-email-writer.json`](../n8n/ai-cold-email-writer.json) is the same agent for n8n. You paste a Sales Navigator search into a form, the emails land in your Google Sheet, and a second form page loads the rows you approve into Instantly.

## What runs

1. **Search to email** (form): a Sales Navigator people search URL and how many leads to export.
2. **Export with Evaboot** (MCP Client): exports that many leads with verified emails. 1 credit per lead.
3. **Lead facts** (Code): the same facts and email-domain check as `emails.py`.
4. **Write the emails** (AI Agent with Claude): one email per lead, or a skip with a reason, for the offer in Your settings.
5. **Check each email** (Code): subject and body length, no link, a hook, the first name; anything else becomes a skip.
6. **Add to the approval sheet** (Google Sheets), then **Approve** (form page).
7. **Read the sheet**, keep the rows marked `yes` with a `safe` email, and **Add to Instantly** (HTTP Request, Instantly API v2).

## Set it up

1. **Set up the Instantly campaign** with [instantly.md](instantly.md) and copy its id.
2. **Make the sheet:** a Google Sheet with this header row:
   `Name, Title, Company, Email, Email status, Email check, Hook, Subject, Body, Send (yes/no)`
3. **Import** the JSON in n8n: *Workflows > Import from file*.
4. **Add four credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on both MCP Client nodes.
   - **Anthropic** on the Claude node.
   - **Google Sheets** on both sheet nodes.
   - **Header Auth** named `Instantly API key`: name `Authorization`, value `Bearer <your Instantly API key>`. Select it on **Add to Instantly**.
5. **Fill in Your settings:** `sheet_url` (with its `gid`), `instantly_campaign_id`, and `offer`: two or three sentences on what you sell, to whom, and your ask.
6. **Test:** click *Execute workflow*, paste a search, ask for 5 leads, read the emails, write `yes` on the ones to load, and approve on the form.

## Good to know

- Each run exports the top of the search again. Use a fresh search each time, or a recurring export in Evaboot.
- An email on a link site such as linktr.ee is never loaded: the company's LinkedIn page lists that site as its website, so the email cannot be right.
- Nothing is sent. You preview the leads in Instantly and launch the campaign yourself.

Back to the [README](../README.md).
