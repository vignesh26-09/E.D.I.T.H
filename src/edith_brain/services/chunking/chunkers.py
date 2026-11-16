"""Chunking algorithms: Fixed-size, Sliding-window, and Structure-aware."""

from abc import ABC, abstractmethod
from typing import Optional, Any
from pydantic import BaseModel, Field

from edith_brain.core.contracts import ChunkingStrategy
from edith_brain.services.parsers.base import ExtractedElement, ExtractionResult
from edith_brain.services.chunking.token_estimator import TokenEstimator, HeuristicTokenEstimator


class Chunk(BaseModel):
    """An atomic text chunk prepared for indexing and retrieval."""
    chunk_index: int
    chunk_text: str
    token_count: int
    page_number: Optional[int] = None
    section: Optional[str] = None
    source_location: Optional[str] = None
    extraction_method: str = "chunker_v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseChunker(ABC):
    """Abstract base class for chunking engines."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive.")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative.")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size.")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.token_estimator = token_estimator or HeuristicTokenEstimator()

    @abstractmethod
    def chunk(self, extraction_result: ExtractionResult) -> list[Chunk]:
        """Produce chunks from extraction output."""
        pass


class FixedSizeChunker(BaseChunker):
    """Splits full document text into fixed-size word/token chunks with deterministic overlap."""

    def chunk(self, extraction_result: ExtractionResult) -> list[Chunk]:
        text = extraction_result.text.strip()
        if not text:
            return []

        words = text.split()
        if not words:
            return []

        chunks: list[Chunk] = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        chunk_index = 0

        for i in range(0, len(words), step):
            window_words = words[i : i + self.chunk_size]
            chunk_text = " ".join(window_words)
            token_count = self.token_estimator.estimate(chunk_text)

            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    token_count=token_count,
                    page_number=None,
                    section=None,
                    source_location=f"words {i}-{i + len(window_words) - 1}",
                    extraction_method=f"{extraction_result.extraction_method}+fixed_chunker",
                    metadata={"strategy": "fixed_size"},
                )
            )
            chunk_index += 1

            if i + self.chunk_size >= len(words):
                break

        return chunks


class SlidingWindowChunker(BaseChunker):
    """Sliding-window chunker with fine-grained step progression."""

    def chunk(self, extraction_result: ExtractionResult) -> list[Chunk]:
        text = extraction_result.text.strip()
        if not text:
            return []

        words = text.split()
        if not words:
            return []

        chunks: list[Chunk] = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        chunk_index = 0

        for start_idx in range(0, len(words), step):
            end_idx = min(start_idx + self.chunk_size, len(words))
            window_words = words[start_idx:end_idx]
            chunk_text = " ".join(window_words)
            token_count = self.token_estimator.estimate(chunk_text)

            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    token_count=token_count,
                    page_number=None,
                    section=None,
                    source_location=f"word_offset {start_idx}-{end_idx}",
                    extraction_method=f"{extraction_result.extraction_method}+sliding_window",
                    metadata={"strategy": "sliding_window"},
                )
            )
            chunk_index += 1

            if end_idx >= len(words):
                break

        return chunks


class StructureAwareChunker(BaseChunker):
    """Chunks documents respecting natural structural elements (headings, paragraphs, pages)."""

    def chunk(self, extraction_result: ExtractionResult) -> list[Chunk]:
        elements = extraction_result.elements
        # If parser did not produce structured elements, fall back to fixed chunker
        if not elements:
            fixed = FixedSizeChunker(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                token_estimator=self.token_estimator,
            )
            return fixed.chunk(extraction_result)

        chunks: list[Chunk] = []
        current_texts: list[str] = []
        current_tokens = 0
        current_page: Optional[int] = None
        current_section: Optional[str] = None
        current_locations: list[str] = []
        chunk_index = 0

        def emit_current_chunk():
            nonlocal chunk_index, current_texts, current_tokens, current_page, current_section, current_locations
            if not current_texts:
                return

            chunk_body = "\n\n".join(current_texts).strip()
            if not chunk_body:
                current_texts = []
                current_tokens = 0
                current_locations = []
                return

            loc_str = ", ".join(current_locations) if current_locations else None
            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    chunk_text=chunk_body,
                    token_count=self.token_estimator.estimate(chunk_body),
                    page_number=current_page,
                    section=current_section,
                    source_location=loc_str,
                    extraction_method=f"{extraction_result.extraction_method}+structure_aware",
                    metadata={"strategy": "structure_aware"},
                )
            )
            chunk_index += 1

            # Prepare for next chunk: implement overlap if applicable
            if self.chunk_overlap > 0 and len(current_texts) > 1:
                # Keep last element as overlap context
                last_elem = current_texts[-1]
                current_texts = [last_elem]
                current_tokens = self.token_estimator.estimate(last_elem)
                current_locations = [current_locations[-1]] if current_locations else []
            else:
                current_texts = []
                current_tokens = 0
                current_locations = []

        for elem in elements:
            elem_text = elem.text.strip()
            if not elem_text:
                continue

            elem_tokens = self.token_estimator.estimate(elem_text)

            # Check if this element by itself exceeds chunk_size
            if elem_tokens > self.chunk_size:
                # Flush existing buffer first
                emit_current_chunk()

                # Sub-split oversized element
                words = elem_text.split()
                sub_step = max(1, self.chunk_size - self.chunk_overlap)
                for w_i in range(0, len(words), sub_step):
                    sub_words = words[w_i : w_i + self.chunk_size]
                    sub_text = " ".join(sub_words)
                    chunks.append(
                        Chunk(
                            chunk_index=chunk_index,
                            chunk_text=sub_text,
                            token_count=self.token_estimator.estimate(sub_text),
                            page_number=elem.page_number,
                            section=elem.section,
                            source_location=f"{elem.source_location or 'element'} (part {w_i // sub_step + 1})",
                            extraction_method=f"{extraction_result.extraction_method}+structure_aware_split",
                            metadata={"strategy": "structure_aware", "split_oversized": True},
                        )
                    )
                    chunk_index += 1
                    if w_i + self.chunk_size >= len(words):
                        break
                continue

            # If adding this element exceeds chunk size, emit current chunk
            if current_tokens + elem_tokens > self.chunk_size and current_texts:
                emit_current_chunk()

            # Track section and page
            if current_page is None or (elem.page_number and elem.page_number != current_page):
                current_page = elem.page_number
            if elem.section:
                current_section = elem.section

            current_texts.append(elem_text)
            current_tokens += elem_tokens
            if elem.source_location:
                current_locations.append(elem.source_location)

        # Emit remaining buffered elements
        if current_texts:
            emit_current_chunk()

        return chunks


def get_chunker(
    strategy: ChunkingStrategy,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    token_estimator: TokenEstimator | None = None,
) -> BaseChunker:
    """Factory function for instantiating chunker by strategy enum."""
    if strategy == ChunkingStrategy.FIXED_SIZE:
        return FixedSizeChunker(chunk_size, chunk_overlap, token_estimator)
    elif strategy == ChunkingStrategy.SLIDING_WINDOW:
        return SlidingWindowChunker(chunk_size, chunk_overlap, token_estimator)
    elif strategy == ChunkingStrategy.STRUCTURE_AWARE:
        return StructureAwareChunker(chunk_size, chunk_overlap, token_estimator)
    else:
        return StructureAwareChunker(chunk_size, chunk_overlap, token_estimator)
