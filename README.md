# 8 Billion Astronauts

*A novel by Dave L. Otteman.* Book One, Revised 4 (October 2026).

**Read it:** https://dotteman.github.io/8_billion_astronauts/

A rogue black hole will pass the Sun in seventeen years. It won't hit anything. It will throw the whole Solar System out of its neighborhood at three thousand kilometers per second, and nobody can promise Earth will still be livable afterward. Eight billion people can't be evacuated, so they get to work.

*We are all astronauts, and Earth is the ship.*

## Leaving feedback

- **Comment threads.** Every chapter page ends with **What worked** and **What could be better** threads, powered by [giscus](https://giscus.app). They need a free GitHub account.
- **Passage notes.** Highlight any text on a chapter page and choose **Annotate**. These use a free [Hypothesis](https://web.hypothes.is/) account.
- **Forms.** [Send praise](../../issues/new?template=praise.yml) or [suggest an improvement](../../issues/new?template=suggestion.yml) as a GitHub issue.

## How this repo works

| Path | What it is |
|---|---|
| `manuscript/` | The source of truth: the manuscript DOCX and its PDF. |
| `site.config.json` | Title, edition, file names and comment settings. |
| `tools/build.py` | Builds the reading site from the DOCX (Python standard library only). |
| `tools/assets/` | Site stylesheet, script and cover image. |
| `tools/export_feedback.py` | Collects every comment, issue and passage note into one Markdown report. |
| `.github/workflows/pages.yml` | Rebuilds and publishes the site on every push to `main`. |
| `.github/workflows/export-feedback.yml` | Manual run that produces `reader-feedback.md` as a downloadable artifact. |

### Publishing a new revision
1. Replace `manuscript/8-billion-astronauts.docx` and `.pdf`.
2. Update `edition` in `site.config.json`.
3. Push to `main`. The site rebuilds in about a minute.

Comment threads are matched to chapters by name (for example *Chapter Seven · The Missing Shipment · Praise*). Renaming a chapter starts a new thread for it. The old thread stays in Discussions and in the export.

Preview locally: `python3 tools/build.py && python3 -m http.server -d _site`

## One-time setup

1. **Pages:** Settings → Pages → Source: **GitHub Actions**.
2. **Discussions:** Settings → General → Features → check **Discussions**.
3. **Discussion categories:** in the Discussions tab, create two categories named **Praise** and **Suggestions**, both with the **Announcement** format, so only giscus and maintainers can start threads.
4. **giscus app:** install https://github.com/apps/giscus on this repository only.
5. **Category IDs:** nothing to do. The publish workflow looks up the **Praise** and **Suggestions** category IDs by name on every build. To pin them instead, put the IDs from https://giscus.app into `praise_category_id` and `suggestions_category_id` in `site.config.json`. If the lookup finds no categories, chapter pages show the issue-form links instead of threads.
6. **Labels:** create labels `praise` and `suggestion` so issue forms are tagged.
7. **Optional, private passage notes:** Hypothesis notes are public by default. To keep them private, create a Hypothesis group, share its invite link with readers, and add a Hypothesis API token as the `HYPOTHESIS_TOKEN` repository secret so the export can read the group.

## Exporting feedback

Actions → **Export reader feedback** → **Run workflow**, then download the `reader-feedback` artifact. Or run locally:

```bash
GITHUB_TOKEN=$(gh auth token) python3 tools/export_feedback.py > reader-feedback.md
```

## Copyright

© 2026 Dave L. Otteman. All rights reserved. The text is shared for reading and feedback. It is not licensed for reuse or redistribution. The site's code (`tools/`, `.github/`) may be reused freely.
