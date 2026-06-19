# Makefile — build the Anthropic & Claude Complete Guide (EPUB + AZW3).
#
# Pipeline:  fetch + notebooks  ->  assemble (build/book.md)  ->  epub  ->  azw3
#
# Requires: pandoc (EPUB), calibre/ebook-convert (AZW3), uvx (nbconvert),
#           python3. PDF is intentionally not built (no TeX dependency).

TITLE     := anthropic-claude-complete-guide
OUTPUT    := output
BUILD     := build
META      := metadata.yaml
MANIFEST  := manifest.txt
BOOK      := $(BUILD)/book.md
COVER     := assets/cover.png
COLLECTION := anthropic-collection

# Pandoc 2.x: chapter split is --epub-chapter-level (3.x renamed it --split-level).
PANDOC_VER_MAJOR := $(shell pandoc --version | head -1 | sed -E 's/[^0-9]*([0-9]+).*/\1/')
SPLIT_FLAG := $(if $(filter 2,$(PANDOC_VER_MAJOR)),--epub-chapter-level=1,--split-level=1)

# Curated notebook directories (mirrors the manifest's notebook selection).
NB_DIRS := \
  $(COLLECTION)/courses/anthropic_api_fundamentals \
  $(COLLECTION)/courses/real_world_prompting \
  $(COLLECTION)/courses/prompt_evaluations \
  $(COLLECTION)/courses/tool_use \
  "$(COLLECTION)/prompt-eng-interactive-tutorial/Anthropic 1P" \
  $(COLLECTION)/claude-cookbooks/capabilities \
  $(COLLECTION)/claude-cookbooks/extended_thinking \
  $(COLLECTION)/claude-cookbooks/multimodal \
  $(COLLECTION)/claude-cookbooks/patterns \
  $(COLLECTION)/claude-cookbooks/claude_agent_sdk \
  $(COLLECTION)/claude-cookbooks/managed_agents \
  $(COLLECTION)/claude-cookbooks/coding \
  $(COLLECTION)/claude-cookbooks/finetuning \
  $(COLLECTION)/claude-cookbooks/observability

.PHONY: all fetch notebooks assemble epub azw3 test clean distclean

all: epub azw3

# 1. Fetch web-only docs (platform, Claude Code, engineering essays) into docs/.
fetch:
	python3 fetch_docs.py

# 2. Convert the curated notebooks to Markdown in place (.md beside each .ipynb).
notebooks:
	find $(NB_DIRS) -name '*.ipynb' -not -path '*/.ipynb_checkpoints/*' -print0 \
	  | xargs -0 uvx --from nbconvert jupyter-nbconvert --to markdown

# 3. Assemble the single normalized book.md from the manifest.
assemble $(BOOK): $(MANIFEST) build_book.py
	python3 build_book.py --manifest $(MANIFEST) --root . --out $(BOOK)

# 4. Render EPUB.
# Read as gfm (the linear cmark parser): pandoc 2.x's default `markdown` reader
# hits exponential backtracking on large concatenated docs (54 GB RSS / no finish);
# gfm builds the same content in seconds. metadata.yaml is passed via --metadata-file
# so it isn't parsed as gfm.
epub: $(OUTPUT)/$(TITLE).epub
$(OUTPUT)/$(TITLE).epub: $(META) $(BOOK)
	@mkdir -p $(OUTPUT)
	pandoc $(BOOK) -f gfm \
	  --metadata-file=$(META) \
	  --toc --toc-depth=2 $(SPLIT_FLAG) \
	  --resource-path=.:$(COLLECTION) \
	  $(if $(wildcard $(COVER)),--epub-cover-image=$(COVER),) \
	  -o $@

# 5. Derive AZW3 (Kindle) from the finished EPUB via Calibre.
azw3: $(OUTPUT)/$(TITLE).azw3
$(OUTPUT)/$(TITLE).azw3: $(OUTPUT)/$(TITLE).epub
	ebook-convert $< $@ --output-profile kindle_pw

test:
	python3 -m unittest test_anthropic_resources test_build_book test_fetch_docs

# Remove build artifacts and outputs (keeps fetched docs/ and converted .md).
clean:
	rm -rf $(BUILD) $(OUTPUT)

# Also remove fetched docs (forces a re-fetch on next build).
distclean: clean
	rm -rf docs
