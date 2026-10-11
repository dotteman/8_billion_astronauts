#!/usr/bin/env python3
"""Post, verify or remove test comments on every comment thread on the reading site.

  python3 tools/test_comments.py post      # add one test comment to each thread
  python3 tools/test_comments.py verify    # check giscus finds each thread and its test comment
  python3 tools/test_comments.py cleanup   # delete the test comments (and threads that only hold tests)

Threads are found the way the site's giscus widget finds them: by the SHA-1 of the
term ("<Section> · Praise" / "<Section> · Suggestions") in the discussion body.
Needs GITHUB_TOKEN with discussions: write. Standard library only.
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

CFG = build.CFG
G = CFG["giscus"]
OWNER, NAME = CFG["repo"].split("/")
SITE = f"https://{OWNER}.github.io{CFG.get('base_path', '/')}"
MARK = "<!-- 8ba-test-comment -->"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def gql(query, **variables):
    for wait in (0, 30, 60, 120, 180, 300):
        if wait:
            print(f"  rate limited; waiting {wait}s", flush=True)
            time.sleep(wait)
        try:
            return _gql(query, **variables)
        except RuntimeError as e:
            if "too quickly" not in str(e) and "RATE_LIMITED" not in str(e):
                raise
        except urllib.error.HTTPError as e:
            if e.code not in (403, 429):
                raise
    return _gql(query, **variables)


def _gql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read())
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


def pages():
    """(section name, page url) for every page with comment threads."""
    out = [("Whole book", SITE)]
    for s in build.parse(build.ROOT / CFG["manuscript"]):
        out.append((s["label"] + (f" · {s['sub']}" if s["sub"] else ""), f"{SITE}{s['slug']}/"))
    return out


def threads():
    for section, url in pages():
        for kind, cat in (("Praise", G["praise_category"]), ("Suggestions", G["suggestions_category"])):
            term = f"{section} · {kind}"
            yield section, url, kind, cat, term, hashlib.sha1(term.encode("utf-8")).hexdigest()


def all_discussions():
    q = """query($o:String!,$n:String!,$a:String){repository(owner:$o,name:$n){
      discussions(first:100,after:$a){pageInfo{hasNextPage endCursor}
        nodes{id title body category{id name}
          comments(first:100){nodes{id body}}}}}}"""
    out, after = [], None
    while True:
        d = gql(q, o=OWNER, n=NAME, a=after)["repository"]["discussions"]
        out += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            return out
        after = d["pageInfo"]["endCursor"]


def ids():
    q = "query($o:String!,$n:String!){repository(owner:$o,name:$n){id discussionCategories(first:50){nodes{id name}}}}"
    r = gql(q, o=OWNER, n=NAME)["repository"]
    names = [c["name"] for c in r["discussionCategories"]["nodes"]]
    print(f"::notice title=categories::{names}")
    return r["id"], {c["name"].strip().lower(): c["id"] for c in r["discussionCategories"]["nodes"]}


def post():
    repo_id, cats = ids()
    by_hash = {}
    for d in all_discussions():
        for h in [line.split("sha1:")[1].split("-->")[0].strip() for line in d["body"].splitlines() if "sha1:" in line]:
            by_hash[(h, d["category"]["name"].strip().lower())] = d
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    made = commented = 0
    for section, url, kind, cat, term, h in threads():
        d = by_hash.get((h, cat.strip().lower()))
        if d and any(MARK in c["body"] for c in d["comments"]["nodes"]):
            print(f"skip    {term} (already has a test comment)")
            continue
        if not d:
            # Same title and body shape giscus uses when a reader starts a thread.
            body = f"# {term}\n\n{url}\n\n<!-- sha1: {h} -->"
            d = gql("""mutation($r:ID!,$c:ID!,$t:String!,$b:String!){createDiscussion(input:{
                repositoryId:$r,categoryId:$c,title:$t,body:$b}){discussion{id url}}}""",
                    r=repo_id, c=cats[cat.strip().lower()], t=term, b=body)["createDiscussion"]["discussion"]
            made += 1
        gql("mutation($d:ID!,$b:String!){addDiscussionComment(input:{discussionId:$d,body:$b}){comment{id}}}",
            d=d["id"], b=f"Test comment ({kind}) for **{section}**, posted {stamp} to check that this thread works. "
                         f"It will be removed.\n\n{MARK}")
        commented += 1
        print(f"posted  {term}", flush=True)
        time.sleep(5)  # stay well under GitHub's content-creation rate limit
    print(f"\n{commented} test comments posted, {made} new threads created.")
    print(f"::notice title=post::{commented} test comments posted, {made} new threads created")


def verify():
    """Ask giscus for each thread exactly as the widget does, and look for the test comment."""
    failed = []
    for section, url, kind, cat, term, h in threads():
        qs = urllib.parse.urlencode({"repo": CFG["repo"], "term": term, "category": cat,
                                     "number": 0, "strict": "true", "last": 100})
        ok, note = False, ""
        for attempt in range(6):  # GitHub search can take a minute to index new threads
            try:
                with urllib.request.urlopen(f"https://giscus.app/api/discussions?{qs}", timeout=30) as r:
                    data = json.loads(r.read())
                comments = data["discussion"]["comments"]
                ok = any(MARK in (c.get("body") or "") or "check that this thread works" in (c.get("bodyHTML") or "")
                         for c in comments)
                note = f"{data['discussion']['totalCommentCount']} comment(s)"
                if ok:
                    break
            except urllib.error.HTTPError as e:
                note = f"HTTP {e.code}"
            time.sleep(10)
        print(f"{'PASS' if ok else 'FAIL'}  {term}  ({note})")
        if not ok:
            failed.append(term)
            print(f"::error title=Thread not found by giscus::{term} ({note})")
    total = sum(1 for _ in threads())
    print(f"\n{total - len(failed)}/{total} threads passed.")
    print(f"::notice title=verify::{total - len(failed)}/{total} threads passed")
    if failed:
        sys.exit(1)


def cleanup():
    hashes = {h for *_, h in threads()}
    removed_c = removed_d = 0
    for d in all_discussions():
        if not any(h in d["body"] for h in hashes):
            continue
        comments = d["comments"]["nodes"]
        tests = [c for c in comments if MARK in c["body"]]
        if tests and len(tests) == len(comments):
            gql("mutation($i:ID!){deleteDiscussion(input:{id:$i}){discussion{id}}}", i=d["id"])
            removed_d += 1
            removed_c += len(tests)
            print(f"deleted thread  {d['title']}")
        else:
            for c in tests:  # a reader has commented too: keep the thread, drop only our comments
                gql("mutation($i:ID!){deleteDiscussionComment(input:{id:$i}){comment{id}}}", i=c["id"])
                removed_c += 1
                print(f"deleted comment {d['title']}")
    print(f"\n{removed_c} test comments removed, {removed_d} test-only threads deleted.")
    print(f"::notice title=cleanup::{removed_c} test comments removed, {removed_d} test-only threads deleted")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("post", "verify", "cleanup"):
        sys.exit(__doc__)
    if mode != "verify" and not TOKEN:
        sys.exit("Set GITHUB_TOKEN.")
    try:
        {"post": post, "verify": verify, "cleanup": cleanup}[mode]()
    except Exception as e:
        detail = e.read().decode(errors="replace")[:500] if hasattr(e, "read") else ""
        msg = f"{type(e).__name__}: {e} {detail}".replace("\n", " ")[:900]
        print(f"::error title={mode} failed::{msg}")
        raise
