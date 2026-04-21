from pathlib import Path

from plesk_unified.html_utils import clean_html_for_markdown, parse_html_file


def test_parse_html_file(tmp_path):
    src = Path("tests/fixtures/sample.html")
    title, breadcrumb, text, endpoint = parse_html_file(src)
    assert "Sample Page" in title
    assert "Heading" in text
    assert "Navigation" not in text
    assert endpoint is None


def test_parse_html_file_extracts_endpoint(tmp_path):
    html = (
        "<!doctype html><html><head><title>T</title></head><body>"
        "<code>GET /api/v2/domains</code>"
        "</body></html>"
    )
    src = tmp_path / "api.html"
    src.write_text(html, encoding="utf-8")
    _, _, _, endpoint = parse_html_file(src)
    assert endpoint == "GET /api/v2/domains"


def test_clean_html_for_markdown():
    src = Path("tests/fixtures/sample.html")
    html = src.read_text(encoding="utf-8")
    cleaned = clean_html_for_markdown(html)
    assert "Navigation" not in cleaned
    assert "Heading" in cleaned


def test_parse_html_file_preserves_code_blocks(tmp_path):
    """Code blocks inside <pre><code> are rendered as Markdown fenced blocks."""
    html = (
        "<!doctype html><html><head><title>T</title></head>"
        "<body><main>"
        "<pre><code>pm_Config::get('timeout');</code></pre>"
        "</main></body></html>"
    )
    src = tmp_path / "code.html"
    src.write_text(html, encoding="utf-8")
    _, _, text, _ = parse_html_file(src)
    assert "```" in text
    assert "pm_Config::get" in text


def test_parse_html_file_converts_table_rows_to_prose(tmp_path):
    html = (
        "<!doctype html><html><head><title>T</title></head><body><main>"
        "<table>"
        "<tr><th>Parameter</th><th>Type</th><th>Default</th></tr>"
        "<tr><td>timeout</td><td>integer</td><td>60</td></tr>"
        "</table>"
        "</main></body></html>"
    )
    src = tmp_path / "table.html"
    src.write_text(html, encoding="utf-8")

    _, _, text, _ = parse_html_file(src)
    assert "Parameter: timeout" in text
    assert "Type: integer" in text
    assert "Default: 60" in text
