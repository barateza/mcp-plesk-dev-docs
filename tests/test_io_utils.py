import json
from unittest.mock import patch

from mcp_plesk_dev_docs.infrastructure.sources.acquisition import (
    ensure_source_exists,
)
from mcp_plesk_dev_docs.infrastructure.sources.discovery import (
    collect_files_for_source,
    compute_source_fingerprint,
    load_toc_map,
    parse_toc_recursive,
)


def test_ensure_source_exists_already_there(tmp_path):
    # Setup mock dir with a file
    (tmp_path / "test.txt").write_text("hello")
    source = {"path": tmp_path, "cat": "test"}
    assert ensure_source_exists(source)


@patch("subprocess.run")
def test_ensure_source_exists_clones(mock_run, tmp_path):
    mock_run.return_value.returncode = 0
    source = {
        "path": tmp_path / "new_repo",
        "repo_url": "https://example.com/repo.git",
        "cat": "test",
    }
    assert ensure_source_exists(source)
    # _get_git_path() resolves to the absolute git path; don't assert exact arg[0]
    call_args, call_kwargs = mock_run.call_args
    assert call_args[0][1:] == [
        "clone",
        "--",
        "https://example.com/repo.git",
        str(tmp_path / "new_repo"),
    ]
    assert call_kwargs == {
        "capture_output": True,
        "text": True,
        "check": False,
    }


@patch("subprocess.run")
def test_ensure_source_exists_clone_fails(mock_run, tmp_path):
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Failed"
    source = {
        "path": tmp_path / "new_repo",
        "repo_url": "https://example.com/repo.git",
        "cat": "test",
    }
    assert not ensure_source_exists(source)


def test_parse_toc_recursive():
    nodes = [
        {"text": "A", "url": "a.htm"},
        {
            "text": "B",
            "url": "b.htm#anchor",
            "children": [{"text": "C", "url": "c.htm"}],
        },
    ]
    res = parse_toc_recursive(nodes)
    assert res["a.htm"]["title"] == "A"
    assert res["a.htm"]["breadcrumb"] == "A"

    assert res["b.htm"]["title"] == "B"
    assert res["b.htm"]["breadcrumb"] == "B"

    assert res["c.htm"]["title"] == "C"
    assert res["c.htm"]["breadcrumb"] == "B > C"


def test_load_toc_map(tmp_path):
    nodes = [
        {"text": "A", "url": "a.htm"},
    ]
    (tmp_path / "toc.json").write_text(json.dumps(nodes))
    res = load_toc_map(tmp_path)
    assert "a.htm" in res


def test_load_toc_map_not_found(tmp_path):
    assert load_toc_map(tmp_path) == {}


def test_collect_files_for_source(tmp_path):
    (tmp_path / "test.htm").touch()
    (tmp_path / "test.php").touch()

    source = {"path": tmp_path, "type": "html"}
    files = collect_files_for_source(source)
    assert len(files) == 1
    assert files[0].name == "test.htm"

    source = {"path": tmp_path, "type": "php"}
    files = collect_files_for_source(source)
    assert len(files) == 1
    assert files[0].name == "test.php"


def test_compute_source_fingerprint_changes_when_file_changes(tmp_path):
    src = tmp_path / "a.php"
    src.write_text("<?php\nclass A {}", encoding="utf-8")
    source = {"path": tmp_path, "type": "php", "cat": "php-stubs"}

    fp1, count1 = compute_source_fingerprint(source)
    src.write_text("<?php\nclass A { public function x() {} }", encoding="utf-8")
    fp2, count2 = compute_source_fingerprint(source)

    assert count1 == 1
    assert count2 == 1
    assert fp1 != fp2


def test_compute_source_fingerprint_empty_source(tmp_path):
    source = {"path": tmp_path, "type": "php", "cat": "php-stubs"}
    fp, count = compute_source_fingerprint(source)
    assert count == 0
    assert isinstance(fp, str)
    assert len(fp) == 64
