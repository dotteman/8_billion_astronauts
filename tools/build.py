#!/usr/bin/env python3
"""Build the 8 Billion Astronauts reading site from the manuscript DOCX.

Usage: python3 tools/build.py [output_dir]      (default: _site)

Standard library only, so it runs unchanged in GitHub Actions.
Reads site.config.json for the title, files and comment settings.
"""
import html
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"
CFG = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))


def resolve_category_ids(cfg):
    """Fill missing giscus category IDs by looking the categories up by name.

    Runs in GitHub Actions, where GITHUB_TOKEN is set. IDs already in
    site.config.json win. Without a token or on any error, the site falls back
    to the issue-form links.
    """
    import os
    import urllib.request
    g = cfg.get("giscus", {})
    token = os.environ.get("GITHUB_TOKEN")
    if not token or (g.get("praise_category_id") and g.get("suggestions_category_id")):
        return
    owner, name = cfg["repo"].split("/")
    q = {"query": "query($o:String!,$n:String!){repository(owner:$o,name:$n){discussionCategories(first:50){nodes{id name}}}}",
         "variables": {"o": owner, "n": name}}
    req = urllib.request.Request("https://api.github.com/graphql", data=json.dumps(q).encode(),
                                 headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            nodes = json.loads(r.read())["data"]["repository"]["discussionCategories"]["nodes"]
    except Exception as e:
        print(f"giscus: category lookup failed ({e}); using issue-form links", file=sys.stderr)
        return
    ids = {n["name"].strip().lower(): n["id"] for n in nodes}
    for key in ("praise", "suggestions"):
        if not g.get(f"{key}_category_id"):
            g[f"{key}_category_id"] = ids.get(g[f"{key}_category"].strip().lower(), "")
    print(f"giscus: categories found {sorted(ids)}; praise={bool(g['praise_category_id'])} "
          f"suggestions={bool(g['suggestions_category_id'])}", file=sys.stderr)


# ---------------------------------------------------------------- parse DOCX
def load_paragraphs(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)


def runs(p):
    out = []
    for r in re.findall(r"<w:r>.*?</w:r>|<w:r .*?</w:r>", p, flags=re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", r))
        if t:
            out.append((html.unescape(t), bool(re.search(r'<w:i/>|<w:i w:val="(true|1)"/>', r))))
    return out


def text(p):
    return "".join(t for t, _ in runs(p))


def render(p):
    s = ""
    for t, italic in runs(p):
        e = html.escape(t, quote=False)
        e = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" rel="noopener">\1</a>', e)
        s += f"<em>{e}</em>" if italic else e
    return s


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse(docx_path):
    paras = load_paragraphs(docx_path)
    start = next(i for i, p in enumerate(paras) if "Heading1" in p)
    toc = [text(p) for p in paras[:start]
           if (" · " in text(p) or text(p) == "Note on the Science") and not text(p).startswith("Revised")]
    sections, cur, i = [], None, start
    while i < len(paras):
        p = paras[i]
        if "Heading1" in p:
            label, _, sub = toc[len(sections)].partition(" · ")
            cur = {"label": label, "sub": sub, "slug": slug(label), "blocks": []}
            sections.append(cur)
            i += 2 if sub and i + 1 < len(paras) and text(paras[i + 1]).strip() == sub else 1
            continue
        t = text(p)
        if not t.strip():
            i += 1
            continue
        if 'w:left="1080"' in p:  # chapter-opening document
            grp = []
            while i < len(paras) and 'w:left="1080"' in paras[i]:
                grp.append(text(paras[i]))
                i += 1
            cur["blocks"].append(("doc", grp))
            continue
        if t.strip() == "* * *":
            cur["blocks"].append(("break", None))
        elif t.strip() == "Scientific background":
            cur["blocks"].append(("h3", t))
        elif '<w:jc w:val="center"/>' in p:
            cur["blocks"].append(("display", render(p)))
        else:
            cur["blocks"].append(("p", render(p)))
        i += 1
    return sections


# ---------------------------------------------------------------- render HTML
def chapter_body(s):
    out, first = [], True
    for kind, val in s["blocks"]:
        if kind == "doc":
            label, *lines, clock = val
            out.append('<aside class="doc"><p class="doc-label">' + html.escape(label) + "</p>"
                       + "".join(f'<p class="doc-line">{html.escape(l)}</p>' for l in lines)
                       + f'<p class="doc-clock">{html.escape(clock)}</p></aside>')
            first = True
        elif kind == "break":
            out.append('<p class="break" aria-hidden="true">* * *</p>')
            first = True
        elif kind == "h3":
            out.append(f'<h2 class="sub">{html.escape(val)}</h2>')
            first = True
        elif kind == "display":
            out.append(f'<p class="display">{val}</p>')
        else:
            out.append(f'<p class="first">{val}</p>' if first else f"<p>{val}</p>")
            first = False
    return "\n".join(out)


def feedback(name, term_base, cfg):
    g = cfg["giscus"]
    ready = bool(g.get("praise_category_id") and g.get("suggestions_category_id"))
    repo = cfg["repo"]
    q = html.escape(name)
    from urllib.parse import quote
    issue = lambda tpl: f"https://github.com/{repo}/issues/new?template={tpl}&section={quote(name)}"
    attrs = (f'data-repo="{repo}" data-repo-id="{g["repo_id"]}" '
             f'data-praise-cat="{html.escape(g["praise_category"])}" data-praise-cat-id="{g.get("praise_category_id", "")}" '
             f'data-sugg-cat="{html.escape(g["suggestions_category"])}" data-sugg-cat-id="{g.get("suggestions_category_id", "")}" '
             f'data-term="{html.escape(term_base)}"')
    tabs = ("" if not ready else
            '<div class="fb-tabs" role="tablist">'
            '<button class="tab praise" role="tab" data-kind="praise" aria-selected="false">What worked</button>'
            '<button class="tab improve" role="tab" data-kind="suggestions" aria-selected="false">What could be better</button>'
            "</div><div class=\"giscus-host\"></div>")
    pending = ("" if ready else
               '<p class="fb-pending">Comment threads open soon. Until then, use the forms below.</p>')
    return (f'<section class="fb" id="reader-notes" {attrs}>'
            f'<h2 class="fb-q">Reader notes on {q}</h2>{tabs}{pending}'
            f'<p class="fb-forms">Prefer a private-ish note? '
            f'<a href="{issue("praise.yml")}" rel="noopener">Send praise</a> or '
            f'<a href="{issue("suggestion.yml")}" rel="noopener">suggest an improvement</a> as a GitHub issue.</p>'
            "</section>")


def page(title, body, cfg, depth, extra_head="", hypothesis=False):
    up = "../" * depth
    hyp = ""
    if hypothesis and cfg.get("hypothesis"):
        hyp = ('<script>window.hypothesisConfig=function(){return{openSidebar:false,showHighlights:"always"}};</script>'
               '<script async src="https://hypothes.is/embed.js"></script>')
    pdf = f'{up}downloads/{Path(cfg["pdf"]).name}'
    docx = f'{up}downloads/{Path(cfg["manuscript"]).name}'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(cfg['title'])}, a novel by {html.escape(cfg['author'])}.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,600;1,7..72,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="icon" href="{up}assets/cover.jpg">
{extra_head}{hyp}
</head>
<body>
<div class="bar"><div class="bar-in">
  <a class="btn" href="{up}#contents">Contents</a>
  <a class="brand" href="{up}">{html.escape(cfg['title'])}</a>
  <span class="spacer"></span>
  <a class="btn" href="{pdf}" download>PDF</a>
  <a class="btn" href="{docx}" download>Word</a>
</div><div class="progress" id="progress"></div></div>
{body}
<script src="{up}assets/site.js"></script>
</body>
</html>
"""


def build():
    resolve_category_ids(CFG)
    sections = parse(ROOT / CFG["manuscript"])
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    (OUT / "downloads").mkdir()
    shutil.copy(TOOLS / "assets" / "style.css", OUT / "assets")
    shutil.copy(TOOLS / "assets" / "site.js", OUT / "assets")
    shutil.copy(TOOLS / "assets" / "cover.jpg", OUT / "assets")
    shutil.copy(ROOT / CFG["pdf"], OUT / "downloads")
    shutil.copy(ROOT / CFG["manuscript"], OUT / "downloads")
    (OUT / ".nojekyll").write_text("")

    words = sum(len(re.sub("<[^>]+>", "", v).split()) for s in sections for k, v in s["blocks"] if k in ("p", "display"))

    # chapter pages
    for n, s in enumerate(sections):
        name = s["label"] + (f" · {s['sub']}" if s["sub"] else "")
        prev_s = sections[n - 1] if n else None
        next_s = sections[n + 1] if n + 1 < len(sections) else None
        nav = '<nav class="pager" aria-label="Chapters">'
        nav += (f'<a href="../{prev_s["slug"]}/" rel="prev"><span>Previous</span>{html.escape(prev_s["label"])}</a>' if prev_s else "<span></span>")
        nav += (f'<a href="../{next_s["slug"]}/" rel="next" class="next"><span>Next</span>{html.escape(next_s["label"])}</a>' if next_s else "<span></span>")
        nav += "</nav>"
        body = (f'<main class="read" data-chapter="{s["slug"]}" data-label="{html.escape(s["label"])}">'
                f'<header class="ch-head"><p class="ch-label">{html.escape(s["label"])}</p>'
                + (f'<h1 class="ch-title">{html.escape(s["sub"])}</h1>' if s["sub"] else f'<h1 class="ch-title">{html.escape(s["label"])}</h1>')
                + "</header>" + chapter_body(s) + nav
                + feedback(name, name, CFG) + "</main>")
        d = OUT / s["slug"]
        d.mkdir()
        (d / "index.html").write_text(page(f"{name} | {CFG['title']}", body, CFG, 1, hypothesis=True), encoding="utf-8")

    # home page
    items = "".join(
        f'<li><a href="{s["slug"]}/"><span class="n">{html.escape(s["label"])}</span>'
        + (f'<span class="t">{html.escape(s["sub"])}</span>' if s["sub"] else "") + "</a></li>"
        for s in sections)
    pdf = f'downloads/{Path(CFG["pdf"]).name}'
    docx = f'downloads/{Path(CFG["manuscript"]).name}'
    body = f"""<main class="home">
<div class="opening">
  <img src="assets/cover.jpg" alt="Cover: six stars arranged in a ring around an empty patch of night sky" width="360" height="480">
  <div>
    <h1>{html.escape(CFG['title'])}</h1>
    <p class="by">A novel by {html.escape(CFG['author'])}</p>
    <p class="meta">Book One · {len(sections)} parts · about {round(words, -2):,} words · {html.escape(CFG['edition'])}</p>
    <div class="actions">
      <a class="btn primary" id="startBtn" href="{sections[0]['slug']}/">Start reading</a>
      <a class="btn" href="{pdf}" download>Download PDF</a>
      <a class="btn" href="{docx}" download>Download Word</a>
    </div>
  </div>
</div>
<section class="howto">
  <h2>Reader notes are welcome</h2>
  <p>Every chapter ends with two comment threads: <strong>What worked</strong> and <strong>What could be better</strong>. They use a free GitHub account.</p>
  <p>To comment on a specific passage, highlight the text in any chapter and choose <strong>Annotate</strong>. Passage notes use a free <a href="https://web.hypothes.is/" rel="noopener">Hypothesis</a> account.</p>
</section>
<section id="contents">
  <h2 class="fb-q">Contents</h2>
  <ol class="contents">{items}</ol>
</section>
{feedback("the whole book", "Whole book", CFG)}
</main>"""
    (OUT / "index.html").write_text(page(CFG["title"], body, CFG, 0), encoding="utf-8")
    (OUT / "404.html").write_text(page(f"Page not found | {CFG['title']}",
        '<main class="read"><h1 class="ch-title">This page drifted out of orbit.</h1>'
        '<p class="first"><a href="./">Back to the contents</a></p></main>', CFG, 0,
        extra_head=f'<base href="{CFG.get("base_path", "/")}">'), encoding="utf-8")
    print(f"built {len(sections)} sections, {words} words -> {OUT}")


if __name__ == "__main__":
    build()
