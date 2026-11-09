"""Unit tests for the search result formatter and its snippet budget."""

from mcp_plesk_dev_docs.formatting.search_formatter import (
    DEFAULT_SNIPPET_CHARS,
    ELLIPSIS,
    SearchFormatter,
    build_doc_url,
    format_snippet,
)


class FakeSource:
    def __init__(self, url):
        self.url = url

    def build_doc_url(self, filename):
        return self.url


class FakeCatalog:
    def __init__(self, sources):
        self.sources = sources

    def by_category(self, category):
        return self.sources.get(category)


def make_result(body: str, **overrides):
    result = {
        "text": body,
        "filename": "77178.htm",
        "category": "guide",
        "title": "Creating a domain",
        "_relevance": 0.9123,
        "chunk_id": 4,
    }
    result.update(overrides)
    return result


def long_body(sentences: int = 60) -> str:
    return " ".join(
        f"Sentence number {i} explains one documented step." for i in range(sentences)
    )


# --- format_snippet -------------------------------------------------------


def test_short_text_is_returned_unchanged():
    text = "Short documentation chunk."
    assert format_snippet(text) == text


def test_snippet_can_cut_on_a_paragraph_boundary():
    text = ("Paragraph. " * 10) + "\n\n" + ("y" * 300)

    snippet = format_snippet(text, max_chars=120)

    # The paragraph break is the closest boundary, so it wins over the last
    # sentence period before it.
    assert "\n\n" not in snippet
    assert snippet[:-1].endswith("Paragraph.")


def test_snippet_is_cut_on_a_sentence_boundary():
    snippet = format_snippet(long_body(), max_chars=200)

    assert len(snippet) <= 200
    assert snippet.endswith(ELLIPSIS)
    # The cut lands after a complete sentence, not in the middle of one.
    assert snippet[:-1].endswith(".")
    assert "Sentence number" in snippet


def test_snippet_falls_back_to_a_word_boundary():
    text = "word " * 200  # no sentence/paragraph punctuation at all

    snippet = format_snippet(text, max_chars=100)

    assert len(snippet) <= 100
    assert snippet.endswith(ELLIPSIS)
    assert not snippet[:-1].endswith("wor")


def test_snippet_falls_back_to_a_hard_cut():
    text = "x" * 500  # a single unbroken token

    snippet = format_snippet(text, max_chars=50)

    assert len(snippet) == 50
    assert snippet.endswith(ELLIPSIS)


def test_snippet_budget_respects_the_max_chars_argument():
    for budget in (20, 101, 400, DEFAULT_SNIPPET_CHARS):
        assert len(format_snippet(long_body(), max_chars=budget)) <= budget


# --- format_markdown ------------------------------------------------------


def test_markdown_keeps_header_metadata_and_documentation_url():
    catalog = FakeCatalog({"guide": FakeSource("https://docs.plesk.com/guide/x.htm")})
    formatter = SearchFormatter(catalog)

    markdown = formatter.format_markdown([make_result(long_body())])

    assert markdown.startswith("### [GUIDE] Creating a domain")
    assert "**File:** `77178.htm`" in markdown
    assert "**Score:** 0.9123" in markdown
    assert "**Documentation:** https://docs.plesk.com/guide/x.htm" in markdown
    assert markdown.endswith("\n\n---\n")


def test_markdown_bounds_the_body_but_keeps_the_card_under_a_thousand_chars():
    formatter = SearchFormatter(FakeCatalog({}))

    markdown = formatter.format_markdown([make_result(long_body())])

    assert len(markdown) < 1000
    assert markdown.count(ELLIPSIS) == 1
    assert long_body() not in markdown


def test_markdown_accepts_a_custom_budget():
    formatter = SearchFormatter(FakeCatalog({}))

    markdown = formatter.format_markdown([make_result(long_body())], max_chars=120)

    body = markdown.split("---", 1)[0]
    assert len(body) < 300
    assert body.count(ELLIPSIS) == 1


def test_markdown_omits_the_documentation_line_without_a_url():
    formatter = SearchFormatter(FakeCatalog({}))

    markdown = formatter.format_markdown([make_result("Body text.")])

    assert "**Documentation:**" not in markdown
    assert "Body text." in markdown


def test_markdown_does_not_truncate_short_results():
    formatter = SearchFormatter(FakeCatalog({}))

    markdown = formatter.format_markdown([make_result("Body text.")])

    assert ELLIPSIS not in markdown


def test_markdown_of_no_results_is_empty():
    formatter = SearchFormatter(FakeCatalog({}))

    assert formatter.format_markdown([]) == ""


# --- build_doc_url --------------------------------------------------------


def test_build_doc_url_uses_the_catalog():
    catalog = FakeCatalog({"cli": FakeSource("https://docs.plesk.com/cli/x.htm")})

    assert build_doc_url(catalog, "cli", "x.htm") == "https://docs.plesk.com/cli/x.htm"


def test_build_doc_url_returns_none_for_missing_or_odd_inputs():
    catalog = FakeCatalog({})

    assert build_doc_url(None, "cli", "x.htm") is None
    assert build_doc_url(catalog, "cli", "x.htm") is None
    assert build_doc_url(catalog, "", "x.htm") is None
    assert build_doc_url(catalog, "cli", "") is None


def test_build_doc_url_ignores_non_string_urls():
    catalog = FakeCatalog({"php-stubs": FakeSource(None)})

    assert build_doc_url(catalog, "php-stubs", "Config.php") is None
