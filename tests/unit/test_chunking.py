"""Unit tests for chunking algorithms: FixedSize, SlidingWindow, and StructureAware."""

from edith_brain.services.parsers.base import ExtractedElement, ExtractionResult
from edith_brain.services.chunking.token_estimator import HeuristicTokenEstimator
from edith_brain.services.chunking.chunkers import (
    FixedSizeChunker,
    SlidingWindowChunker,
    StructureAwareChunker,
)


def test_heuristic_token_estimator():
    """Estimates tokens deterministically and reasonably."""
    estimator = HeuristicTokenEstimator()
    assert estimator.estimate("") == 0
    assert estimator.estimate("   ") == 0
    # Single short word
    assert estimator.estimate("apple") >= 1
    # Multi-word sentence
    text = "The quick brown fox jumps over the lazy dog."
    tokens = estimator.estimate(text)
    assert 8 <= tokens <= 14


def test_fixed_size_chunker_with_overlap():
    """Fixed-size chunker chunks text with specified overlap."""
    words = [f"word{i}" for i in range(100)]
    full_text = " ".join(words)

    chunker = FixedSizeChunker(chunk_size=30, chunk_overlap=10)
    res = ExtractionResult(text=full_text, extraction_method="test")
    chunks = chunker.chunk(res)

    assert len(chunks) >= 3
    # Check index monotonicity
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert len(c.chunk_text) > 0

    # Check overlap presence
    chunk_0_words = chunks[0].chunk_text.split()
    chunk_1_words = chunks[1].chunk_text.split()
    overlap = set(chunk_0_words).intersection(set(chunk_1_words))
    assert len(overlap) >= 5


def test_sliding_window_chunker():
    """Sliding-window chunker advances step-by-step."""
    words = [f"item{i}" for i in range(50)]
    text = " ".join(words)
    chunker = SlidingWindowChunker(chunk_size=20, chunk_overlap=5)
    chunks = chunker.chunk(ExtractionResult(text=text, extraction_method="test"))

    assert len(chunks) >= 3
    assert chunks[0].chunk_index == 0
    assert "item0" in chunks[0].chunk_text
    assert "item49" in chunks[-1].chunk_text


def test_structure_aware_chunker():
    """StructureAwareChunker groups elements respecting headings and page bounds."""
    elements = [
        ExtractedElement(
            text="Chapter 1: Foundations",
            page_number=1,
            section="Chapter 1",
            element_type="heading",
        ),
        ExtractedElement(
            text="This is the first paragraph of foundations.",
            page_number=1,
            section="Chapter 1",
            element_type="paragraph",
        ),
        ExtractedElement(
            text="Chapter 2: Concurrency",
            page_number=2,
            section="Chapter 2",
            element_type="heading",
        ),
        ExtractedElement(
            text="This is paragraph about SQLite WAL and transactions.",
            page_number=2,
            section="Chapter 2",
            element_type="paragraph",
        ),
    ]

    extraction = ExtractionResult(
        text="Chapter 1: Foundations\n\nThis is the first paragraph...",
        elements=elements,
        extraction_method="test_parser",
    )

    # Set chunk size small enough so that chapters separate into different chunks
    chunker = StructureAwareChunker(chunk_size=15, chunk_overlap=0)
    chunks = chunker.chunk(extraction)

    assert len(chunks) >= 2
    # First chunk should have page 1 provenance
    assert chunks[0].page_number == 1
    assert chunks[0].section == "Chapter 1"
    # Second or later chunk should have page 2 provenance
    assert any(c.page_number == 2 for c in chunks)
    assert any(c.section == "Chapter 2" for c in chunks)


def test_chunking_determinism():
    """Chunking the same extraction result twice produces identical outputs."""
    elements = [
        ExtractedElement(text=f"Paragraph {i} with some content here.", page_number=i // 2 + 1)
        for i in range(15)
    ]
    ext = ExtractionResult(text="Combined text", elements=elements, extraction_method="test")

    chunker = StructureAwareChunker(chunk_size=25, chunk_overlap=5)
    run1 = chunker.chunk(ext)
    run2 = chunker.chunk(ext)

    assert len(run1) == len(run2)
    for c1, c2 in zip(run1, run2):
        assert c1.chunk_index == c2.chunk_index
        assert c1.chunk_text == c2.chunk_text
        assert c1.token_count == c2.token_count
        assert c1.page_number == c2.page_number
        assert c1.source_location == c2.source_location
