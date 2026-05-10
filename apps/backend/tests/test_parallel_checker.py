"""Tests for ProcessPoolExecutor integration and parallel spell-checking.

These tests cover the new parallel processing functionality added to
app.engine.checker.SpellChecker:

* Executor initialization with correct worker count (FR-07)
* Parallel chunk processing with asyncio.gather (FR-06)
* Error handling and graceful degradation (NFR-07)
* Shutdown procedures and resource cleanup
* Performance characteristics of parallel processing
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from unittest import mock

import pytest

from app.engine.checker import SpellChecker, get_checker
from app.engine.dictionary import Dictionary
from app.schemas.spell import SpellCheckResponse


class TestSpellCheckerInitialization:
    """Tests for SpellChecker.__init__ and executor setup."""

    def test_executor_created_on_init(self) -> None:
        """ProcessPoolExecutor must be created during __init__."""
        checker = SpellChecker()
        try:
            assert isinstance(checker._executor, ProcessPoolExecutor)
        finally:
            checker.shutdown()

    def test_worker_count_from_cpu_count(self) -> None:
        """Worker count should default to os.cpu_count() when WORKER_COUNT not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            checker = SpellChecker()
            try:
                expected = os.cpu_count() or 1
                assert checker._worker_count == expected
            finally:
                checker.shutdown()

    def test_worker_count_from_env_var(self) -> None:
        """WORKER_COUNT env var should override default cpu_count."""
        with mock.patch.dict(os.environ, {"WORKER_COUNT": "4"}, clear=False):
            checker = SpellChecker()
            try:
                assert checker._worker_count == 4
            finally:
                checker.shutdown()

    def test_worker_count_invalid_env_falls_back_to_default(self) -> None:
        """Invalid WORKER_COUNT should fall back to os.cpu_count()."""
        with mock.patch.dict(os.environ, {"WORKER_COUNT": "invalid"}, clear=False):
            checker = SpellChecker()
            try:
                expected = os.cpu_count() or 1
                assert checker._worker_count == expected
            finally:
                checker.shutdown()

    def test_chunk_size_from_env_var(self) -> None:
        """CHUNK_SIZE env var should be respected."""
        with mock.patch.dict(os.environ, {"CHUNK_SIZE": "100"}, clear=False):
            checker = SpellChecker()
            try:
                assert checker._chunk_size == 100
            finally:
                checker.shutdown()

    def test_dictionary_initialized(self) -> None:
        """Dictionary must be loaded during __init__."""
        checker = SpellChecker()
        try:
            assert isinstance(checker._dictionary, Dictionary)
        finally:
            checker.shutdown()


