# Building with Claude — Offline Ebook & Build System

A personal, offline-readable compilation of Anthropic's official Claude documentation,
cookbooks, courses, and engineering guidance — built into a single cohesive **EPUB** and
**AZW3** (Kindle) ebook for distraction-free reading.

This repo is both the *collection* and the *build system* that turns it into ebooks.

---

> **✅ Status: the pipeline is built and runs.** `make all` assembles ~280 curated sources
> into one EPUB + AZW3 with an eight-part table of contents. Quick start:
>
> ```bash
> make fetch       # download web-only docs (platform, Claude Code, essays) into docs/
> make notebooks   # convert the curated .ipynb set to Markdown
> make all         # assemble build/book.md -> output/*.epub + *.azw3
> ```
>
> **EPUB + AZW3 only — PDF is intentionally not built** (no TeX dependency). Curation lives in
> `manifest.txt`; the assembler is `build_book.py`; the web fetch is `fetch_docs.py`.

---

## What's in here

The collection is assembled from three kinds of official, first-party sources:

1. **Cloned Git repositories** — content-rich repos pulled with `git clone` (cookbooks,
   courses, skills, quickstarts, MCP spec). Refreshed with `git pull`.
2. **Fetched documentation pages** — the docs that live *only* as rendered pages
   (Claude Developer Platform and Claude Code), harvested as Markdown via Anthropic's
   `llms.txt` indexes using `anthropic_resources.py`.
3. **Curated notes** — saved guidance and the link index that has no machine-readable feed
   (engineering blog, news/research).

> **Why hybrid?** The cookbooks/courses/skills are real Git repos, so cloning gives you the
> true source (and history). But `platform.claude.com` and `code.claude.com` docs are not
> published as a public repo — they exist only as rendered pages — so those are fetched as
> `.md` via the `llms.txt` route instead. MCP is the exception: its docs *are* in a repo, so
> they come from the clone.

---

## Suggested project layout

