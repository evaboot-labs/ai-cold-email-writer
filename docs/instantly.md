# Set up the Instantly campaign

The agent adds each approved lead to an Instantly campaign with two fields: the email body in `personalization` and the subject in the custom variable `ai_subject`. The campaign uses them as its first email.

1. In Instantly, create a campaign (or open one).
2. In **Sequences**, set the first step's subject to `{{ai_subject}}` and its body to `{{personalization}}`. Nothing else in the body: the AI wrote the whole email.
3. Add later steps (follow-ups) as usual if you want them.
4. Copy the campaign id from the address bar (`app.instantly.ai/app/campaign/<id>/...`).
5. Put your Instantly API key in `.env` as `INSTANTLY_API_KEY` (Settings > Integrations > API keys, API v2).
6. Run the dry run, then the push with `--send` (see the skill, step 4).
7. Open the campaign, preview a few leads to read the real emails, attach your sending accounts, and launch.

Only leads with an Evaboot email status of `safe` are pushed, and never an email on a link-site domain such as linktr.ee.

Back to the [README](../README.md).
