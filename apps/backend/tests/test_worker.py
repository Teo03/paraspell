"""Tests for ``app.engine.worker.process_chunk``.

The worker is the orchestration layer that ties Dictionary's data
structures to the suggestion ranking pipeline:

    membership → Soundex filter → length pre-filter → Levenshtein rank → top-N

These tests cover the contract every other layer (router, end-to-end
parallel checker) depends on:
    * known words pass through silently
    * misspellings produce ``Correction`` rows with offset preserved
    * suggestions are ranked best-first, capped at ``MAX_SUGGESTIONS``
    * scores stay inside the [0, 1] interval pydantic enforces
    * the right correction makes top-5 for common English typos
"""

from __future__ import annotations

import pytest

from app.engine.dictionary import Dictionary
from app.engine.worker import MAX_DISTANCE, MAX_SUGGESTIONS, process_chunk


# ---------------------------------------------------------------------------
# Membership pass-through
# ---------------------------------------------------------------------------

class TestKnownWords:
    def test_known_word_produces_no_correction(
        self, dictionary: Dictionary
    ) -> None:
        """Words in the dictionary must not appear in the output."""
        out = process_chunk([("hello", 0)], dictionary)
        assert out == []

    def test_mixed_known_and_unknown(self, dictionary: Dictionary) -> None:
        """Known words filter out cleanly even when interleaved."""
        chunk = [
            ("hello", 0),       # known
            ("recieve", 6),     # misspelled
            ("python", 14),     # known
            ("seperate", 21),   # misspelled
        ]
        out = process_chunk(chunk, dictionary)
        originals = [c.original for c in out]
        assert originals == ["recieve", "seperate"]

    def test_empty_chunk(self, dictionary: Dictionary) -> None:
        """No tokens → no corrections (and no exceptions)."""
        assert process_chunk([], dictionary) == []


# ---------------------------------------------------------------------------
# Correction shape — offset, original, suggestion structure
# ---------------------------------------------------------------------------

class TestCorrectionShape:
    def test_offset_preserved(self, dictionary: Dictionary) -> None:
        """The offset arrives in the response unchanged so the frontend
        can highlight the right span."""
        out = process_chunk([("recieve", 42)], dictionary)
        assert len(out) == 1
        assert out[0].offset == 42

    def test_original_preserved(self, dictionary: Dictionary) -> None:
        """``original`` echoes the surface form the user typed."""
        out = process_chunk([("Recieve", 0)], dictionary)
        assert out[0].original == "Recieve"

    def test_suggestions_capped_at_max(self, dictionary: Dictionary) -> None:
        """Even buckets with hundreds of candidates respect MAX_SUGGESTIONS."""
        out = process_chunk([("seperate", 0)], dictionary)
        assert 0 < len(out[0].suggestions) <= MAX_SUGGESTIONS


# ---------------------------------------------------------------------------
# Ranking — score range, ordering, top-5 hits
# ---------------------------------------------------------------------------

class TestRanking:
    def test_scores_in_unit_interval(self, dictionary: Dictionary) -> None:
        """Pydantic's Suggestion.score has ``ge=0.0, le=1.0`` — must hold."""
        out = process_chunk([("recieve", 0), ("seperate", 8)], dictionary)
        for c in out:
            for s in c.suggestions:
                assert 0.0 <= s.score <= 1.0

    def test_suggestions_sorted_descending(self, dictionary: Dictionary) -> None:
        """Best-first ordering — frontend renders the top suggestion."""
        out = process_chunk([("definately", 0)], dictionary)
        scores = [s.score for s in out[0].suggestions]
        assert scores == sorted(scores, reverse=True), (
            f"suggestions should be sorted desc by score, got {scores}"
        )

    @pytest.mark.parametrize(
        ("typo", "expected_correction"),
        [
            ("recieve", "receive"),
            ("seperate", "separate"),
            ("definately", "definitely"),
            ("worlld", "world"),
            ("begining", "beginning"),
            ("occured", "occurred"),
            ("reccomend", "recommend"),
            ("acommodate", "accommodate"),
        ],
    )
    def test_correct_word_in_top_suggestions(
        self,
        dictionary: Dictionary,
        typo: str,
        expected_correction: str,
    ) -> None:
        """The end-to-end smoke test: typing a common typo must surface
        the expected correction in the top-N."""
        out = process_chunk([(typo, 0)], dictionary)
        assert len(out) == 1, f"{typo!r} should be flagged as misspelled"
        words = [s.word for s in out[0].suggestions]
        assert expected_correction in words, (
            f"{expected_correction!r} should appear in top {MAX_SUGGESTIONS} "
            f"for {typo!r}, got {words}"
        )


# ---------------------------------------------------------------------------
# Filter behaviour — distance and length pre-filter
# ---------------------------------------------------------------------------

class TestFilters:
    def test_garbage_input_yields_few_or_no_suggestions(
        self, dictionary: Dictionary
    ) -> None:
        """A random consonant cluster has no near-neighbours."""
        out = process_chunk([("xqzqzqz", 0)], dictionary)
        # The word must still be flagged (it's not in the dict) — but the
        # suggestion list is allowed to be empty since nothing in the
        # Soundex bucket is within MAX_DISTANCE edits.
        assert len(out) == 1
        assert all(0.0 <= s.score <= 1.0 for s in out[0].suggestions)

    def test_no_suggestion_exceeds_max_distance(
        self, dictionary: Dictionary
    ) -> None:
        """The distance filter rejects candidates with too many edits.

        Score = 1 - dist/max_len, so a candidate at exactly MAX_DISTANCE
        edits still has score > 0; anything farther is dropped before
        scoring. The implication: scores must lie strictly above
        ``1 - MAX_DISTANCE / max_len_lower_bound``.
        """
        out = process_chunk([("recieve", 0)], dictionary)
        for s in out[0].suggestions:
            # Lower bound: shortest possible candidate length is 1.
            # We use max(len(query), len(s.word)) to mirror the formula
            # in worker._rank_suggestions.
            max_len = max(len("recieve"), len(s.word))
            implied_distance = round((1.0 - s.score) * max_len)
            assert implied_distance <= MAX_DISTANCE


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_chunk_same_output(self, dictionary: Dictionary) -> None:
        """Two identical calls produce identical responses (no randomness)."""
        chunk = [("recieve", 0), ("seperate", 8), ("worlld", 17)]
        out_a = process_chunk(chunk, dictionary)
        out_b = process_chunk(chunk, dictionary)
        assert [(c.original, c.offset, [(s.word, s.score) for s in c.suggestions])
                for c in out_a] == [
            (c.original, c.offset, [(s.word, s.score) for s in c.suggestions])
            for c in out_b
        ]
