"""SpellChecker — main engine facade (NFR-12).

SpellChecker is instantiated once at application startup (via the FastAPI
lifespan) and injected into route handlers through ``get_checker()``.

Implementation
--------------
* Tokenises the input text.
* Splits tokens into balanced chunks for parallel processing.
* Dispatches chunks to ProcessPoolExecutor workers (FR-06, FR-07).
* Handles worker failures gracefully (NFR-07).
* Merges results and returns structured response.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor

from app.engine.dictionary import Dictionary
from app.engine.worker import process_chunk
from app.schemas.spell import Correction, SpellCheckResponse

logger = logging.getLogger(__name__)

# Matches sequences of Unicode letters (handles accented chars too).
_WORD_RE = re.compile(r"\b[^\W\d_]+\b", re.UNICODE)

# Singleton instance shared across requests.
_checker_instance: "SpellChecker | None" = None


class SpellChecker:
    """Facade that coordinates dictionary, chunking, and parallel workers (FR-06, NFR-07)."""

    def __init__(self) -> None:
        self._dictionary = Dictionary()
        self._worker_count = self._resolve_int("WORKER_COUNT", os.cpu_count() or 1)
        self._chunk_size = self._resolve_int("CHUNK_SIZE", 0)  # 0 → auto
        self._executor = ProcessPoolExecutor(max_workers=self._worker_count)
        logger.info(
            "SpellChecker initialized with %d workers, chunk_size=%s",
            self._worker_count,
            self._chunk_size or "auto",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, text: str) -> SpellCheckResponse:
        """Spell-check *text* and return a structured response (FR-06, FR-07, NFR-07, FR-20).

        Parallelizes processing across worker pool, handles failures gracefully.
        Measures and returns server-side processing time in seconds (FR-20).
        """
        t_start = time.perf_counter()

        tokens = self._tokenise(text)
        chunks = self._split(tokens)

        if not chunks:
            # Empty input
            return SpellCheckResponse(
                word_count=0,
                error_count=0,
                processing_time=round(time.perf_counter() - t_start, 4),
                corrections=[],
            )

        # Submit all chunks to the executor and collect futures
        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(self._executor, process_chunk, chunk, self._dictionary)
            for chunk in chunks
        ]

        # Await all futures with error handling
        try:
            all_results = await asyncio.gather(*futures, return_exceptions=True)
        except Exception as e:
            logger.exception("Unexpected error awaiting futures: %s", e)
            all_results = []

        # Process results, handling both successful results and exceptions
        corrections: list[Correction] = []
        for i, result in enumerate(all_results):
            if isinstance(result, Exception):
                logger.warning(
                    "Worker %d failed: %s; continuing with partial results",
                    i,
                    result,
                )
                continue
            if result is not None:
                corrections.extend(result)

        return SpellCheckResponse(
            word_count=len(tokens),
            error_count=len(corrections),
            processing_time=round(time.perf_counter() - t_start, 4),
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

    def shutdown(self) -> None:
        """Shutdown the executor gracefully (called during app lifespan)."""
        logger.info("Shutting down ProcessPoolExecutor...")
        self._executor.shutdown(wait=True)
        logger.info("ProcessPoolExecutor shutdown complete.")


# ------------------------------------------------------------------
# FastAPI dependency
# ------------------------------------------------------------------

def get_checker() -> SpellChecker:
    """FastAPI dependency that returns the singleton SpellChecker."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = SpellChecker()
    return _checker_instance
