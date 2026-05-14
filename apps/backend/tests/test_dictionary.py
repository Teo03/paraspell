"""Tests for ``app.engine.dictionary.Dictionary``.

Covers the data layer the worker depends on:
    * ``contains`` — trie-backed membership
    * ``soundex_candidates`` — SQLite-backed phonetic lookup
    * LRU cache accounting (hits / misses / eviction)
    * Pickle round-trip (the path that ``ProcessPoolExecutor.submit``
      takes when the Dictionary is sent as an arg)
    * Construction errors when the data files are missing
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

import pytest

from app.engine.dictionary import Dictionary, soundex


# ---------------------------------------------------------------------------
# Membership — Dictionary.contains
# ---------------------------------------------------------------------------

class TestContains:
    def test_known_word_hits(self, dictionary: Dictionary) -> None:
        assert dictionary.contains("hello")
        assert dictionary.contains("python")
        assert dictionary.contains("world")

    def test_misspelling_misses(self, dictionary: Dictionary) -> None:
        # These nonsense strings exist in no English dictionary.
        assert not dictionary.contains("asdfghjkl")
        assert not dictionary.contains("qzxqzxqzx")

    def test_case_insensitive(self, dictionary: Dictionary) -> None:
        """User-typed casing must not affect membership."""
        assert dictionary.contains("Hello")
        assert dictionary.contains("WORLD")
        assert dictionary.contains("PyThOn")

    def test_empty_string_misses(self, dictionary: Dictionary) -> None:
        """Defensive: tokenizer shouldn't yield empties, but if one slips
        through it must not be treated as a hit."""
        assert not dictionary.contains("")

    def test_dunder_in_works(self, dictionary: Dictionary) -> None:
        assert "hello" in dictionary
        assert "asdfghjkl" not in dictionary
        # __contains__ must guard against non-string lookups.
        assert 42 not in dictionary  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Sizing / iteration
# ---------------------------------------------------------------------------

class TestSize:
    def test_len_in_expected_range(self, dictionary: Dictionary) -> None:
        """The committed trie comes from dwyl/english-words (~370 k)."""
        assert 350_000 <= len(dictionary) <= 400_000

    def test_iter_words_count_matches_len(self, dictionary: Dictionary) -> None:
        # Don't materialise the full list — count via sum() to stay light.
        assert sum(1 for _ in dictionary.iter_words()) == len(dictionary)

    def test_iter_words_includes_known(self, dictionary: Dictionary) -> None:
        """Spot-check a small subset is reachable via the iterator."""
        sample = set()
        target = {"hello", "world", "python"}
        for w in dictionary.iter_words():
            if w in target:
                sample.add(w)
            if sample == target:
                break
        assert sample == target


# ---------------------------------------------------------------------------
# Phonetic candidate lookup — Dictionary.soundex_candidates
# ---------------------------------------------------------------------------

class TestSoundexCandidates:
    def test_known_word_appears_in_its_own_bucket(
        self, dictionary: Dictionary
    ) -> None:
        candidates = dictionary.soundex_candidates("receive")
        assert "receive" in candidates

    def test_typo_and_correction_share_bucket(self, dictionary: Dictionary) -> None:
        """The contract that makes Soundex+Levenshtein work end-to-end."""
        a = set(dictionary.soundex_candidates("recieve"))
        b = set(dictionary.soundex_candidates("receive"))
        assert "receive" in a, "typo's bucket must contain the correction"
        assert a == b, "typo and correction map to the same bucket"

    def test_unknown_code_returns_empty_list(self, dictionary: Dictionary) -> None:
        """An empty input yields an empty Soundex code → empty bucket."""
        assert dictionary.soundex_candidates("") == []

    def test_returned_list_is_a_fresh_copy(self, dictionary: Dictionary) -> None:
        """Caller may sort/mutate without poisoning the LRU cache."""
        first = dictionary.soundex_candidates("receive")
        first.append("__poison__")
        second = dictionary.soundex_candidates("receive")
        assert "__poison__" not in second

    def test_results_are_deterministic(self, dictionary: Dictionary) -> None:
        """Same input → same output across calls (cached or not)."""
        a = dictionary.soundex_candidates("hello")
        b = dictionary.soundex_candidates("hello")
        assert a == b


# ---------------------------------------------------------------------------
# LRU cache behaviour
# ---------------------------------------------------------------------------

class TestLRUCache:
    def test_repeated_codes_hit_cache(self) -> None:
        """Querying the same code twice → 1 miss, 1 hit."""
        d = Dictionary(cache_size=64)
        try:
            d.soundex_candidates("recieve")
            d.soundex_candidates("recieve")  # same code, R210
            info = d.cache_info()
            assert info["misses"] == 1
            assert info["hits"] == 1
        finally:
            d.close()

    def test_different_words_same_code_hit_cache(self) -> None:
        """``recieve`` and ``recipe`` both hash to R210 → 2nd is a hit."""
        d = Dictionary(cache_size=64)
        try:
            assert soundex("recieve") == soundex("recipe")  # precondition
            d.soundex_candidates("recieve")
            d.soundex_candidates("recipe")
            info = d.cache_info()
            assert info["hits"] == 1
            assert info["misses"] == 1
        finally:
            d.close()

    def test_eviction_when_capacity_exceeded(self) -> None:
        """A 2-slot LRU evicts the oldest entry once a 3rd unique code arrives."""
        d = Dictionary(cache_size=2)
        try:
            # Three distinct codes — guaranteed by R/S/B starting letters.
            d.soundex_candidates("recieve")    # R210
            d.soundex_candidates("seperate")   # S163
            d.soundex_candidates("begining")   # B255 — evicts R210

            # currsize must stay at the configured maximum
            info = d.cache_info()
            assert info["currsize"] == 2

            # Re-querying the evicted code re-runs SQL → miss count grows
            misses_before = info["misses"]
            d.soundex_candidates("recieve")
            assert d.cache_info()["misses"] == misses_before + 1
        finally:
            d.close()


# ---------------------------------------------------------------------------
# Pickle round-trip — exercises __getstate__ / __setstate__
# ---------------------------------------------------------------------------

class TestPickle:
    def test_roundtrip_preserves_membership(self, dictionary: Dictionary) -> None:
        clone = pickle.loads(pickle.dumps(dictionary))
        try:
            assert clone.contains("hello")
            assert not clone.contains("asdfghjkl")
            assert len(clone) == len(dictionary)
        finally:
            clone.close()

    def test_roundtrip_preserves_soundex_buckets(
        self, dictionary: Dictionary
    ) -> None:
        clone = pickle.loads(pickle.dumps(dictionary))
        try:
            assert (
                set(clone.soundex_candidates("receive"))
                == set(dictionary.soundex_candidates("receive"))
            )
        finally:
            clone.close()

    def test_roundtrip_resets_cache(self, dictionary: Dictionary) -> None:
        """Each unpickled clone has a fresh LRU; warmth doesn't carry over."""
        # Warm the source's cache so its hit count is non-zero.
        dictionary.soundex_candidates("hello")
        dictionary.soundex_candidates("hello")
        clone = pickle.loads(pickle.dumps(dictionary))
        try:
            assert clone.cache_info()["hits"] == 0
            assert clone.cache_info()["misses"] == 0
            assert clone.cache_info()["currsize"] == 0
        finally:
            clone.close()


