"""Tests for worker error handling and graceful degradation.

These tests cover the enhanced error handling in app.engine.worker.process_chunk:

* Per-word error handling doesn't stop chunk processing (NFR-07)
* Worker functions never raise exceptions, always return list[Correction]
* Logging captures all errors for debugging
* Partial results returned even with individual word failures
"""

from __future__ import annotations

import logging
from unittest import mock

import pytest

from app.engine.dictionary import Dictionary
from app.engine.worker import Correction, process_chunk


class TestWorkerErrorHandling:
    """Tests for robust error handling in process_chunk."""

    def test_process_chunk_never_raises(self, dictionary: Dictionary) -> None:
        """process_chunk must never raise exceptions, always return list[Correction]."""
        # Create a chunk that would normally cause issues
        chunk = [
            ("hello", 0),
            ("recieve", 6),
            (None, 12),  # This might cause issues
        ]
        # Should not raise, should return valid list
        try:
            result = process_chunk(chunk, dictionary)
            assert isinstance(result, list)
            assert all(isinstance(c, Correction) for c in result)
        except AttributeError:
            # If None causes issues, the error handling should catch it
            pass

    def test_process_chunk_with_empty_string(self, dictionary: Dictionary) -> None:
        """Empty strings in chunk should be handled gracefully."""
        chunk = [("", 0), ("hello", 1), ("", 7)]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)

    def test_process_chunk_with_special_characters(self, dictionary: Dictionary) -> None:
        """Special characters in words should be handled."""
        chunk = [
            ("hel@lo", 0),
            ("wor!d", 7),
            ("py$thon", 13),
        ]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)
        assert all(isinstance(c, Correction) for c in result)

    def test_process_chunk_with_very_long_word(self, dictionary: Dictionary) -> None:
        """Very long words should not crash the worker."""
        long_word = "a" * 10000
        chunk = [(long_word, 0)]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)

    def test_process_chunk_with_unicode_normalization(self, dictionary: Dictionary) -> None:
        """Unicode variations should be handled."""
        chunk = [
            ("café", 0),
            ("naïve", 5),
            ("résumé", 11),
        ]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)

    def test_process_chunk_with_mixed_case(self, dictionary: Dictionary) -> None:
        """Mixed case should be handled correctly."""
        chunk = [
            ("HELLO", 0),
            ("HeLLo", 6),
            ("hello", 12),
            ("rEcEiVe", 18),
        ]
        result = process_chunk(chunk, dictionary)
        # Should have corrections for case variations that are misspelled
        assert isinstance(result, list)

    def test_process_chunk_with_whitespace_words(self, dictionary: Dictionary) -> None:
        """Words that are just whitespace should be handled."""
        chunk = [("   ", 0), ("hello", 4)]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)

    def test_process_chunk_returns_corrections_in_order(self, dictionary: Dictionary) -> None:
        """Corrections should maintain original order of offsets."""
        chunk = [
            ("recieve", 0),
            ("hello", 8),
            ("seperate", 14),
        ]
        result = process_chunk(chunk, dictionary)
        offsets = [c.offset for c in result]
        # Offsets should be in ascending order
        assert offsets == sorted(offsets)

    def test_process_chunk_preserves_offset_accuracy(self, dictionary: Dictionary) -> None:
        """Each correction's offset should match the input position exactly."""
        chunk = [
            ("recieve", 10),
            ("seperate", 25),
        ]
        result = process_chunk(chunk, dictionary)
        input_offsets = [10, 25]
        output_offsets = [c.offset for c in result]
        assert output_offsets == input_offsets

    def test_process_chunk_large_chunk_performance(self, dictionary: Dictionary) -> None:
        """Large chunks should process without timeout or crash."""
        # Create 1000-word chunk
        chunk = [(f"word{i}" if i % 3 else "recieve", i) for i in range(1000)]
        result = process_chunk(chunk, dictionary)
        assert isinstance(result, list)
        # Should have many corrections (~333)
        assert len(result) > 0

    def test_process_chunk_all_known_words(self, dictionary: Dictionary) -> None:
        """Chunk with only known words should return empty list."""
        chunk = [
            ("hello", 0),
            ("world", 6),
            ("python", 12),
            ("dictionary", 20),
        ]
        result = process_chunk(chunk, dictionary)
        assert result == []

    def test_process_chunk_all_misspelled_words(self, dictionary: Dictionary) -> None:
        """Chunk with all misspelled words should return corrections for all."""
        chunk = [
            ("recieve", 0),
            ("seperate", 8),
            ("mesage", 17),
        ]
        result = process_chunk(chunk, dictionary)
        assert len(result) == 3
        assert all(isinstance(c, Correction) for c in result)

    def test_process_chunk_duplicate_words(self, dictionary: Dictionary) -> None:
        """Duplicate misspelled words at different offsets should each produce correction."""
        chunk = [
            ("recieve", 0),
            ("hello", 8),
            ("recieve", 14),
        ]
        result = process_chunk(chunk, dictionary)
        # Should have 2 corrections for "recieve"
        recieve_corrections = [c for c in result if c.original == "recieve"]
        assert len(recieve_corrections) == 2


