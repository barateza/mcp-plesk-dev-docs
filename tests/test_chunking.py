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
    assert "chunk_hash" in recs[0]
    assert len(recs[0]["chunk_hash"]) == 64  # SHA-256 hex


def test_build_doc_records_with_summary_and_endpoint():
    chunks = ["content"]
    meta = {
        "title": "T",
        "category": "api",
        "breadcrumb": "B",
        "summary": "This is a summary.",
        "endpoint": "GET /test",
    }
    recs = build_doc_records("api.html", chunks, meta)
    assert len(recs) == 1
    assert recs[0]["summary"] == "This is a summary."
    assert recs[0]["endpoint"] == "GET /test"
    assert "Summary: This is a summary." in recs[0]["text"]
    assert "Endpoint: GET /test" in recs[0]["text"]


def test_chunk_hash_changes_with_version(monkeypatch):
    import plesk_unified.chunking as chunking

    chunks = ["content"]
    meta = {"title": "T", "category": "cat", "breadcrumb": "B"}

    monkeypatch.setattr(chunking, "CHUNK_VERSION", "v1")
    recs_v1 = build_doc_records("f.html", chunks, meta)

    monkeypatch.setattr(chunking, "CHUNK_VERSION", "v2")
    recs_v2 = build_doc_records("f.html", chunks, meta)

    assert recs_v1[0]["chunk_hash"] != recs_v2[0]["chunk_hash"]


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