# ---------------------------------------------------------------------------
# Construction errors / path resolution
# ---------------------------------------------------------------------------

class TestPaths:
    def test_missing_trie_raises(self, tmp_path: Path) -> None:
        """A clear FileNotFoundError beats silent zero-correction output."""
        # Build a placeholder SQLite so only the trie path fails.
        bogus_trie = tmp_path / "no_such.marisa"
        bogus_db = tmp_path / "no_such.sqlite"
        with pytest.raises(FileNotFoundError, match="MARISA-trie"):
            Dictionary(trie_path=bogus_trie, db_path=bogus_db)

    def test_missing_db_raises(self, tmp_path: Path, dictionary: Dictionary) -> None:
        """The trie loads fine, but the SQLite file is missing."""
        # Reuse the real trie so we get past the first check.
        bogus_db = tmp_path / "no_such.sqlite"
        with pytest.raises(FileNotFoundError, match="Soundex"):
            Dictionary(trie_path=dictionary._trie_path, db_path=bogus_db)

    def test_env_var_overrides_default_path(
        self, monkeypatch: pytest.MonkeyPatch, dictionary: Dictionary
    ) -> None:
        """Setting DICT_PATH / SOUNDEX_DB_PATH steers the loader."""
        monkeypatch.setenv("DICT_PATH", str(dictionary._trie_path))
        monkeypatch.setenv("SOUNDEX_DB_PATH", str(dictionary._db_path))
        d = Dictionary()  # no explicit args
        try:
            assert len(d) == len(dictionary)
        finally:
            d.close()

    def test_close_is_idempotent(self, dictionary: Dictionary) -> None:
        """A clone can be closed twice without raising."""
        clone = pickle.loads(pickle.dumps(dictionary))
        clone.close()
        clone.close()  # must not raise


