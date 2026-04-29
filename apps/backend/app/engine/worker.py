"""Parallel worker logic (FR-06, FR-07 / NFR-12).

Each worker receives a chunk of pre-tokenised words, checks them against the
shared Dictionary, and returns a list of Correction objects.

The multiprocessing pool is managed by SpellChecker (checker.py); this module
owns only the per-chunk processing function so it can be safely pickled and
sent to child processes.

TODO (workers card): implement real parallel dispatch with
    concurrent.futures.ProcessPoolExecutor and the WORKER_COUNT / CHUNK_SIZE
    env vars from .env.
"""

from __future__ import annotations

from app.engine.dictionary import Dictionary
from app.schemas.spell import Correction, Suggestion


def process_chunk(chunk: list[tuple[str, int]], dictionary: Dictionary) -> list[Correction]:
    """Check a chunk of (word, offset) pairs and return corrections.

    Parameters
    ----------
    chunk:
        List of ``(word, character_offset)`` tuples for this worker's slice.
    dictionary:
        Shared read-only Dictionary instance (safe across processes because
        it is constructed before the fork, not after).

    Returns
    -------
    list[Correction]
        One entry per misspelled word found in *chunk*.
    """
    corrections: list[Correction] = []

    for word, offset in chunk:
        if dictionary.contains(word):
            continue

        candidates = dictionary.soundex_candidates(word)
        suggestions = [
            Suggestion(word=candidate, score=1.0)
            for candidate in candidates[:5]   # UC-03: up to 5
        ]
        corrections.append(
            Correction(original=word, offset=offset, suggestions=suggestions)
        )

    return corrections
