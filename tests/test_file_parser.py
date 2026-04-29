import io
import zipfile

from app.services.file_parser import LocalFileParser


def test_parse_json_upload() -> None:
    parser = LocalFileParser()
    parsed = __import__("asyncio").run(parser.parse_upload("sample.json", b'{"name":"Uday","salary":"1543200"}'))
    assert '"name": "Uday"' in parsed.extracted_text


def test_parse_docx_upload() -> None:
    parser = LocalFileParser()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Private Name Uday</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    parsed = __import__("asyncio").run(parser.parse_upload("sample.docx", stream.getvalue()))
    assert "Private Name Uday" in parsed.extracted_text
