"""Markdown document parser adapter preserving heading hierarchy and structural blocks."""

import re
from pathlib import Path
from edith_brain.core.exceptions import ValidationError
from edith_brain.services.parsers.base import BaseDocumentParser, ExtractedElement, ExtractionResult


class MarkdownParser(BaseDocumentParser):
    """Parses Markdown (.md) documents with heading tracking and section breadcrumbs."""

    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")

    def extract(self, file_path: Path, raw_bytes: bytes, filename: str) -> ExtractionResult:
        if not raw_bytes:
            raise ValidationError(f"File '{filename}' is empty.")

        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = raw_bytes.decode("latin-1")
            except Exception as exc:
                raise ValidationError(f"Cannot decode markdown file '{filename}': {exc}") from exc

        elements: list[ExtractedElement] = []
        heading_stack: list[tuple[int, str]] = []  # (level, heading_text)

        lines = content.splitlines()
        current_block: list[str] = []
        in_code_block = False
        block_start_line = 1

        def get_current_section() -> str | None:
            if not heading_stack:
                return None
            return " > ".join(h[1] for h in heading_stack)

        def flush_block(line_num: int):
            nonlocal current_block, block_start_line
            if not current_block:
                return
            block_text = "\n".join(current_block).strip()
            if block_text:
                elements.append(
                    ExtractedElement(
                        text=block_text,
                        page_number=1,
                        section=get_current_section(),
                        source_location=f"lines {block_start_line}-{line_num - 1}",
                        element_type="code_block" if in_code_block else "paragraph",
                    )
                )
            current_block = []

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Handle fenced code block toggle
            if stripped.startswith("```"):
                if in_code_block:
                    current_block.append(line)
                    flush_block(idx + 1)
                    in_code_block = False
                    block_start_line = idx + 1
                    continue
                else:
                    flush_block(idx)
                    in_code_block = True
                    current_block.append(line)
                    block_start_line = idx
                    continue

            if in_code_block:
                current_block.append(line)
                continue

            # Check for Markdown headings
            heading_match = self.HEADING_REGEX.match(stripped)
            if heading_match:
                flush_block(idx)
                level = len(heading_match.group(1))
                heading_title = heading_match.group(2).strip()

                # Maintain heading stack for breadcrumbs
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_title))

                elements.append(
                    ExtractedElement(
                        text=heading_title,
                        page_number=1,
                        section=get_current_section(),
                        source_location=f"line {idx}",
                        element_type="heading",
                    )
                )
                block_start_line = idx + 1
                continue

            # Check for empty lines denoting paragraph boundaries
            if not stripped:
                flush_block(idx)
                block_start_line = idx + 1
                continue

            if not current_block:
                block_start_line = idx
            current_block.append(line)

        # Flush final block
        flush_block(len(lines) + 1)

        return ExtractionResult(
            text=content,
            elements=elements,
            extraction_method="markdown_parser_v1",
            warnings=[],
            metadata={"heading_count": sum(1 for e in elements if e.element_type == "heading")},
        )
