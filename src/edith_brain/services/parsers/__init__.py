"""Document parser adapters for various file formats."""

from edith_brain.services.parsers.base import BaseDocumentParser, ExtractedElement, ExtractionResult
from edith_brain.services.parsers.text_parser import PlainTextParser
from edith_brain.services.parsers.markdown_parser import MarkdownParser
from edith_brain.services.parsers.pdf_parser import PDFParser
from edith_brain.services.parsers.docx_parser import DocxParser
from edith_brain.services.parsers.registry import ParserRegistry, get_parser_for_file

__all__ = [
    "BaseDocumentParser",
    "ExtractedElement",
    "ExtractionResult",
    "PlainTextParser",
    "MarkdownParser",
    "PDFParser",
    "DocxParser",
    "ParserRegistry",
    "get_parser_for_file",
]
