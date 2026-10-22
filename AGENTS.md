# Agent instructions

This repo is an AI cold email agent. It exports leads from a Sales Navigator search with Evaboot, writes one short first email per lead from real profile and company data, checks every email, queues them in a sheet for the user to approve, and loads the approved ones into an Instantly campaign. The user launches the campaign; the agent never sends an email. When the user asks to automate cold emails with AI or to write personalised cold emails:

1. Follow the skill in `skills/ai-cold-emails/SKILL.md` step by step.
2. Read `OFFER.md` for what the user sells and the writing rules. If it says `Status: EXAMPLE`, ask the user and update it.
3. Use `emails.py` for the facts, the checks, the sheet and the Instantly push. The Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them. For the Instantly campaign, follow `docs/instantly.md`.
5. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Confirm with the user before every export (1 Evaboot credit per lead) and before `emails.py push --send`. Never launch a campaign and never send an email. Never ask for or handle an API key: the user writes them into `.env`. Never commit `.env`, `data/` or `queue/`: they hold real people's data.
