"""Helpers for the AI cold email agent. The agent exports leads through the Evaboot MCP and writes the
emails itself; these commands keep the facts, the checks, the sheet and the Instantly push the same on
every run. Only `push` touches the network, and only with --send.

    python3 emails.py facts <export.json> > queue/facts.json            the real hooks per lead
    python3 emails.py check <facts.json> <emails.json>                  length, links, hooks, repetition
    python3 emails.py sheet <facts.json> <emails.json> > queue/queue.csv
    python3 emails.py push <queue.csv> --campaign <id> [--send]          approved rows to Instantly
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request

SUBJECT_MAX = 60       # characters
BODY_WORDS = (40, 110)  # a cold email that gets read is short
# Phrases that mark an email as a template. Extend the list in OFFER.md if you have your own.
CLICHES = ["hope this finds you", "i hope you're well", "just checking in", "quick question", "touch base",
           "circle back", "synergy", "game-changer", "revolutionize", "i came across your profile"]
SEND_STATUSES = {"safe"}  # only verified emails are pushed; "riskier" can bounce
# A company page that lists a link-in-bio site as its website gives emails on that domain: never send.
LINK_DOMAINS = {"linktr.ee", "bit.ly", "beacons.ai", "lnk.bio", "linkin.bio", "carrd.co", "about.me"}


def domain_note(email, company_domain):
    """Empty when the email domain matches the company's; otherwise a reason to look before sending."""
    if not email:
        return ""
    domain = email.rsplit("@", 1)[-1].lower()
    company = (company_domain or "").lower()
    if domain in LINK_DOMAINS:
        return f"email on {domain}, a link site: do not send"
    if company and not (domain == company or domain.endswith("." + company) or company.endswith("." + domain)):
        return f"email domain {domain} differs from the company's {company}: check it"
    return ""


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def facts(path):
    """export.json = the Evaboot export (get_export or the API). One entry per lead, only real fields."""
    out = []
    for p in json.load(open(path)).get("prospects") or []:
        months = (num(p.get("Years in Position")) or 0) * 12 + (num(p.get("Months in Position")) or 0)
        out.append({
            "id": p.get("Linkedin URL Unique ID") or p.get("Linkedin URL Public") or p.get("Full Name"),
            "first_name": p.get("First Name") or "",
            "last_name": p.get("Last Name") or "",
            "name": p.get("Full Name") or "",
            "email": p.get("Email") or "",
            "email_status": p.get("Email Status") or "not found",
            "email_check": domain_note(p.get("Email") or "", p.get("Company Domain")),
            "title": (p.get("Current Job") or "").strip(),
            "company": p.get("Company Name") or "",
            "months_in_role": months,
            "new_in_role": str(p.get("Has New Position")).lower() in ("true", "yes", "1") or months < 6,
            "headline": " ".join((p.get("Profile Headline") or "").split()),
            "summary": " ".join((p.get("Profile Summary") or "").split())[:700],
            "company_description": " ".join((p.get("Company Description") or "").split())[:400],
            "company_growth_1y_pct": num(p.get("Company Employee Growth 1 Year (%)")),
            "sales_team": num(p.get("Sales Team Size")),
            "linkedin": p.get("Linkedin URL Public") or "",
        })
    return out


def check(facts_path, emails_path):
    """Every lead gets an email or a skip with a reason, within the limits, with no template tells."""
    leads = {f["id"]: f for f in json.load(open(facts_path))}
    emails = json.load(open(emails_path))
    problems, openings = [], {}
    for e in emails:
        lead = leads.get(e["id"])
        if not lead:
            problems.append(f"unknown lead {e['id']}")
            continue
        who = lead["name"]
        if e.get("skip"):
            if not e.get("reason"):
                problems.append(f"{who}: skip without a reason")
            continue
        subject, body = e.get("subject", ""), e.get("body", "")
        words = len(body.split())
        if not e.get("hook"):
            problems.append(f"{who}: no hook named")
        if not subject or len(subject) > SUBJECT_MAX:
            problems.append(f"{who}: subject empty or over {SUBJECT_MAX} characters")
        if not BODY_WORDS[0] <= words <= BODY_WORDS[1]:
            problems.append(f"{who}: body is {words} words, keep it between {BODY_WORDS[0]} and {BODY_WORDS[1]}")
        if re.search(r"https?://|www\.", body):
            problems.append(f"{who}: a link in a first email hurts deliverability")
        first = re.split(r"[\s-]", lead["first_name"].strip())[0].lower()  # "Cristian-Daniel" -> "cristian"
        if not body.lower().startswith(f"hi {first}"):
            problems.append(f"{who}: open with the first name")
        for c in CLICHES:
            if c in body.lower():
                problems.append(f'{who}: template phrase "{c}"')
        opening = " ".join(body.split(".")[0].split()[2:7]).lower()
        openings[opening] = openings.get(opening, 0) + 1
    written = sum(1 for e in emails if not e.get("skip"))
    for o, c in openings.items():
        if written >= 6 and c > written / 3:
            problems.append(f'{c} of {written} emails open the same way ("{o}..."): vary it')
    missing = set(leads) - {e["id"] for e in emails}
    problems += [f"no email for {leads[i]['name']}" for i in missing]
    for p in problems:
        print("FAIL", p)
    print(f"{written} emails, {len(emails) - written} skipped, {len(problems)} problems")
    return 1 if problems else 0


