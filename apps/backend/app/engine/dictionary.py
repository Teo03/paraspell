"""Dictionary loader (NFR-12 / engine layer).

Responsible for loading the 370 k-word reference dictionary and its
pre-computed Soundex map into memory once at startup.  The actual
dictionary file and Soundex implementation will be added in a later card;
this module owns the loading contract so every other engine component has a
single import point.

Usage (called from checker.py at startup)
-----------------------------------------
    from app.engine.dictionary import Dictionary
    d = Dictionary()          # loads from DICT_PATH env var, falls back to built-in
    d.contains("hello")       # True
    d.soundex_candidates("wold")  # ["world", "wild", ...]
"""

from __future__ import annotations

import os


class Dictionary:
    """In-memory word list + Soundex index.

    TODO (dictionary card): replace _words stub with real file load.
    """

    def __init__(self) -> None:
        dict_path = os.getenv("DICT_PATH", "")
        self._words: set[str] = self._load(dict_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def contains(self, word: str) -> bool:
        """Return True if *word* (lowercased) is in the dictionary."""
        return word.lower() in self._words

    def soundex_candidates(self, word: str) -> list[str]:
        """Return words that share a Soundex code with *word*.

        TODO (dictionary card): implement real Soundex lookup.
        """
        return []

    def __len__(self) -> int:
        return len(self._words)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: str) -> set[str]:
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return {line.strip().lower() for line in fh if line.strip()}
        # Placeholder — real dictionary loaded by future card.
        return set()
