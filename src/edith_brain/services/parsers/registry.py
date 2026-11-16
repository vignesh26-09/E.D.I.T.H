"""Registry and factory for document parser resolution."""

from pathlib import Path
from typing import Optional
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.base import BaseDocumentParser
from edith_brain.services.parsers.text_parser import PlainTextParser
from edith_brain.services.parsers.markdown_parser import MarkdownParser
from edith_brain.services.parsers.pdf_parser import PDFParser
from edith_brain.services.parsers.docx_parser import DocxParser


class ParserRegistry:
    """Resolves appropriate parser adapter based on file extension and MIME type."""

    def __init__(self) -> None:
        self._parsers_by_ext: dict[str, BaseDocumentParser] = {}
        self._parsers_by_mime: dict[str, BaseDocumentParser] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        txt_parser = PlainTextParser()
        md_parser = MarkdownParser()
        pdf_parser = PDFParser()
        docx_parser = DocxParser()

        # Extensions
        self._parsers_by_ext[".txt"] = txt_parser
        self._parsers_by_ext[".md"] = md_parser
        self._parsers_by_ext[".markdown"] = md_parser
        self._parsers_by_ext[".pdf"] = pdf_parser
        self._parsers_by_ext[".docx"] = docx_parser

        # MIME types
        self._parsers_by_mime["text/plain"] = txt_parser
        self._parsers_by_mime["text/markdown"] = md_parser
        self._parsers_by_mime["text/x-markdown"] = md_parser
        self._parsers_by_mime["application/pdf"] = pdf_parser
        self._parsers_by_mime["application/vnd.openxmlformats-officedocument.wordprocessingml.document"] = docx_parser

    def get_parser(self, filename: str, mime_type: Optional[str] = None) -> BaseDocumentParser:
        """Resolve parser matching extension or MIME type, or raise ValidationError."""
        ext = Path(filename).suffix.lower()

        if ext in self._parsers_by_ext:
            return self._parsers_by_ext[ext]

        if mime_type:
            cleaned_mime = mime_type.split(";")[0].strip().lower()
            if cleaned_mime in self._parsers_by_mime:
                return self._parsers_by_mime[cleaned_mime]

        supported_extensions = list(self._parsers_by_ext.keys())
        raise ValidationError(
            f"Unsupported document format '{ext or filename}'. "
            f"Supported extensions: {', '.join(supported_extensions)}"
        )


_DEFAULT_REGISTRY = ParserRegistry()


def get_parser_for_file(filename: str, mime_type: Optional[str] = None) -> BaseDocumentParser:
    """Helper function to fetch parser from default registry."""
    return _DEFAULT_REGISTRY.get_parser(filename, mime_type)
