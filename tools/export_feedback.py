#!/usr/bin/env python3
"""Export all reader feedback to one Markdown report on stdout.

Sources:
  * giscus threads (GitHub Discussions in the Praise and Suggestions categories)
  * Praise / Suggestion issues (labels "praise" and "suggestion")
  * Hypothesis passage notes on the reading site (public, or a private group with HYPOTHESIS_TOKEN)

Usage:  GITHUB_TOKEN=... python3 tools/export_feedback.py > reader-feedback.md
        (locally: GITHUB_TOKEN=$(gh auth token) python3 tools/export_feedback.py)
Standard library only.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

CFG = json.loads((Path(__file__).resolve().parent.parent / "site.config.json").read_text(encoding="utf-8"))
OWNER, NAME = CFG["repo"].split("/")
SITE = f"https://{OWNER}.github.io{CFG.get('base_path', '/')}"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    res = http("https://api.github.com/graphql", body,
               {"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


DISCUSSIONS = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    discussions(first:50, after:$after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        title url
        category { name }
        reactionGroups { content reactors { totalCount } }
        comments(first:100) {
          nodes {
            author { login } createdAt body url
            reactionGroups { content reactors { totalCount } }
            replies(first:50) { nodes { author { login } createdAt body } }
          }
        }
      }
    }
  }
}"""


def discussions():
    out, after = [], None
    while True:
        d = gh_graphql(DISCUSSIONS, {"owner": OWNER, "name": NAME, "after": after})["repository"]["discussions"]
        out += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            return out
        after = d["pageInfo"]["endCursor"]


def issues():
    out, page = [], 1
    while True:
        url = f"https://api.github.com/repos/{OWNER}/{NAME}/issues?state=all&per_page=100&page={page}"
        batch = http(url, headers={"Authorization": f"bearer {TOKEN}", "Accept": "application/vnd.github+json"})
        batch = [i for i in batch if "pull_request" not in i]
        out += [i for i in batch if {l["name"] for l in i["labels"]} & {"praise", "suggestion"}]
        if len(batch) < 100:
            return out
        page += 1


def field(body, label):
    m = re.search(rf"### {re.escape(label)}\s*\n+(.*?)(?=\n### |\Z)", body or "", flags=re.S)
    v = m.group(1).strip() if m else ""
    return "" if v == "_No response_" else v


def hypothesis():
    headers = {"Accept": "application/json"}
    if os.environ.get("HYPOTHESIS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['HYPOTHESIS_TOKEN']}"
    url = "https://api.hypothes.is/api/search?" + urllib.parse.urlencode(
        {"wildcard_uri": SITE + "*", "limit": 200, "sort": "created", "order": "asc"})
    try:
        return http(url, headers=headers).get("rows", [])
    except Exception as e:  # passage notes are optional
        print(f"<!-- Hypothesis export skipped: {e} -->")
        return []


def quote(text):
    return "\n".join("> " + line for line in text.strip().splitlines())


def main():
    by_section = defaultdict(lambda: {"Praise": [], "Suggestions": []})
    for d in discussions():
        cat = d["category"]["name"]
        if cat not in (CFG["giscus"]["praise_category"], CFG["giscus"]["suggestions_category"]):
            continue
        kind = "Praise" if cat == CFG["giscus"]["praise_category"] else "Suggestions"
        section = re.sub(r"\s·\s(Praise|Suggestions)$", "", d["title"])
        for c in d["comments"]["nodes"]:
            who = (c["author"] or {}).get("login", "ghost")
            entry = f"- **@{who}**, {c['createdAt'][:10]} ([thread]({c['url']}))\n{quote(c['body'])}"
            for r in c["replies"]["nodes"]:
                entry += f"\n  - reply from **@{(r['author'] or {}).get('login', 'ghost')}**: {r['body'].strip()}"
            by_section[section][kind].append(entry)

    for i in issues():
        labels = {l["name"] for l in i["labels"]}
        kind = "Praise" if "praise" in labels else "Suggestions"
        section = field(i["body"], "Chapter or section") or "Unspecified"
        passage = field(i["body"], "Passage (optional)")
        comment = field(i["body"], "What worked") or field(i["body"], "What could be better")
        note_kind = field(i["body"], "Kind of note")
        entry = f"- **@{i['user']['login']}**, {i['created_at'][:10]} ([issue #{i['number']}]({i['html_url']}))"
        if note_kind:
            entry += f" · {note_kind}"
        if passage:
            entry += "\n  - passage:\n" + quote(passage.strip("`\n "))
        entry += "\n" + quote(comment)
        by_section[section][kind].append(entry)

    notes = hypothesis()

    print(f"# Reader feedback: {CFG['title']}\n")
    total = sum(len(v["Praise"]) + len(v["Suggestions"]) for v in by_section.values())
    print(f"{total} comments and issues across {len(by_section)} sections, plus {len(notes)} passage notes.\n")
    for section in sorted(by_section):
        print(f"## {section}\n")
        for kind in ("Praise", "Suggestions"):
            items = by_section[section][kind]
            if items:
                print(f"### {kind} ({len(items)})\n")
                print("\n\n".join(items) + "\n")
    if notes:
        print("## Passage notes (Hypothesis)\n")
        for n in notes:
            page = n.get("uri", "").replace(SITE, "").strip("/") or "home"
            exact = ""
            for t in n.get("target", []):
                for sel in t.get("selector", []):
                    if sel.get("type") == "TextQuoteSelector":
                        exact = sel.get("exact", "")
            who = n.get("user", "").replace("acct:", "").split("@")[0]
            print(f"- **{page}** · {who}, {n.get('created', '')[:10]}")
            if exact:
                print(quote(exact))
            if n.get("text"):
                print(f"  - note: {n['text'].strip()}")
            print()


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("Set GITHUB_TOKEN (for example: GITHUB_TOKEN=$(gh auth token)).")
    main()
