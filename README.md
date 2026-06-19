# Anthropic & Claude — Official Resource Collection

A personal, offline-readable compilation of Anthropic's official Claude documentation,
cookbooks, courses, and engineering guidance — built into **PDF**, **EPUB**, and **AZW3**
(Kindle) for distraction-free reading.

This repo is both the *collection* and the *build system* that turns it into ebooks.

---

> **📌 Status: this README is currently a build guide / blueprint, not a description of finished tooling.**
>
> What exists today: the resource harvester (`anthropic_resources.py`), its generated index
> (`anthropic_resources.{md,json,csv}`), and the cloned official repos under
> `anthropic-collection/`. The ebook pipeline below — `metadata.yaml`, `manifest.txt`, the
> `Makefile`, and the Pandoc/Calibre build — is the **planned design**; those files are not in
> the repo yet. Sections describing them are the spec to implement against.
>
> As we build each piece, update this README to match, removing it from "planned" once it's
> real. The goal is for this file to converge on an accurate description of the codebase.

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
anthropic-collection/
├── README.md                  # this file
├── Makefile                   # build orchestration (see "Building")
├── metadata.yaml              # ebook title/author/rights
├── manifest.txt               # reading order — one source path per line
├── anthropic_resources.py     # llms.txt + GitHub harvester
├── assets/
│   └── cover.png              # optional ebook cover (1600×2560 works well)
├── repos/                     # cloned official repositories
│   ├── claude-cookbooks/
│   ├── courses/
│   ├── prompt-eng-interactive-tutorial/
│   ├── skills/
│   ├── anthropic-quickstarts/
│   ├── claude-plugins-official/
│   └── modelcontextprotocol/
├── docs/                      # fetched .md pages (platform + claude code)
├── notes/                     # curated guidance, saved responses, link index
├── build/                     # intermediate artifacts (generated)
└── output/                    # final PDF / EPUB / AZW3 (generated)
```

---

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| **Pandoc** ≥ 3.0 | Markdown → EPUB / PDF | `apt install pandoc` or [pandoc.org](https://pandoc.org/installing.html) |
| **TeX Live** (xelatex) | PDF engine with full Unicode | `apt install texlive-xetex texlive-fonts-recommended` |
| **Calibre** (`ebook-convert`) | EPUB → AZW3 for Kindle | `apt install calibre` or [calibre-ebook.com](https://calibre-ebook.com) |
| **Jupyter / nbconvert** | `.ipynb` → Markdown | `pip install nbconvert` |

> On Zorin OS / Ubuntu, all four are in apt except `nbconvert` (pip). `xelatex` is preferred
> over the default `pdflatex` because the docs contain emoji, box-drawing characters, and CJK
> snippets that `pdflatex` chokes on.

---

## Build pipeline

The flow is: **normalize → order → render**.

### 1. Normalize notebooks → Markdown

The cookbooks and courses ship as Jupyter notebooks. Pandoc reads Markdown, not `.ipynb`,
so convert them in place first (outputs a `.md` beside each `.ipynb`, plus a `_files/` dir
for any embedded images):

```bash
find repos -name '*.ipynb' -exec jupyter nbconvert --to markdown {} +
```

### 2. Define reading order (`manifest.txt`)

Pandoc concatenates inputs **in the order you list them**, so a thoughtful order is what
separates a book from a pile of files. List one path per line; comments (`#`) and blank lines
are fine if you strip them before passing to Pandoc (the Makefile does). A sensible spine:

```
# --- Foundations ---
docs/intro.md
docs/get-started.md
notes/overview.md

# --- Prompt engineering ---
docs/prompt-engineering-overview.md
docs/claude-prompting-best-practices.md
repos/prompt-eng-interactive-tutorial/README.md

# --- Tools & agents ---
docs/tool-use-overview.md
docs/agent-skills-overview.md
notes/building-effective-agents.md

# --- MCP ---
repos/modelcontextprotocol/docs/getting-started/intro.md

# --- Claude Code ---
docs/claude-code-overview.md
docs/claude-code-best-practices.md

# --- Cookbooks & courses (longer-form) ---
repos/claude-cookbooks/README.md
repos/courses/README.md
```

> Keep the giant per-endpoint API reference **out** of the ebook (run the harvester with
> `--no-api-ref`). 1,500 SDK-stub pages make a miserable book and a 50 MB PDF; keep that
> material as searchable files on disk instead.

### 3. Render EPUB, PDF, and AZW3

EPUB and PDF are built directly by Pandoc from the same manifest. AZW3 is derived from the
finished EPUB via Calibre (don't build it from Markdown directly — converting the polished
EPUB gives a cleaner Kindle TOC):