# ---------------------------------------------------------------------------
# lookup() — clean public alias for contains()
# ---------------------------------------------------------------------------

class TestLookup:
    def test_known_word_returns_true(self, dictionary: Dictionary) -> None:
        assert dictionary.lookup("hello") is True
        assert dictionary.lookup("python") is True

    def test_misspelling_returns_false(self, dictionary: Dictionary) -> None:
        assert dictionary.lookup("recieve") is False
        assert dictionary.lookup("seperate") is False

    def test_case_insensitive(self, dictionary: Dictionary) -> None:
        assert dictionary.lookup("Hello") is True
        assert dictionary.lookup("WORLD") is True

    def test_empty_string_returns_false(self, dictionary: Dictionary) -> None:
        assert dictionary.lookup("") is False

    def test_agrees_with_contains(self, dictionary: Dictionary) -> None:
        """lookup and contains must always return the same value."""
        for word in ("hello", "recieve", "python", "xqzqzx", ""):
            assert dictionary.lookup(word) == dictionary.contains(word), (
                f"lookup({word!r}) disagrees with contains({word!r})"
            )


# ---------------------------------------------------------------------------
# get_candidates() — Soundex + Levenshtein ranked list
# ---------------------------------------------------------------------------

class TestGetCandidates:
    def test_returns_list(self, dictionary: Dictionary) -> None:
        result = dictionary.get_candidates("recieve", top_n=5)
        assert isinstance(result, list)

    def test_top_n_respected(self, dictionary: Dictionary) -> None:
        result = dictionary.get_candidates("recieve", top_n=3)
        assert len(result) <= 3

    def test_top_n_zero_returns_empty(self, dictionary: Dictionary) -> None:
        assert dictionary.get_candidates("recieve", top_n=0) == []

    def test_known_word_still_returns_candidates(
        self, dictionary: Dictionary
    ) -> None:
        """Even correctly spelled words have a Soundex bucket — the method
        doesn't short-circuit on membership, it always returns the ranked
        neighbours."""
        result = dictionary.get_candidates("receive", top_n=5)
        assert isinstance(result, list)

    def test_correct_word_appears_in_candidates(
        self, dictionary: Dictionary
    ) -> None:
        """The primary contract: the right correction must be in the list."""
        result = dictionary.get_candidates("recieve", top_n=5)
        assert "receive" in result, f"expected 'receive' in {result}"

    def test_results_are_strings(self, dictionary: Dictionary) -> None:
        result = dictionary.get_candidates("seperate", top_n=5)
        assert all(isinstance(w, str) for w in result)

    def test_results_are_ranked_best_first(self, dictionary: Dictionary) -> None:
        """Verify ordering is descending by the frequency-blended score.

        Pre-v2 this test asserted monotonic Levenshtein distance — but
        the v2 ranking can legitimately put a slightly-more-distant
        very-common word above a closer rare word (that's the whole
        reason for the freq blend; see ``thier → their`` parametrisation
        below). The honest invariant is the score itself, not the
        underlying edit distance.
        """
        from rapidfuzz.distance import Levenshtein

        from app.engine.dictionary import _score_with_freq

        query = "recieve"
        qlen = len(query)
        result = dictionary.get_candidates(query, top_n=5)

        # Look up the same frequency table the ranker used.
        freq_for = dict(dictionary._soundex_candidates_with_freq(query))

        scores = [
            _score_with_freq(
                Levenshtein.distance(query, cand),
                qlen,
                len(cand),
                freq_for.get(cand, 0),
            )
            for cand in result
        ]
        assert scores == sorted(scores, reverse=True), (
            f"candidates should be ranked highest-score-first, got {scores}"
        )

    def test_garbage_input_returns_list(self, dictionary: Dictionary) -> None:
        """Nonsense input must not raise — empty bucket → empty list."""
        result = dictionary.get_candidates("xqzqzqzqzqz", top_n=5)
        assert isinstance(result, list)

    @pytest.mark.parametrize(
        ("typo", "expected"),
        [
            ("recieve", "receive"),
            ("seperate", "separate"),
            ("definately", "definitely"),
            ("begining", "beginning"),
            ("occured", "occurred"),
        ],
    )
    def test_common_typos_surface_correction(
        self, dictionary: Dictionary, typo: str, expected: str
    ) -> None:
        result = dictionary.get_candidates(typo, top_n=5)
        assert expected in result, (
            f"expected {expected!r} in get_candidates({typo!r}, 5), got {result}"
        )