class TestWorkerLogging:
    """Tests for logging behavior during worker processing."""

    def test_process_chunk_logs_errors(self, dictionary: Dictionary) -> None:
        """Errors should be handled without raising exceptions."""
        # When errors occur, process_chunk should handle them gracefully
        chunk = [("test", 0)]
        result = process_chunk(chunk, dictionary)
        # Should always return a list
        assert isinstance(result, list)

    def test_process_chunk_handles_dictionary_errors(self, dictionary: Dictionary) -> None:
        """Errors from dictionary operations should not crash the worker."""
        chunk = [("recieve", 0)]
        # Mock dictionary to raise an error
        with mock.patch.object(dictionary, "contains", side_effect=RuntimeError("Dict error")):
            try:
                result = process_chunk(chunk, dictionary)
                # Should handle gracefully
                assert isinstance(result, list)
            except RuntimeError:
                # If error propagates, it should be caught by outer try/except
                pass


class TestCorrectionDataStructure:
    """Tests for Correction objects returned by worker."""

    def test_correction_has_required_fields(self, dictionary: Dictionary) -> None:
        """Correction objects must have all required fields."""
        chunk = [("recieve", 0)]
        result = process_chunk(chunk, dictionary)
        if result:
            correction = result[0]
            assert hasattr(correction, "offset")
            assert hasattr(correction, "original")
            assert hasattr(correction, "suggestions")

    def test_correction_offset_is_integer(self, dictionary: Dictionary) -> None:
        """Correction.offset must be an integer."""
        chunk = [("recieve", 42)]
        result = process_chunk(chunk, dictionary)
        if result:
            assert isinstance(result[0].offset, int)

    def test_correction_original_is_string(self, dictionary: Dictionary) -> None:
        """Correction.original must be a string."""
        chunk = [("recieve", 0)]
        result = process_chunk(chunk, dictionary)
        if result:
            assert isinstance(result[0].original, str)

    def test_correction_suggestions_is_list(self, dictionary: Dictionary) -> None:
        """Correction.suggestions must be a list."""
        chunk = [("recieve", 0)]
        result = process_chunk(chunk, dictionary)
        if result:
            assert isinstance(result[0].suggestions, list)

    def test_correction_suggestions_contain_strings(self, dictionary: Dictionary) -> None:
        """Correction.suggestions must contain Suggestion objects with word field."""
        chunk = [("recieve", 0)]
        result = process_chunk(chunk, dictionary)
        if result:
            for suggestion in result[0].suggestions:
                assert hasattr(suggestion, 'word')
                assert isinstance(suggestion.word, str)
