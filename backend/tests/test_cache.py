"""Cache keys and the rule that originals are not deleted."""

from pathlib import Path

from app.services.cache_store import cache_is_complete, cache_key, config_payload, restore_derived, store_file


def test_key_changes_when_inputs_or_config_change() -> None:
    base = cache_key("a" * 64, "b" * 64, config_payload())
    assert base == cache_key("a" * 64, "b" * 64, config_payload())
    assert base != cache_key("c" * 64, "b" * 64, config_payload())
    assert base != cache_key("a" * 64, "d" * 64, config_payload())
    changed = dict(config_payload())
    changed["max_layout_nodes"] = 1
    assert base != cache_key("a" * 64, "b" * 64, changed)


def test_restore_copies_derived_files_and_leaves_the_original(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    job = tmp_path / "job"
    job.mkdir()
    original = job / "original.pdf"
    original.write_bytes(b"%PDF-original")
    workbook = job / "io_list.xlsx"
    workbook.write_bytes(b"workbook")
    source = tmp_path / "graph.json"
    source.write_text('{"nodes":[]}', encoding="utf-8")
    store_file(str(cache), "abc", "graph.json", source)
    store_file(str(cache), "abc", "original.pdf", original)
    restored = restore_derived(str(cache), "abc", job)
    assert restored == ["graph.json"]
    assert original.read_bytes() == b"%PDF-original"
    assert workbook.read_bytes() == b"workbook"
    assert not cache_is_complete(str(cache), "abc")
