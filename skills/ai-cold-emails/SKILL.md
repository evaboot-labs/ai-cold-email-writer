---
name: ai-cold-emails
description: Write a personalised first cold email for every lead with AI, from real data, and load the approved ones into Instantly - build or reuse a Sales Navigator search, export the leads with verified emails through Evaboot, write one short email per lead from profile and company facts, check length, links, template phrases and email domains, queue them in a sheet for approval, then push the approved rows into an Instantly campaign. Use when the user asks to automate cold emails with AI, write personalised cold emails, or fill an Instantly campaign with AI-written emails.
---

# AI cold emails

This skill runs inside a clone of https://github.com/evaboot-labs/ai-cold-email-writer: it uses the repo's `emails.py`, `OFFER.md` and `docs/`. If `emails.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). Every tool named below is an Evaboot MCP tool. You write the emails yourself. `emails.py` turns the export into facts, checks the emails, builds the sheet and, with `--send`, pushes approved rows to Instantly.

## Rules

- **Nothing is sent from this skill.** The push only adds leads to an Instantly campaign; the user launches the campaign themselves, after reading the emails.
- Confirm with the user before every call that spends credits or writes somewhere: `export_sn_search_or_list`, `create_recurring_export`, and `emails.py push --send`. Show the count and the cost (1 Evaboot credit per exported lead), then wait for a yes.
- Write each email only from that lead's facts in `queue/facts.json` and the offer in `OFFER.md`. Never invent a customer, a number or a result.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` and `INSTANTLY_API_KEY` into `.env`.
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. If the Evaboot MCP tools are not in this session, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder: `EVABOOT_API_KEY` is read only when the agent starts.
2. Otherwise call `verify_token` and `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click Export with Evaboot, then call the quota again.
3. Run `mkdir -p data queue`, and `cp .env.example .env` if `.env` is missing (the user fills in the keys). Both folders and `.env` are git-ignored: they hold real people's data and secrets.
4. Read `OFFER.md`. If it says `Status: EXAMPLE`, ask the user what they sell, to whom, what proof they may use and what they ask for. Rewrite the file and set `Status: yours`.

## Step 1: the leads

Ask where the leads come from: an Evaboot export they already have (use it, no credits), the latest run of a recurring export (`get_recurring_export`, then `get_export`), or a new search. Say the cost before any new export: 1 credit per lead. For a new search:

1. Call `build_sn_search_from_prompt` with **people only** (titles, seniority, geography, and a signal such as "changed jobs recently"), with `max_results` = how many emails they want this time. Never put an industry or a company size in this request: that starts a company-first crawl.
2. Poll `get_search_build`, then add industry and size to the URL yourself if needed (the same `INDUSTRY` and `COMPANY_HEADCOUNT` filters the account's other searches use).
3. Call `search_sn_leads` on the URL with `count: 25`. It is free. Show the total and the first titles and companies. Tighten the search if the list is noisy.
4. On a yes, call `export_sn_search_or_list` with `max_results`, poll `get_export` until `EXECUTED`, and save the JSON to `data/export.json`.

Then:

```bash
python3 emails.py facts data/export.json > queue/facts.json
```

## Step 2: write the emails

Read `OFFER.md` again, then write `queue/emails.json`: one entry per lead in `facts.json`, either `{"id", "hook", "subject", "body"}` or `{"id", "skip": true, "reason"}`.

- Skip leads with no email, an `email_status` other than `safe` (only safe emails are loaded into Instantly), or an `email_check` that says "do not send". A link site is a link-in-bio or link-shortener domain such as linktr.ee: a company page that lists one as its website gives emails that cannot be right.
- The hook is the fact the email rests on, in a few words. Good hooks: a new role (`new_in_role`), company growth (`company_growth_1y_pct`, always "in a year"), the size of the sales team (`sales_team`), one concrete line of the lead's own `headline` or `summary`.
- Body: "Hi <first name>," then one short paragraph on them, one on the offer, and a one-line ask. Use `\n\n` between paragraphs.

```bash
python3 emails.py check queue/facts.json queue/emails.json
```

Fix every `FAIL` and run it again.

## Step 3: approval

```bash
python3 emails.py sheet queue/facts.json queue/emails.json > queue/queue.csv
```

Put it where the user reviews: a Google Sheet when the session has a Google Drive tool, otherwise give them the CSV path to open in any spreadsheet app (Excel, Numbers, Google Sheets import). Point out the rows with an `Email check` note. Ask them to edit the emails they want and write `yes` in `Send (yes/no)`. Wait.

## Step 4: load the approved emails into Instantly

1. In Instantly, the user needs a campaign whose first step has the subject `{{ai_subject}}` and the body `{{personalization}}` (see `docs/instantly.md`). Ask for its id (in the campaign URL).
2. Dry run: `python3 emails.py push queue/queue.csv --campaign <id>`. Show which rows go and which are skipped (only `safe` emails, never a link site).
3. On a yes: `python3 emails.py push queue/queue.csv --campaign <id> --send`.
4. Ask the user to open the campaign, preview two or three leads, and launch it themselves.

## Step 5 (optional): every week

Offer `save_search`, then `create_recurring_export` on it (weekly). Each run returns only new people, so each week's emails go to fresh leads. Each run spends credits; say so before creating it. Then run steps 2 to 4 on each new export.
