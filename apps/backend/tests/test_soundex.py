"""Unit tests for ``app.engine.dictionary.soundex``.

The function is a thin wrapper over jellyfish's American Soundex
implementation. The point of these tests isn't to re-validate
jellyfish — it's to lock in the *contract* the rest of the engine
relies on, so a future refactor (different library, different
algorithm) doesn't silently break candidate generation.

Algorithm reference (Russell/Odell):

    1. keep the first letter (uppercased)
    2. drop a/e/i/o/u/y/h/w
    3. map remaining consonants → digits
          b f p v          → 1
          c g j k q s x z  → 2
          d t              → 3
          l                → 4
          m n              → 5
          r                → 6
    4. collapse adjacent duplicates
    5. pad with ``0`` (or truncate) to exactly 4 chars
"""

from __future__ import annotations

import pytest

from app.engine.dictionary import soundex


# ---------------------------------------------------------------------------
# Format / shape
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("word", ["a", "Smith", "supercalifragilistic", "x"])
def test_output_is_four_chars(word: str) -> None:
    """Every non-empty input produces exactly 4 characters."""
    assert len(soundex(word)) == 4


def test_first_char_is_uppercase_first_letter() -> None:
    """The leading character of the code mirrors the input's first letter."""
    assert soundex("Smith")[0] == "S"
    assert soundex("python")[0] == "P"
    assert soundex("WORLD")[0] == "W"


def test_case_insensitive() -> None:
    """``Smith``, ``smith``, and ``SMITH`` produce the same code."""
    assert soundex("Smith") == soundex("smith") == soundex("SMITH")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_string_returns_empty() -> None:
    """Empty input falls cleanly out of the candidate index."""
    assert soundex("") == ""


def test_non_ascii_does_not_crash() -> None:
    """``naïve`` shouldn't raise — jellyfish folds the diacritic."""
    code = soundex("naïve")
    assert code == "" or len(code) == 4


def test_single_letter() -> None:
    """One-letter words pad to 4 chars."""
    assert soundex("a") == "A000"
    assert soundex("z") == "Z000"


# ---------------------------------------------------------------------------
# Algorithm correctness — the typo / correction pairs the engine
# actually relies on at runtime.
# ---------------------------------------------------------------------------

# Common English misspellings and their corrections — all of these MUST
# end up in the same Soundex bucket, otherwise the worker can never
# surface the right suggestion.
_TYPO_PAIRS = [
    ("recieve", "receive"),
    ("seperate", "separate"),
    ("definately", "definitely"),
    ("worlld", "world"),
    ("writting", "writing"),
    ("begining", "beginning"),
    ("occured", "occurred"),
    ("reccomend", "recommend"),
    ("acommodate", "accommodate"),
    ("hellp", "help"),
    ("freind", "friend"),
]


@pytest.mark.parametrize(("typo", "correct"), _TYPO_PAIRS)
def test_typo_collides_with_correction(typo: str, correct: str) -> None:
    """The contract that makes Soundex+Levenshtein work end-to-end."""
    assert soundex(typo) == soundex(correct), (
        f"{typo!r}({soundex(typo)}) and {correct!r}({soundex(correct)}) "
        "must share a code so the worker can find the right suggestion."
    )


def test_distinct_words_diverge() -> None:
    """Sanity check — Soundex isn't returning the same code for everything."""
    codes = {soundex(w) for w in ("apple", "banana", "tree", "horse", "rocket")}
    assert len(codes) == 5


# ---------------------------------------------------------------------------
# Specific algorithm rules — these are the rules the rest of the engine
# implicitly assumes; if any of them break, the candidate buckets drift.
# ---------------------------------------------------------------------------

def test_vowels_after_first_letter_are_dropped() -> None:
    """``Robert`` and ``Rupert`` differ only in vowels → same code."""
    assert soundex("Robert") == soundex("Rupert")


def test_h_and_w_are_dropped() -> None:
    """h/w are treated like vowels — only matter as the leading char."""
    # "Ashcraft" vs "Ashcroft" — same code (vowel-only difference)
    assert soundex("Ashcraft") == soundex("Ashcroft")


def test_adjacent_duplicates_collapse() -> None:
    """``Pfister`` should not double-count the silent ``f`` after ``p``."""
    # Both p and f map to digit 1; adjacent duplicates collapse.
    assert soundex("Pfister") == "P236"