# ---------------------------------------------------------------------------
# Frequency-blended ranking (v2) — top-1 must be the common-English answer
# ---------------------------------------------------------------------------

class TestFreqBlendRanking:
    """The v2 score-blend is supposed to deliver the *right* top suggestion,
    not just include it somewhere in the top-5. Each row here is a case
    that v1 (alphabetical tiebreak on equal Levenshtein) got wrong —
    they're the regression frontier for the frequency change.
    """

    @pytest.mark.parametrize(
        ("typo", "expected_top"),
        [
            ("recieve", "receive"),   # v1 returned "reachieve" (longer ⇒ higher norm-score)
            ("wrds",    "words"),     # v1 returned "wards"     (alphabetical)
            ("smal",    "small"),     # v1 returned "samal"     (alphabetical)
            ("exmple",  "example"),
            ("thier",   "their"),     # dist 2 — frequency must overcome the gap
        ],
    )
    def test_top_suggestion_is_common_english(
        self, dictionary: Dictionary, typo: str, expected_top: str
    ) -> None:
        result = dictionary.get_candidates(typo, top_n=5)
        assert result, f"empty candidate list for {typo!r}"
        assert result[0] == expected_top, (
            f"top suggestion for {typo!r} was {result[0]!r}, expected {expected_top!r} "
            f"(full top-5: {result})"
        )

    def test_zero_freq_candidate_falls_back_to_base_score(
        self, dictionary: Dictionary
    ) -> None:
        """Words missing from Norvig's data have freq=0 → no boost. The
        score for those must equal the v1 formula `1 - dist/max(qlen,clen)`,
        i.e. the freq blend is invisible when frequency is unknown.
        """
        from app.engine.dictionary import _score_with_freq

        # freq=0 → score must equal pure Levenshtein similarity
        assert _score_with_freq(dist=1, qlen=5, clen=5, freq=0) == pytest.approx(0.8)
        assert _score_with_freq(dist=2, qlen=7, clen=9, freq=0) == pytest.approx(1 - 2/9)

    def test_score_blend_bounded_in_unit_interval(self) -> None:
        """Final score must stay in [0, 1] so SpellCheckResponse validates."""
        from app.engine.dictionary import _score_with_freq

        # Maximum-frequency word ("the", count 2.3e10) at minimum distance
        s = _score_with_freq(dist=0, qlen=3, clen=3, freq=23_135_851_162)
        assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# Blocklist — words.marisa must not contain known-bad dwyl entries
# ---------------------------------------------------------------------------

class TestBlocklist:
    """``scripts/build_dict.py`` drops a curated list of typo/archaic
    spellings before serialising the trie. The build script verifies the
    drop, but a runtime check catches a stale committed artifact too —
    e.g. if someone rebuilds the trie without the blocklist and pushes it.
    """

    @pytest.mark.parametrize(
        "typo",
        ["untill", "embarras", "accomodate", "wierd",
         "calender", "cemetary", "noticable", "priviledge"],
    )
    def test_blocklisted_typos_not_in_trie(
        self, dictionary: Dictionary, typo: str
    ) -> None:
        assert not dictionary.contains(typo), (
            f"{typo!r} should be blocklisted from words.marisa "
            "but the runtime trie still treats it as a valid word"
        )
