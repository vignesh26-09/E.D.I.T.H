"""Base interfaces and data contracts for document extraction."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field


class ExtractedElement(BaseModel):
    """An individual structural element extracted from a document (e.g. paragraph, heading, page)."""
    text: str = Field(..., min_length=1)
    page_number: Optional[int] = Field(default=None, ge=1)
    section: Optional[str] = None
    source_location: Optional[str] = None
    element_type: str = Field(default="paragraph")  # paragraph, heading, list_item, code_block, table


class ExtractionResult(BaseModel):
    """Normalized output from any document parser adapter."""
    text: str
    elements: list[ExtractedElement] = Field(default_factory=list)
    extraction_method: str
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseDocumentParser(ABC):
    """Abstract base class for format-specific document parsers."""

    @abstractmethod
    def extract(self, file_path: Path, raw_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text and structural elements from the given file or bytes."""
        pass
