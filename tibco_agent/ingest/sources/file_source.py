from pathlib import Path

from .base import KnowledgeSource, RawDocument

_TEXT_SUFFIXES = {".md", ".txt", ".html"}
_PDF_SUFFIX = ".pdf"
_SUPPORTED_SUFFIXES = _TEXT_SUFFIXES | {_PDF_SUFFIX}


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


class FileSource(KnowledgeSource):
    """Loads text, markdown, PDF, and HTML files from a directory tree.

    Supported formats: .md  .txt  .html  .pdf
    Pass glob_pattern="**/*" (default) to pick up all supported types.
    """

    def __init__(self, path: str, glob_pattern: str = "**/*", name: str = "") -> None:
        self.path = Path(path)
        self.glob_pattern = glob_pattern
        self.name = name or f"file:{path}"

    def load(self) -> list[RawDocument]:
        docs = []
        for file_path in sorted(self.path.glob(self.glob_pattern)):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in _SUPPORTED_SUFFIXES:
                continue
            try:
                if suffix == _PDF_SUFFIX:
                    content = _read_pdf(file_path)
                else:
                    content = file_path.read_text(encoding="utf-8")
                if content.strip():
                    docs.append(RawDocument(
                        content=content,
                        source=str(file_path),
                        metadata={
                            "source_type": "file",
                            "file_name": file_path.name,
                            "file_type": suffix.lstrip("."),
                            "product": self._infer_product(file_path),
                        },
                    ))
            except Exception as e:
                print(f"  [WARN] Could not read {file_path}: {e}")
        return docs

    def _infer_product(self, path: Path) -> str:
        parts = {p.lower() for p in path.parts}
        name = path.name.lower()
        if "flogo" in parts or "flogo" in name:
            return "flogo"
        if "bw" in parts or "businessworks" in name or "bwce" in name:
            return "bw"
        return "general"
