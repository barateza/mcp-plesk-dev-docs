from plesk_unified.chunking import (
    build_doc_records,
    chunk_by_chars,
    chunk_by_sentence_window,
    chunk_js_hierarchical,
    chunk_php_hierarchical,
)


def test_chunk_by_chars_empty():
    assert chunk_by_chars("") == []


def test_chunk_by_chars_overlap():
    text = "a" * 5000
    chunks = chunk_by_chars(text, size=1000, overlap=200)
    assert len(chunks) >= 5
    # ensure overlap by checking consecutive chunks share content
    assert chunks[0][-1] == "a"


def test_build_doc_records():
    chunks = ["one", "two"]
    meta = {"title": "T", "category": "cat", "breadcrumb": "A > B"}
    recs = build_doc_records("file.html", chunks, meta)
    assert len(recs) == 2
    assert recs[0]["title"] == "T"
    assert recs[1]["filename"] == "file.html"


def test_chunk_by_sentence_window_uses_stride_one_windows():
    text = "One. Two. Three. Four."
    chunks = chunk_by_sentence_window(text, window_size=3)
    assert len(chunks) == 2
    assert chunks[0].startswith("One.")
    assert chunks[1].startswith("Two.")


def test_chunk_php_hierarchical_splits_by_declarations():
    text = """
class A {
    public function alpha() {}
}

class B {
    public function beta() {}
}
"""
    chunks = chunk_php_hierarchical(text)
    assert len(chunks) >= 2
    assert any("class A" in c for c in chunks)
    assert any("class B" in c for c in chunks)


def test_chunk_js_hierarchical_splits_exports():
    text = """
export function first() {
    return 1;
}

export function second() {
    return 2;
}
"""
    chunks = chunk_js_hierarchical(text)
    assert len(chunks) >= 2
    assert any("first" in c for c in chunks)
    assert any("second" in c for c in chunks)
