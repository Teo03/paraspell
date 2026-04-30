"""SpellChecker — main engine facade (NFR-12).

SpellChecker is instantiated once at application startup (via the FastAPI
lifespan) and injected into route handlers through ``get_checker()``.

Current state
-------------
* Tokenises the input text.
* Dispatches word chunks to ``worker.process_chunk`` (single-process for now).
* Returns a fully-shaped SpellCheckResponse.

TODO (workers card): swap the sequential loop for a ProcessPoolExecutor
    using WORKER_COUNT and CHUNK_SIZE from the environment.
"""

from __future__ import annotations

import math
import os
import re

from app.engine.dictionary import Dictionary
from app.engine.worker import process_chunk
from app.schemas.spell import Correction, SpellCheckResponse

# Matches sequences of Unicode letters (handles accented chars too).
_WORD_RE = re.compile(r"\b[^\W\d_]+\b", re.UNICODE)

# Singleton instance shared across requests.
_checker_instance: "SpellChecker | None" = None


class SpellChecker:
    """Facade that coordinates dictionary, chunking, and workers."""

    def __init__(self) -> None:
        self._dictionary = Dictionary()
        self._worker_count = self._resolve_int("WORKER_COUNT", os.cpu_count() or 1)
        self._chunk_size = self._resolve_int("CHUNK_SIZE", 0)  # 0 → auto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, text: str) -> SpellCheckResponse:
        """Spell-check *text* and return a structured response."""
        tokens = self._tokenise(text)
        chunks = self._split(tokens)

        corrections: list[Correction] = []
        for chunk in chunks:
            corrections.extend(process_chunk(chunk, self._dictionary))

        return SpellCheckResponse(
            word_count=len(tokens),
            error_count=len(corrections),
            corrections=corrections,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenise(text: str) -> list[tuple[str, int]]:
        """Return ``(word, offset)`` pairs for every word token in *text*."""
        return [(m.group(), m.start()) for m in _WORD_RE.finditer(text)]

    def _split(self, tokens: list[tuple[str, int]]) -> list[list[tuple[str, int]]]:
        """Partition *tokens* into balanced chunks for parallel workers."""
        if not tokens:
            return []
        size = self._chunk_size or math.ceil(len(tokens) / self._worker_count)
        return [tokens[i:i + size] for i in range(0, len(tokens), size)]

    @staticmethod
    def _resolve_int(env_var: str, default: int) -> int:
        val = os.getenv(env_var, "auto")
        try:
            return int(val)
        except ValueError:
            return default


# ------------------------------------------------------------------
# FastAPI dependency
# ------------------------------------------------------------------

def get_checker() -> SpellChecker:
    """FastAPI dependency that returns the singleton SpellChecker."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = SpellChecker()
    return _checker_instance
