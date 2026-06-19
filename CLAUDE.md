# CLAUDE.md — claude-ebook

Build system + collection that compiles Anthropic's official Claude docs, cookbooks, courses,
and engineering guidance into offline ebooks (PDF / EPUB / AZW3).

## Ground truth (read before trusting the README)

**The README is a build guide / blueprint, not a description of finished tooling.** It documents
the *planned* ebook pipeline. Do not assume those files exist.

What actually exists today:

- `anthropic_resources.py` — the resource harvester (the only real code). Stdlib-only, Python 3.8+.
- `anthropic_resources.{md,json,csv}` — generated link index (~811 links). Committed outputs.
- `anthropic-collection/` — 7 cloned official repos (~666 MB). **Git-ignored** — never `git add` it.
- `sources.md` — raw research transcript that produced the plan. Notes, not code.

What is **planned but not built** (don't try to run these):

- `metadata.yaml`, `manifest.txt`, `Makefile`, `assets/cover.png`, and the `docs/` content corpus.
- The Pandoc → EPUB/PDF and Calibre → AZW3 build. `make all` / `make notebooks` will not work yet.

## Gotchas

- **The harvester emits a link *index*, not page content.** Pandoc needs `.md` files on disk; the
  non-repo docs (`platform.claude.com`, `code.claude.com`) still need a content-fetch step that
  doesn't exist yet. The cloned repos + notebooks already have their content locally.
- **196 notebooks are unconverted.** `jupyter nbconvert` has never been run over the collection.
- **Refresh `anthropic-collection/` with `git pull`, not by re-committing** — it's intentionally ignored.

## Commands that work today

```bash
python3 anthropic_resources.py --no-api-ref   # rebuild the index (skips ~1500 API-stub pages)
```

Flags: `--no-local` (skip repo enumeration), `--github-api` (enumerate orgs via REST),
`--out PREFIX` (custom output path). See the module docstring for the full list.

## When building the planned pipeline

Keep this file and the README in sync with reality: as each planned piece becomes real, move it
out of "planned" in both. Per global setup, use `uvx nbconvert` rather than `pip install nbconvert`.