```bash
# EPUB
pandoc metadata.yaml $(grep -v '^#' manifest.txt | grep .) \
  --toc --toc-depth=2 --split-level=1 \
  --resource-path=.:repos:docs \
  --epub-cover-image=assets/cover.png \
  -o output/anthropic-guide.epub

# PDF (xelatex)
pandoc metadata.yaml $(grep -v '^#' manifest.txt | grep .) \
  --toc --toc-depth=2 --pdf-engine=xelatex \
  --resource-path=.:repos:docs \
  -V geometry:margin=1in -V colorlinks=true \
  -V mainfont="DejaVu Sans" -V monofont="DejaVu Sans Mono" \
  -o output/anthropic-guide.pdf

# AZW3 (from the EPUB) — set the profile to your device
ebook-convert output/anthropic-guide.epub output/anthropic-guide.azw3 \
  --output-profile kindle_pw
```

`--output-profile` tunes margins/hyphenation for the target device — `kindle_pw` for
Paperwhite, `kindle_oasis`, or `kindle` for older models.

---

## `metadata.yaml`

```yaml
---
title: "Anthropic & Claude — Official Resource Collection"
subtitle: "Documentation, cookbooks, courses, and engineering notes"
author: "<your name>"
date: "2026-06-20"
lang: en-US
rights: "Compiled for personal offline study. Contains material © Anthropic."
---
```

---

## `Makefile`

Reproducible one-command builds. `make all` produces all three formats.

```makefile
TITLE     := anthropic-guide
OUTPUT    := output
META      := metadata.yaml
MANIFEST  := manifest.txt
COVER     := assets/cover.png
RESOURCES := .:repos:docs

# Reading-order file list, comments/blanks stripped
SOURCES := $(shell grep -v '^\#' $(MANIFEST) | grep .)

.PHONY: all notebooks epub pdf azw3 clean

all: epub pdf azw3

notebooks:
	find repos -name '*.ipynb' -exec jupyter nbconvert --to markdown {} +

epub: $(OUTPUT)/$(TITLE).epub
$(OUTPUT)/$(TITLE).epub: $(META) $(MANIFEST) $(SOURCES)
	@mkdir -p $(OUTPUT)
	pandoc $(META) $(SOURCES) \
	  --toc --toc-depth=2 --split-level=1 \
	  --resource-path=$(RESOURCES) \
	  $(if $(wildcard $(COVER)),--epub-cover-image=$(COVER),) \
	  -o $@

pdf: $(OUTPUT)/$(TITLE).pdf
$(OUTPUT)/$(TITLE).pdf: $(META) $(MANIFEST) $(SOURCES)
	@mkdir -p $(OUTPUT)
	pandoc $(META) $(SOURCES) \
	  --toc --toc-depth=2 --pdf-engine=xelatex \
	  --resource-path=$(RESOURCES) \
	  -V geometry:margin=1in -V colorlinks=true \
	  -V mainfont="DejaVu Sans" -V monofont="DejaVu Sans Mono" \
	  -o $@

azw3: $(OUTPUT)/$(TITLE).azw3
$(OUTPUT)/$(TITLE).azw3: $(OUTPUT)/$(TITLE).epub
	ebook-convert $< $@ --output-profile kindle_pw

clean:
	rm -rf $(OUTPUT)
```

Typical run:

```bash
make notebooks   # once after each fresh clone/pull
make all         # epub + pdf + azw3
```

---

## Refreshing the collection

```bash
# Update cloned repos
for d in repos/*/; do git -C "$d" pull --ff-only; done

# Re-fetch the docs that aren't in a repo
python3 anthropic_resources.py --no-api-ref

# Rebuild
make notebooks && make all
```

Consider a monthly cron/`systemd` timer if you want the ebooks to stay current — Anthropic
ships docs frequently.

---

## Known gotchas

- **Image paths across repos.** Each repo references its own relative image paths. The
  `--resource-path=.:repos:docs` flag lets Pandoc search multiple roots, but deeply nested
  notebook images can still miss. If a build warns about a missing image, either add its
  parent dir to `--resource-path` or drop that file from the manifest.
- **Long code lines in PDF.** xelatex won't wrap long unbroken code lines and they'll run off
  the page. Add `-V geometry:landscape` for code-heavy volumes, or post-process with a
  listings template that enables `breaklines`.
- **Size.** The full collection (minus API ref) is large. If a single ebook feels unwieldy,
  split the manifest into volumes (e.g. *Foundations*, *Agents & Tools*, *Claude Code*) and
  build each separately — just point the Makefile at different manifest files.
- **EPUB chapter splitting.** `--split-level=1` is Pandoc 3.x syntax; on Pandoc 2.x use
  `--epub-chapter-level=1`.

---

## Scope & usage

This is a **personal, offline study compilation** of publicly available, official Anthropic
material. Each source remains under its original license/copyright (© Anthropic and the
respective repo licenses). Keep it for your own use; don't redistribute the compiled ebooks.
When in doubt, the canonical, always-current versions live at
`docs.claude.com` / `code.claude.com` and `github.com/anthropics`.