def sheet(facts_path, emails_path):
    emails = {e["id"]: e for e in json.load(open(emails_path))}
    w = csv.writer(sys.stdout)
    w.writerow(["Name", "Title", "Company", "Email", "Email status", "Email check", "Hook", "Subject", "Body",
                "Send (yes/no)"])
    for f in json.load(open(facts_path)):
        e = emails.get(f["id"], {})
        skip = e.get("skip")
        w.writerow([f["name"], f["title"], f["company"], f["email"], f["email_status"], f.get("email_check", ""),
                    f"SKIP: {e.get('reason', '')}" if skip else e.get("hook", ""),
                    "" if skip else e.get("subject", ""), "" if skip else e.get("body", ""), ""])


def instantly(method, path, body=None):
    key = os.environ.get("INSTANTLY_API_KEY")
    if not key:
        sys.exit("INSTANTLY_API_KEY is not set: put it in .env and load it (set -a; . ./.env; set +a)")
    req = urllib.request.Request("https://api.instantly.ai/api/v2" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "User-Agent": "ai-cold-email-writer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")


def push(queue_path, campaign, send):
    """Rows marked yes, with a safe email, go to the campaign as leads. The body goes in
    `personalization` and the subject in the custom variable `ai_subject`: the campaign's step uses
    {{ai_subject}} as its subject and {{personalization}} as its body."""
    rows = [r for r in csv.DictReader(open(queue_path))
            if r["Send (yes/no)"].strip().lower() == "yes" and r["Body"]]
    ready = [r for r in rows if r["Email status"] in SEND_STATUSES and r["Email"]
             and "do not send" not in r.get("Email check", "")]
    for r in rows:
        if r not in ready:
            why = r.get("Email check") if "do not send" in r.get("Email check", "") else f"email status {r['Email status'] or 'missing'}"
            print(f"skip {r['Name']}: {why}")
    for r in ready:
        first, _, last = r["Name"].partition(" ")
        lead = {"campaign": campaign, "email": r["Email"], "first_name": first, "last_name": last,
                "company_name": r["Company"], "personalization": r["Body"],
                "custom_variables": {"ai_subject": r["Subject"]}, "skip_if_in_campaign": True}
        if send:
            instantly("POST", "/leads", lead)
        print(("added" if send else "dry run") + f": {r['Name']} <{r['Email']}>")
    print(f"{len(ready)} of {len(rows)} approved rows {'added to' if send else 'ready for'} campaign {campaign}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("facts"); a.add_argument("export")
    a = sub.add_parser("check"); a.add_argument("facts"); a.add_argument("emails")
    a = sub.add_parser("sheet"); a.add_argument("facts"); a.add_argument("emails")
    a = sub.add_parser("push"); a.add_argument("queue"); a.add_argument("--campaign", required=True)
    a.add_argument("--send", action="store_true", help="really add the leads; without it, a dry run")
    args = ap.parse_args()
    if args.cmd == "facts":
        print(json.dumps(facts(args.export), indent=2, ensure_ascii=False))
    elif args.cmd == "check":
        sys.exit(check(args.facts, args.emails))
    elif args.cmd == "sheet":
        sheet(args.facts, args.emails)
    else:
        push(args.queue, args.campaign, args.send)


if __name__ == "__main__":
    main()
