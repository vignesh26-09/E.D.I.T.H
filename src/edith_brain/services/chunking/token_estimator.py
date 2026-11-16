"""Lightweight, deterministic token estimation."""

from typing import Protocol


class TokenEstimator(Protocol):
    """Protocol for estimating token count of text."""

    def estimate(self, text: str) -> int:
        """Estimate the number of tokens in text."""
        ...


class HeuristicTokenEstimator:
    """Fast, deterministic heuristic token estimator.

    Uses average word-boundary and character-length ratios for English/code text (~4 chars/token).
    Zero external dependencies and sub-microsecond execution time.
    """

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        stripped = text.strip()
        if not stripped:
            return 0

        # Heuristic: 1 token ~= 4 characters, or words / 0.75
        char_estimate = len(stripped) / 4.0
        word_estimate = len(stripped.split()) / 0.75

        # Balanced average
        estimated = int(round((char_estimate + word_estimate) / 2.0))
        return max(1, estimated)
