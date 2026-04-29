from pathlib import Path

from app.services.file_parser import LocalFileParser


def test_parse_directory_collects_supported_files(tmp_path: Path) -> None:
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "a.txt").write_text("Employee Uday", encoding="utf-8")
    (folder / "b.json").write_text('{"salary":"1543200"}', encoding="utf-8")
    (folder / "ignore.bin").write_bytes(b"\x00\x01")

    parsed = LocalFileParser().parse_directory(str(folder), recursive=True, max_files=10)

    assert len(parsed) == 2
    assert {item.extension for item in parsed} == {".txt", ".json"}
