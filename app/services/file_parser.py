from __future__ import annotations

import io
import json
import mimetypes
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET

from app.models import FileArtifact


MAX_EXTRACTED_CHARS = 50000
CHUNK_SIZE = 8000
CHUNK_OVERLAP = 400
DEFAULT_MAX_FILES = 25


@dataclass
class ParsedFile:
    path: str
    media_type: str
    extension: str
    extracted_text: str
    parser: str
    warnings: list[str] = field(default_factory=list)

    @property
    def artifact(self) -> FileArtifact:
        return FileArtifact(
            path=self.path,
            parser=self.parser,
            extension=self.extension,
            media_type=self.media_type,
            chars_extracted=len(self.extracted_text),
            chunks=len(chunk_text(self.extracted_text)),
            warnings=self.warnings,
        )


class UnsupportedFileTypeError(ValueError):
    pass


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunks.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = end - overlap
    return chunks


class LocalFileParser:
    def __init__(self, max_directory_files: int = DEFAULT_MAX_FILES) -> None:
        self.max_directory_files = max_directory_files
        self._binary_parsers: dict[str, Callable[[Path], ParsedFile]] = {
            ".pdf": self._parse_pdf,
            ".docx": self._parse_docx,
            ".pptx": self._parse_pptx,
            ".xlsx": self._parse_xlsx,
            ".csv": self._parse_csv,
            ".tsv": self._parse_tsv,
            ".json": self._parse_json,
            ".xml": self._parse_xml,
            ".png": self._parse_image,
            ".jpg": self._parse_image,
            ".jpeg": self._parse_image,
            ".tif": self._parse_image,
            ".tiff": self._parse_image,
            ".bmp": self._parse_image,
            ".mp3": self._parse_media,
            ".wav": self._parse_media,
            ".m4a": self._parse_media,
            ".mp4": self._parse_media,
            ".mov": self._parse_media,
            ".mkv": self._parse_media,
        }
        self._text_extensions = {
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".html",
            ".css",
            ".scss",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".sh",
            ".yaml",
            ".yml",
            ".ini",
            ".toml",
            ".log",
            ".sql",
        }

    def parse_path(self, raw_path: str) -> ParsedFile:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        return self._parse(path)

    def discover_directory_files(
        self, raw_path: str, recursive: bool = True, max_files: int = DEFAULT_MAX_FILES
    ) -> list[Path]:
        root = Path(raw_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {root}")
        effective_max = min(max_files, self.max_directory_files)
        pattern = "**/*" if recursive else "*"
        supported: list[Path] = []
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            if self._is_supported_extension(path.suffix.lower()):
                supported.append(path)
            if len(supported) >= effective_max:
                break
        if not supported:
            raise UnsupportedFileTypeError("No supported files were found in the selected directory.")
        return supported

    def parse_directory(self, raw_path: str, recursive: bool = True, max_files: int = DEFAULT_MAX_FILES) -> list[ParsedFile]:
        files: list[ParsedFile] = []
        for path in self.discover_directory_files(raw_path, recursive=recursive, max_files=max_files):
            files.append(self._parse(path))
        return files

    async def parse_upload(self, filename: str, content: bytes) -> ParsedFile:
        suffix = Path(filename).suffix.lower()
        if suffix in self._text_extensions:
            text = content.decode("utf-8", errors="replace")
            return self._build_parsed_file(filename, suffix, text, "text")
        if suffix == ".pdf":
            return self._parse_pdf_bytes(filename, content)
        if suffix in {".docx", ".pptx", ".xlsx"}:
            return self._parse_office_bytes(filename, content, suffix)
        if suffix == ".csv":
            return self._build_parsed_file(filename, suffix, content.decode("utf-8", errors="replace"), "csv")
        if suffix == ".tsv":
            return self._build_parsed_file(filename, suffix, content.decode("utf-8", errors="replace"), "tsv")
        if suffix == ".json":
            return self._build_parsed_file(filename, suffix, self._normalize_json(content.decode("utf-8", errors="replace")), "json")
        if suffix == ".xml":
            return self._build_parsed_file(filename, suffix, self._normalize_xml(content.decode("utf-8", errors="replace")), "xml")
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return self._parse_image_bytes(filename, content)
        if suffix in {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".mkv"}:
            return self._parse_media_bytes(filename, content)
        raise UnsupportedFileTypeError(
            "Unsupported file type for automatic local parsing. Supported types include text, code, PDF, DOCX, PPTX, XLSX, CSV, TSV, JSON, XML, images, and audio/video."
        )

    def _parse(self, path: Path) -> ParsedFile:
        suffix = path.suffix.lower()
        if suffix in self._text_extensions:
            return self._build_parsed_file(str(path), suffix, path.read_text(encoding="utf-8", errors="replace"), "text")
        parser = self._binary_parsers.get(suffix)
        if parser:
            return parser(path)
        raise UnsupportedFileTypeError(
            "Unsupported file type for automatic local parsing. Supported types include text, code, PDF, DOCX, PPTX, XLSX, CSV, TSV, JSON, XML, images, and audio/video."
        )

    def _is_supported_extension(self, suffix: str) -> bool:
        return suffix in self._text_extensions or suffix in self._binary_parsers

    def _parse_pdf(self, path: Path) -> ParsedFile:
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise UnsupportedFileTypeError("PDF parsing requires pypdf to be installed locally.") from exc
        reader = PdfReader(str(path))
        parts = [page.extract_text() or "" for page in reader.pages]
        return self._build_parsed_file(str(path), ".pdf", "\n\n".join(parts), "pypdf")

    def _parse_pdf_bytes(self, filename: str, content: bytes) -> ParsedFile:
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise UnsupportedFileTypeError("PDF parsing requires pypdf to be installed locally.") from exc
        reader = PdfReader(io.BytesIO(content))
        parts = [page.extract_text() or "" for page in reader.pages]
        return self._build_parsed_file(filename, ".pdf", "\n\n".join(parts), "pypdf")

    def _parse_docx(self, path: Path) -> ParsedFile:
        with zipfile.ZipFile(path) as archive:
            text = self._extract_docx_text(archive)
        return self._build_parsed_file(str(path), ".docx", text, "docx-xml")

    def _parse_pptx(self, path: Path) -> ParsedFile:
        with zipfile.ZipFile(path) as archive:
            text = self._extract_pptx_text(archive)
        return self._build_parsed_file(str(path), ".pptx", text, "pptx-xml")

    def _parse_xlsx(self, path: Path) -> ParsedFile:
        with zipfile.ZipFile(path) as archive:
            text = self._extract_xlsx_text(archive)
        return self._build_parsed_file(str(path), ".xlsx", text, "xlsx-xml")

    def _parse_office_bytes(self, filename: str, content: bytes, suffix: str) -> ParsedFile:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if suffix == ".docx":
                text = self._extract_docx_text(archive)
                parser = "docx-xml"
            elif suffix == ".pptx":
                text = self._extract_pptx_text(archive)
                parser = "pptx-xml"
            else:
                text = self._extract_xlsx_text(archive)
                parser = "xlsx-xml"
        return self._build_parsed_file(filename, suffix, text, parser)

    def _parse_csv(self, path: Path) -> ParsedFile:
        return self._build_parsed_file(str(path), ".csv", path.read_text(encoding="utf-8", errors="replace"), "csv")

    def _parse_tsv(self, path: Path) -> ParsedFile:
        return self._build_parsed_file(str(path), ".tsv", path.read_text(encoding="utf-8", errors="replace"), "tsv")

    def _parse_json(self, path: Path) -> ParsedFile:
        return self._build_parsed_file(str(path), ".json", self._normalize_json(path.read_text(encoding="utf-8", errors="replace")), "json")

    def _parse_xml(self, path: Path) -> ParsedFile:
        return self._build_parsed_file(str(path), ".xml", self._normalize_xml(path.read_text(encoding="utf-8", errors="replace")), "xml")

    def _parse_image(self, path: Path) -> ParsedFile:
        try:
            from PIL import Image
            import pytesseract
        except Exception as exc:
            raise UnsupportedFileTypeError("Image OCR requires Pillow and pytesseract locally.") from exc
        image = Image.open(path)
        text = pytesseract.image_to_string(image)
        warnings = []
        if not text.strip():
            warnings.append("OCR returned little or no text.")
        return self._build_parsed_file(str(path), path.suffix.lower(), text, "tesseract-ocr", warnings=warnings)

    def _parse_image_bytes(self, filename: str, content: bytes) -> ParsedFile:
        try:
            from PIL import Image
            import pytesseract
        except Exception as exc:
            raise UnsupportedFileTypeError("Image OCR requires Pillow and pytesseract locally.") from exc
        image = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(image)
        warnings = []
        if not text.strip():
            warnings.append("OCR returned little or no text.")
        return self._build_parsed_file(filename, Path(filename).suffix.lower(), text, "tesseract-ocr", warnings=warnings)

    def _parse_media(self, path: Path) -> ParsedFile:
        text = self._transcribe_media_file(path)
        warnings = []
        if not text.strip():
            warnings.append("Transcription returned little or no text.")
        return self._build_parsed_file(str(path), path.suffix.lower(), text, "whisper-local", warnings=warnings)

    def _parse_media_bytes(self, filename: str, content: bytes) -> ParsedFile:
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            text = self._transcribe_media_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
        warnings = []
        if not text.strip():
            warnings.append("Transcription returned little or no text.")
        return self._build_parsed_file(filename, suffix, text, "whisper-local", warnings=warnings)

    def _transcribe_media_file(self, path: Path) -> str:
        try:
            import whisper
        except Exception as exc:
            raise UnsupportedFileTypeError("Audio and video transcription requires the local whisper package.") from exc
        model = whisper.load_model("base")
        result = model.transcribe(str(path), fp16=False, verbose=False)
        return str(result.get("text", "")).strip()

    def _build_parsed_file(
        self,
        path: str,
        extension: str,
        extracted_text: str,
        parser: str,
        warnings: Optional[list[str]] = None,
    ) -> ParsedFile:
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        compact = self._truncate(extracted_text)
        return ParsedFile(
            path=path,
            media_type=media_type,
            extension=extension,
            extracted_text=compact,
            parser=parser,
            warnings=warnings or [],
        )

    def _extract_docx_text(self, archive: zipfile.ZipFile) -> str:
        xml = archive.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            text_nodes = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
            if text_nodes:
                paragraphs.append("".join(text_nodes))
        return "\n".join(paragraphs)

    def _extract_pptx_text(self, archive: zipfile.ZipFile) -> str:
        slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        slides = []
        for name in slide_names:
            root = ET.fromstring(archive.read(name))
            texts = [node.text for node in root.findall(".//a:t", ns) if node.text]
            if texts:
                slides.append(" ".join(texts))
        return "\n\n".join(slides)

    def _extract_xlsx_text(self, archive: zipfile.ZipFile) -> str:
        shared_strings = self._read_shared_strings(archive)
        workbook = []
        worksheet_names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for name in worksheet_names:
            root = ET.fromstring(archive.read(name))
            rows = []
            for row in root.findall(".//a:sheetData/a:row", ns):
                values = []
                for cell in row.findall("a:c", ns):
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("a:v", ns)
                    if value_node is None or value_node.text is None:
                        continue
                    value = value_node.text
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(value)]
                        except Exception:
                            pass
                    values.append(value)
                if values:
                    rows.append(", ".join(values))
            if rows:
                workbook.append("\n".join(rows))
        return "\n\n".join(workbook)

    def _read_shared_strings(self, archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        values = []
        for item in root.findall(".//a:si", ns):
            text = "".join(node.text or "" for node in item.findall(".//a:t", ns))
            values.append(text)
        return values

    def _normalize_json(self, text: str) -> str:
        try:
            parsed = json.loads(text)
        except Exception:
            return text
        return json.dumps(parsed, indent=2, ensure_ascii=False)

    def _normalize_xml(self, text: str) -> str:
        try:
            root = ET.fromstring(text)
        except Exception:
            return text
        return ET.tostring(root, encoding="unicode")

    def _truncate(self, text: str) -> str:
        cleaned = text.replace("\x00", " ").strip()
        if len(cleaned) <= MAX_EXTRACTED_CHARS:
            return cleaned
        head = cleaned[:30000]
        tail = cleaned[-15000:]
        return f"{head}\n\n[... document truncated locally for prompt sizing ...]\n\n{tail}"