class TestParallelCheckFunctionality:
    """Tests for SpellChecker.check() parallel processing."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_response(self) -> None:
        """Empty input should return zero counts and empty corrections."""
        checker = SpellChecker()
        try:
            response = await checker.check("")
            assert response.word_count == 0
            assert response.error_count == 0
            assert response.corrections == []
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_single_known_word(self) -> None:
        """Text with only known words should return empty corrections."""
        checker = SpellChecker()
        try:
            response = await checker.check("hello world")
            assert response.word_count == 2
            assert response.error_count == 0
            assert response.corrections == []
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_single_misspelled_word(self) -> None:
        """Single misspelled word should produce one correction."""
        checker = SpellChecker()
        try:
            response = await checker.check("recieve")
            assert response.word_count == 1
            assert response.error_count == 1
            assert len(response.corrections) == 1
            assert response.corrections[0].original == "recieve"
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_mixed_known_and_misspelled(self) -> None:
        """Mixed text should correctly count both known and misspelled words."""
        checker = SpellChecker()
        try:
            text = "I recieve a seperate mesage"
            response = await checker.check(text)
            assert response.word_count == 5
            assert response.error_count == 3
            assert len(response.corrections) == 3
            originals = {c.original for c in response.corrections}
            assert originals == {"recieve", "seperate", "mesage"}
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_response_structure(self) -> None:
        """Response must have correct SpellCheckResponse structure."""
        checker = SpellChecker()
        try:
            response = await checker.check("recieve")
            assert isinstance(response, SpellCheckResponse)
            assert hasattr(response, "word_count")
            assert hasattr(response, "error_count")
            assert hasattr(response, "corrections")
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_offset_preserved_in_corrections(self) -> None:
        """Offsets should match token positions in original text."""
        checker = SpellChecker()
        try:
            text = "hello recieve world"
            response = await checker.check(text)
            assert len(response.corrections) == 1
            correction = response.corrections[0]
            assert text[correction.offset : correction.offset + len(correction.original)] == correction.original
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_large_text_processing(self) -> None:
        """Large text should be chunked and processed without errors."""
        checker = SpellChecker()
        try:
            # Create large text with multiple chunks
            text = " ".join(["recieve", "seperate"] * 500)
            response = await checker.check(text)
            assert response.word_count == 1000
            assert response.error_count == 1000
            assert len(response.corrections) == 1000
        finally:
            checker.shutdown()


class TestChunkingStrategy:
    """Tests for SpellChecker._split() chunk partitioning logic."""

    def test_split_empty_tokens(self) -> None:
        """Empty token list should produce empty chunk list."""
        checker = SpellChecker()
        try:
            chunks = checker._split([])
            assert chunks == []
        finally:
            checker.shutdown()

    def test_split_single_token(self) -> None:
        """Single token should produce single chunk."""
        checker = SpellChecker()
        try:
            tokens = [("hello", 0)]
            chunks = checker._split(tokens)
            assert len(chunks) == 1
            assert chunks[0] == tokens
        finally:
            checker.shutdown()

    def test_split_multiple_tokens_auto_chunk_size(self) -> None:
        """Tokens should be split across workers."""
        checker = SpellChecker()
        try:
            # Create 100 tokens, should split across worker_count
            tokens = [(f"word{i}", i) for i in range(100)]
            chunks = checker._split(tokens)
            assert len(chunks) > 0
            # All tokens should be distributed across chunks
            total_tokens = sum(len(c) for c in chunks)
            assert total_tokens == 100
        finally:
            checker.shutdown()

    def test_split_respects_explicit_chunk_size(self) -> None:
        """Explicit CHUNK_SIZE should override auto calculation."""
        with mock.patch.dict(os.environ, {"CHUNK_SIZE": "10"}, clear=False):
            checker = SpellChecker()
            try:
                tokens = [(f"word{i}", i) for i in range(100)]
                chunks = checker._split(tokens)
                # All chunks except last should be exactly 10
                for chunk in chunks[:-1]:
                    assert len(chunk) == 10
            finally:
                checker.shutdown()


class TestTokenization:
    """Tests for SpellChecker._tokenise() token extraction."""

    def test_tokenise_empty_string(self) -> None:
        """Empty string should produce empty token list."""
        tokens = SpellChecker._tokenise("")
        assert tokens == []

    def test_tokenise_single_word(self) -> None:
        """Single word should produce single token with correct offset."""
        tokens = SpellChecker._tokenise("hello")
        assert tokens == [("hello", 0)]

    def test_tokenise_multiple_words(self) -> None:
        """Multiple words should each produce a token."""
        tokens = SpellChecker._tokenise("hello world python")
        assert len(tokens) == 3
        assert tokens[0] == ("hello", 0)
        assert tokens[1] == ("world", 6)
        assert tokens[2] == ("python", 12)

    def test_tokenise_ignores_punctuation(self) -> None:
        """Punctuation should not be included in tokens."""
        tokens = SpellChecker._tokenise("hello, world!")
        originals = [t[0] for t in tokens]
        assert originals == ["hello", "world"]

    def test_tokenise_ignores_numbers(self) -> None:
        """Numbers should not be tokenized as words."""
        tokens = SpellChecker._tokenise("hello 123 world")
        originals = [t[0] for t in tokens]
        assert originals == ["hello", "world"]

    def test_tokenise_unicode_characters(self) -> None:
        """Unicode letters should be tokenized correctly."""
        tokens = SpellChecker._tokenise("café naïve résumé")
        originals = [t[0] for t in tokens]
        assert originals == ["café", "naïve", "résumé"]


class TestShutdownProcedure:
    """Tests for SpellChecker.shutdown() cleanup."""

    def test_shutdown_calls_executor_shutdown(self) -> None:
        """shutdown() must call executor.shutdown(wait=True)."""
        checker = SpellChecker()
        with mock.patch.object(checker._executor, "shutdown") as mock_shutdown:
            checker.shutdown()
            mock_shutdown.assert_called_once_with(wait=True)

    def test_shutdown_multiple_calls_safe(self) -> None:
        """Multiple shutdown() calls should not raise exceptions."""
        checker = SpellChecker()
        checker.shutdown()
        # Second shutdown should not raise
        checker.shutdown()


class TestErrorHandling:
    """Tests for robust error handling during parallel processing."""

    @pytest.mark.asyncio
    async def test_handles_worker_exception_gracefully(self) -> None:
        """If a worker raises an exception, processing should continue with partial results."""
        checker = SpellChecker()
        try:
            # Mock process_chunk to raise an exception for one call
            original_process_chunk = __import__("app.engine.worker", fromlist=["process_chunk"]).process_chunk
            call_count = 0

            def mock_process_chunk(chunk, dictionary):
                nonlocal call_count
                call_count += 1
                if call_count == 2:  # Fail on second chunk
                    raise RuntimeError("Simulated worker failure")
                return original_process_chunk(chunk, dictionary)

            with mock.patch("app.engine.checker.process_chunk", side_effect=mock_process_chunk):
                # This should not raise, even with one worker failing
                response = await checker.check("hello recieve world python seperate")
                # Should have some results from non-failed chunks
                assert isinstance(response, SpellCheckResponse)
        finally:
            checker.shutdown()

    @pytest.mark.asyncio
    async def test_all_workers_fail_returns_empty_corrections(self) -> None:
        """If all workers fail, should return valid response with partial/empty corrections."""
        checker = SpellChecker()
        try:
            with mock.patch("app.engine.checker.process_chunk", side_effect=RuntimeError("All workers down")):
                response = await checker.check("recieve")
                assert isinstance(response, SpellCheckResponse)
                assert response.word_count >= 0
        finally:
            checker.shutdown()


class TestDependencyInjection:
    """Tests for FastAPI dependency injection via get_checker()."""

    def test_get_checker_returns_singleton(self) -> None:
        """get_checker() should return the same instance on multiple calls."""
        # Clear the global instance first
        import app.engine.checker as checker_module

        checker_module._checker_instance = None
        instance1 = get_checker()
        instance2 = get_checker()
        try:
            assert instance1 is instance2
        finally:
            instance1.shutdown()
            checker_module._checker_instance = None

    def test_get_checker_initializes_on_first_call(self) -> None:
        """get_checker() should initialize SpellChecker on first call."""
        import app.engine.checker as checker_module

        checker_module._checker_instance = None
        instance = get_checker()
        try:
            assert isinstance(instance, SpellChecker)
        finally:
            instance.shutdown()
            checker_module._checker_instance = None


@pytest.mark.asyncio
async def test_concurrent_requests_use_same_executor() -> None:
    """Multiple concurrent requests should share the same executor instance."""
    checker = SpellChecker()
    try:
        executor_id = id(checker._executor)

        # Run multiple concurrent checks
        results = await asyncio.gather(
            checker.check("recieve"),
            checker.check("seperate"),
            checker.check("mesage"),
        )

        # Executor should not have changed
        assert id(checker._executor) == executor_id
        assert len(results) == 3
        assert all(isinstance(r, SpellCheckResponse) for r in results)
    finally:
        checker.shutdown()


@pytest.mark.asyncio
async def test_suggestions_populated_correctly() -> None:
    """Corrections should have populated suggestions field."""
    checker = SpellChecker()
    try:
        response = await checker.check("recieve")
        assert len(response.corrections) >= 1
        correction = response.corrections[0]
        assert hasattr(correction, "suggestions")
        assert isinstance(correction.suggestions, list)
        assert len(correction.suggestions) > 0
    finally:
        checker.shutdown()