```
claude-ebook/
├── README.md                  # this file
├── Makefile                   # build orchestration (fetch/notebooks/assemble/epub/azw3)
├── metadata.yaml              # ebook title/author/rights
├── manifest.txt               # curated reading order (8 Parts) — the source of truth
├── anthropic_resources.py     # llms.txt + GitHub harvester -> link index
├── fetch_docs.py              # fetch web-only docs (platform/Claude Code/essays) -> docs/
├── build_book.py              # assembler: manifest -> normalized build/book.md
├── test_*.py                  # unittest suites (make test)
├── frontmatter/               # authored preface + per-Part intros
├── assets/
│   └── cover.png              # optional ebook cover (1600×2560 works well)
├── anthropic-collection/      # cloned official repos (git-ignored, ~666 MB)
│   ├── claude-cookbooks/  courses/  prompt-eng-interactive-tutorial/
│   ├── skills/  anthropic-quickstarts/  claude-plugins-official/
│   └── modelcontextprotocol/
├── docs/                      # fetched .md pages (generated, git-ignored)
├── build/                     # intermediate book.md (generated, git-ignored)
└── output/                    # final EPUB / AZW3 (generated, git-ignored)
```

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| **Pandoc** (2.9+ works) | Markdown → EPUB | `apt install pandoc` or [pandoc.org](https://pandoc.org/installing.html) |
| **Calibre** (`ebook-convert`) | EPUB → AZW3 for Kindle | `apt install calibre` or [calibre-ebook.com](https://calibre-ebook.com) |
| **nbconvert** (via `uvx`) | `.ipynb` → Markdown | no install — `uvx --from nbconvert jupyter-nbconvert` |

> The only `apt` package strictly required is **`pandoc`** (Calibre is usually already present).
> nbconvert runs through `uvx`, so nothing is `pip install`ed. **No TeX Live** is needed because
> PDF output is not built. The Makefile detects Pandoc 2.x vs 3.x and uses the right chapter-split
> flag (`--epub-chapter-level=1` on 2.x, `--split-level=1` on 3.x) automatically.

---

## Build pipeline

The flow is: **fetch → normalize → assemble → render**, all wired into the `Makefile`.

### 1. Fetch web-only docs (`make fetch`)

`fetch_docs.py` downloads the content that isn't in any cloned repo — the Developer Platform
and Claude Code pages (published as `.md`) and the seven engineering essays (HTML, with the
`main-content` region extracted and converted to Markdown via Pandoc) — into `docs/`. It is
idempotent (skips existing files; `--force` re-fetches) and **fails loud**: any page that
can't be fetched is reported and the run exits non-zero.

### 2. Normalize notebooks → Markdown (`make notebooks`)

The cookbooks, courses, and prompting tutorial ship as Jupyter notebooks. The target converts
the **curated** notebook set (the directories the manifest draws from — not all 196) to `.md`
in place via `uvx`, so no Jupyter install is needed:

```bash
find <curated dirs> -name '*.ipynb' -print0 \
  | xargs -0 uvx --from nbconvert jupyter-nbconvert --to markdown
```

### 3. Assemble one cohesive `book.md` (`build_book.py`)

Rather than handing Pandoc a flat file list, `build_book.py` reads `manifest.txt` and produces
a single normalized `build/book.md`. For every source it **demotes headings** (each Part
becomes an H1 chapter group, each source a chapter beneath it), **rewrites relative image
paths** so they resolve after concatenation, **cleans MDX** (strips YAML frontmatter and JSX),
and adds a `*Source:*` line. The manifest uses three directives:

```
PART: Part I — Foundations      # a Part divider (top-level TOC entry)
~ frontmatter/part1.md          # authored include: inserted verbatim
docs/platform/get-started.md    # curated source: demoted + attributed
```

This is what turns ~280 files into a book with a clean eight-part table of contents instead
of a pile of concatenated pages. The manifest fails loud on any missing path.

> Keep the giant per-endpoint API reference **out** of the ebook (the harvester's `--no-api-ref`
> flag, and the manifest simply doesn't list it). 1,500 SDK-stub pages make a miserable book.

### 4. Render EPUB + AZW3 (`make all`)

Pandoc builds the EPUB from `book.md`; Calibre derives the AZW3 from the finished EPUB (cleaner
Kindle TOC than converting Markdown directly). The Makefile picks the right chapter-split flag
for your Pandoc version automatically.

```bash
make all     # -> output/building-with-claude.{epub,azw3}
```

`ebook-convert --output-profile` tunes margins/hyphenation for the target device — `kindle_pw`
for Paperwhite, `kindle_oasis`, or `kindle` for older models.

> **Reader matters:** the EPUB is built with `pandoc -f gfm`. Pandoc 2.x's *default* `markdown`
> reader hits exponential backtracking on a document this size (it ballooned to 54 GB RSS and
> never finished); the `gfm` reader (linear cmark parser) builds the whole ~6 MB book in about
> a minute at ~1 GB. Don't drop `-f gfm`. PDF is intentionally not produced.

---

## `metadata.yaml`

```yaml
---
title: "Building with Claude"
subtitle: "The Complete Guide — Anthropic's official documentation, cookbooks, courses, and engineering notes, compiled for offline study"
author: "Compiled from official Anthropic sources"
date: "2026-06-20"
lang: en-US
rights: "Compiled for personal offline study. Contains material © Anthropic and the respective repository licenses."
---
```

---

## `Makefile`

The real `Makefile` lives in the repo root — see it for the exact recipes. Targets:

| Target | Does |
|--------|------|
| `make fetch` | download web-only docs into `docs/` (`fetch_docs.py`) |
| `make notebooks` | convert the curated `.ipynb` set to `.md` via `uvx` nbconvert |
| `make assemble` | `manifest.txt` → `build/book.md` (`build_book.py`) |
| `make epub` / `make azw3` / `make all` | render EPUB, then AZW3 from it |
| `make test` | run the `unittest` suites |
| `make clean` / `make distclean` | remove build artifacts (also `docs/`) |

First run on a fresh clone:

```bash
make fetch && make notebooks && make all
```

---

## Refreshing the collection

```bash
# Update cloned repos
for d in anthropic-collection/*/; do git -C "$d" pull --ff-only; done

# Re-fetch the web-only docs and the link index
python3 fetch_docs.py --force
python3 anthropic_resources.py --no-api-ref

# Rebuild
make notebooks && make all
```

Consider a monthly cron/`systemd` timer if you want the ebooks to stay current — Anthropic
ships docs frequently.

---

## Known gotchas

- **Curation is in `manifest.txt`.** To add, remove, or reorder content, edit the manifest —
  not the code. It fails loud on any missing path, so a typo or a renamed source is caught
  immediately rather than silently dropped.
- **Image paths.** `build_book.py` rewrites relative image refs to resolve from the project
  root, and Pandoc searches `.:anthropic-collection`. Deeply nested notebook images can still
  miss; if a build warns about one, the source can be dropped from the manifest.
- **Use the `gfm` reader.** The build passes `-f gfm` on purpose. Pandoc 2.x's default
  `markdown` reader blows up exponentially on a doc this large (54 GB RSS, never finishes);
  `gfm` builds it in ~1 minute. The Makefile already does this — don't remove it.
- **Pandoc 2.x vs 3.x.** Chapter splitting is `--epub-chapter-level=1` on 2.x and
  `--split-level=1` on 3.x; the Makefile detects the version and picks the right one.
- **Size / volumes.** If one ebook feels unwieldy, split `manifest.txt` into per-theme
  manifests and build each with `make BOOK=… MANIFEST=…` — the assembler is manifest-driven.

---

## Scope & usage

This is a **personal, offline study compilation** of publicly available, official Anthropic
material. Each source remains under its original license/copyright (© Anthropic and the
respective repo licenses). Keep it for your own use; don't redistribute the compiled ebooks.
When in doubt, the canonical, always-current versions live at
`docs.claude.com` / `code.claude.com` and `github.com/anthropics`.

**Licensing split:** the **build tooling** in this repo (the scripts, Makefile, manifest,
front matter, and tests) is MIT-licensed — see [`LICENSE`](LICENSE). That license covers the
code only. It does **not** cover the third-party content the tooling fetches or compiles, nor
the generated EPUB/AZW3 — those stay under Anthropic's and the source repos' own licenses and
are intentionally git-ignored (`docs/`, `anthropic-collection/`, `output/`). Open-source the
tool freely; don't redistribute the content it assembles.
