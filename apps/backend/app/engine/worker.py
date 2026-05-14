"""Parallel worker logic (FR-06, FR-07 / NFR-12).

Each worker receives a chunk of pre-tokenised words, checks them against
the shared ``Dictionary``, and returns ``Correction`` objects with up to
``MAX_SUGGESTIONS`` ranked suggestions.

Pipeline per word
-----------------
    1. Trie membership check               (Dictionary.contains)
    2. Phonetic candidate filter (Soundex) (Dictionary.soundex_candidates)
    3. Length pre-filter   |len(c)-len(w)| ≤ MAX_DISTANCE  (cheap)
    4. Edit-distance ranking (Levenshtein, rapidfuzz)
    5. Sort by score, take top MAX_SUGGESTIONS

This module is the function ``ProcessPoolExecutor`` will pickle and send
to child workers (see ``checker.py``). Everything below the function
signature is **stateless**: the only mutable thing is the local
``corrections`` list, and ``Dictionary`` is constructed before fork so
the trie + Soundex index are shared via Linux copy-on-write — no locks,
no per-call allocation of the 370 k key set.

Design pattern note
-------------------
* **Strategy** — ``Dictionary.soundex_candidates`` is the phonetic
  strategy, ``rapidfuzz.distance.Levenshtein`` is the ranking strategy.
  Both can be swapped (Metaphone / Damerau-Levenshtein / Jaro-Winkler)
  without touching this orchestration code.
* The function shape itself is **Pipeline**: filter → rank → top-N. Kept
  inline (rather than a class hierarchy) because each stage is a single
  call and a class would cost more in pickling overhead than it would
  save in clarity.
"""

from __future__ import annotations

import os

from rapidfuzz.distance import Levenshtein

from app.engine.dictionary import Dictionary, _score_with_freq
from app.schemas.spell import Correction, Suggestion


# ---------------------------------------------------------------------------
# Tunables — read once at module import. Resolved per-process; with
# ProcessPoolExecutor each worker re-imports this module post-fork, so
# the values are stable for the lifetime of the worker.
# ---------------------------------------------------------------------------

# UC-03 / .env.example MAX_SUGGESTIONS — at most this many suggestions per
# misspelled word. Defaults to 5 per the SRS.
MAX_SUGGESTIONS: int = int(os.getenv("MAX_SUGGESTIONS", "5"))

# Levenshtein distance > MAX_DISTANCE is dropped before ranking. Empirically
# the right correction for a typo is at edit-distance 1 or 2 in >95% of
# cases; allowing 3 catches doubled letters / vowel swaps in long words;
# 4+ produces semantic noise (e.g. "the" → "those"). Configurable so the
# benchmark task in Part 3 can tune it.
MAX_DISTANCE: int = int(os.getenv("MAX_EDIT_DISTANCE", "3"))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_chunk(
    chunk: list[tuple[str, int]],
    dictionary: Dictionary,
) -> list[Correction]:
    """Check a chunk of ``(word, offset)`` pairs with fault tolerance (NFR-07).

    Parameters
    ----------
    chunk:
        Tokens this worker is responsible for. The chunk is already load-
        balanced by ``checker.SpellChecker._split`` so workers finish at
        roughly the same time.
    dictionary:
        Shared read-only ``Dictionary`` instance (built before fork).

    Returns
    -------
    list[Correction]
        One entry per misspelled word in *chunk*. Order matches input order.
        On partial failure, returns corrections found before the error.
        Never raises; always returns a valid list.
    """
    import logging

    logger = logging.getLogger(__name__)
    corrections: list[Correction] = []

    try:
        for word, offset in chunk:
            try:
                if dictionary.contains(word):
                    continue

                suggestions = _rank_suggestions(word, dictionary)
                corrections.append(
                    Correction(original=word, offset=offset, suggestions=suggestions)
                )
            except Exception as e:
                # Log the error for this individual word but continue processing
                logger.warning(
                    "Failed to process word '%s' at offset %d: %s",
                    word,
                    offset,
                    e,
                )
                continue
    except Exception as e:
        # Catch any unexpected errors (e.g., from Dictionary initialization)
        # Log and return partial results instead of raising
        logger.exception(
            "Chunk processing failed after %d corrections found: %s",
            len(corrections),
            e,
        )

    return corrections


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _rank_suggestions(word: str, dictionary: Dictionary) -> list[Suggestion]:
    """Soundex-filter then Levenshtein-rank candidates for *word*.

    Length pre-filter
        ``Levenshtein(a, b) ≥ |len(a) - len(b)|`` so any candidate whose
        length differs by more than MAX_DISTANCE can never qualify. We
        skip the (relatively expensive) edit-distance call for those —
        a meaningful speedup on common short words where Soundex returns
        thousands of candidates.

    Score
        ``base = 1 - dist / max(len(query), len(candidate))`` produces a
        value in [0, 1] from edit distance alone — the v1 formula.
        ``_score_with_freq`` then geometrically pulls that toward 1 by an
        amount proportional to ``log10(freq+1)``, so common candidates
        beat rare ones at the same edit distance (and can even overcome
        a small distance gap, e.g. ``thier→their`` at dist=2 beating
        ``thier→theer`` at dist=1). Words missing from Norvig's data
        have freq=0 → no boost → behaviour reduces to the v1 formula.
    """
    query = word.lower()
    candidates = dictionary._soundex_candidates_with_freq(query)
    if not candidates:
        return []

    qlen = len(query)
    scored: list[tuple[float, int, int, str]] = []  # (score, dist, -freq, word)

    for candidate, freq in candidates:
        # Cheap length pre-filter — no allocation, no C call.
        if abs(len(candidate) - qlen) > MAX_DISTANCE:
            continue

        # ``score_cutoff`` lets rapidfuzz bail out early once the running
        # distance exceeds the threshold. Matches the post-filter below
        # but saves cycles inside the C extension.
        dist = Levenshtein.distance(query, candidate, score_cutoff=MAX_DISTANCE)
        if dist > MAX_DISTANCE:
            continue

        score = _score_with_freq(dist, qlen, len(candidate), freq)
        # Negate freq so the secondary sort prefers commoner words on
        # near-ties — most of the freq influence is already in `score`,
        # but identical scores still need a deterministic order.
        scored.append((score, dist, -freq, candidate))

    # Sort: highest score first; tie-break on shorter distance, then on
    # higher frequency (smaller -freq), then alphabetical for determinism.
    scored.sort(key=lambda t: (-t[0], t[1], t[2], t[3]))

    return [
        Suggestion(word=cand, score=score)
        for score, _dist, _nfreq, cand in scored[:MAX_SUGGESTIONS]
    ]
