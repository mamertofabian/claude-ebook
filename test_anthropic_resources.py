"""Tests for anthropic_resources.py parsing.

Stdlib-only (unittest) to match the harvester's zero-dependency ethos.
Run: python3 -m unittest test_anthropic_resources -v
"""

import unittest

from anthropic_resources import parse_llms


class ParseLlmsTest(unittest.TestCase):
    def test_dash_separated_entry_yields_title_url_desc(self):
        text = (
            "## Docs\n- [Tool use](https://platform.claude.com/x.md) — How tools work\n"
        )
        rows = list(parse_llms(text, "Platform"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Tool use")
        self.assertEqual(rows[0]["url"], "https://platform.claude.com/x.md")
        self.assertEqual(rows[0]["description"], "How tools work")

    def test_colon_separated_entry_is_parsed(self):
        # The Claude Code llms.txt uses `](url): description`, which the
        # original dash-only LINK_RE rejected, dropping all 149 pages.
        text = (
            "## Docs\n"
            "- [Set up Claude Code](https://code.claude.com/docs/en/admin-setup.md):"
            " A decision map for administrators.\n"
        )
        rows = list(parse_llms(text, "Claude Code"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Set up Claude Code")
        self.assertEqual(
            rows[0]["url"], "https://code.claude.com/docs/en/admin-setup.md"
        )
        self.assertEqual(rows[0]["category"], "Claude Code")
        self.assertEqual(rows[0]["description"], "A decision map for administrators.")

    def test_entry_without_description_still_parses(self):
        text = "## Docs\n- [Overview](https://code.claude.com/docs/en/overview.md)\n"
        rows = list(parse_llms(text, "Claude Code"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "")

    def test_non_http_links_are_skipped(self):
        text = "## Docs\n- [Local](./relative.md): nope\n"
        self.assertEqual(list(parse_llms(text, "X")), [])


if __name__ == "__main__":
    unittest.main()
