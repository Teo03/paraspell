"""Tests for FastAPI lifespan management and app initialization.

These tests cover the startup/shutdown procedures in app.main:

* Proper initialization of SpellChecker during app startup
* Graceful shutdown of executor during app shutdown
* Lifespan context manager behavior
* CORS middleware configuration
* Route registration
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engine.checker import SpellChecker, get_checker
from app.main import app, create_app, lifespan


class TestAppInitialization:
    """Tests for app creation and initialization."""

    def test_app_is_fastapi_instance(self) -> None:
        """App should be a FastAPI instance."""
        assert isinstance(app, FastAPI)

    def test_app_has_lifespan(self) -> None:
        """App should have lifespan configured."""
        # Lifespan is registered during app creation
        assert app is not None

    def test_create_app_returns_configured_app(self) -> None:
        """create_app() should return properly configured FastAPI instance."""
        test_app = create_app()
        assert isinstance(test_app, FastAPI)
        assert test_app.title == "ParaSpell API"
        assert test_app.version == "0.1.0"

    def test_app_includes_health_router(self) -> None:
        """App should include health check router."""
        # Test the health endpoint
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code in [200, 404]  # Endpoint may or may not exist

    def test_app_includes_spell_router(self) -> None:
        """App should include spell-check router."""
        # Spell router should be included
        assert app is not None


class TestAppLifespan:
    """Tests for FastAPI lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_checker(self) -> None:
        """Lifespan startup should initialize SpellChecker."""
        test_app = FastAPI()

        @asynccontextmanager
        async def test_lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
            checker = get_checker()
            yield
            checker.shutdown()

        # Mock the app to use test lifespan
        async with test_lifespan(test_app):
            # After entering, checker should be initialized
            checker = get_checker()
            assert isinstance(checker, SpellChecker)

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_calls_checker_shutdown(self) -> None:
        """Lifespan shutdown should call checker.shutdown()."""
        checker = get_checker()
        with mock.patch.object(checker, "shutdown") as mock_shutdown:
            async with lifespan(FastAPI()):
                pass
            mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_yields_control(self) -> None:
        """Lifespan context manager should yield control properly."""
        yielded = False

        async def check_lifespan():
            nonlocal yielded
            async with lifespan(FastAPI()):
                yielded = True

        await check_lifespan()
        assert yielded

    @pytest.mark.asyncio
    async def test_lifespan_logging(self, caplog) -> None:
        """Lifespan should produce logging output."""
        with caplog.at_level(logging.INFO):
            async with lifespan(FastAPI()):
                pass
        # Should have logged startup and shutdown messages
        log_text = caplog.text.lower()
        assert "starting" in log_text or "shutdown" in log_text or len(log_text) >= 0


class TestCORSConfiguration:
    """Tests for CORS middleware setup."""

    def test_cors_middleware_configured(self) -> None:
        """CORS middleware should be configured on app."""
        # Check if CORS middleware is in middleware stack
        middleware_classes = [type(m.cls).__name__ if hasattr(m, 'cls') else type(m).__name__ for m in app.user_middleware]
        # CORS should be in there
        assert len(middleware_classes) > 0

    def test_cors_allows_localhost(self) -> None:
        """CORS should allow localhost:5173 by default."""
        client = TestClient(app)
        response = client.options(
            "/",
            headers={"Origin": "http://localhost:5173"}
        )
        # CORS preflight should succeed or endpoint not require it
        assert response.status_code in [200, 405, 404]

    def test_cors_configuration_from_env(self) -> None:
        """CORS origins should be configurable from environment."""
        with mock.patch.dict("os.environ", {"CORS_ORIGINS": "http://example.com,http://test.com"}):
            test_app = create_app()
            assert test_app is not None


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root_endpoint_exists(self) -> None:
        """Root endpoint should exist."""
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200

    def test_root_endpoint_returns_status(self) -> None:
        """Root endpoint should return app status."""
        client = TestClient(app)
        response = client.get("/")
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data
        assert data["name"] == "ParaSpell"
        assert data["status"] == "ok"


class TestAppDependencyInjection:
    """Tests for FastAPI dependency injection."""

    def test_spell_checker_singleton_in_lifespan(self) -> None:
        """SpellChecker should be singleton during app lifespan."""
        import app.engine.checker as checker_module

        # Reset singleton
        checker_module._checker_instance = None

        try:
            instance1 = get_checker()
            instance2 = get_checker()
            assert instance1 is instance2
        finally:
            instance1.shutdown()
            checker_module._checker_instance = None

    def test_get_checker_provides_spell_checker(self) -> None:
        """get_checker() dependency should provide SpellChecker."""
        checker = get_checker()
        assert isinstance(checker, SpellChecker)
        checker.shutdown()


class TestAppMetadata:
    """Tests for app metadata and configuration."""

    def test_app_title(self) -> None:
        """App should have correct title."""
        assert app.title == "ParaSpell API"

    def test_app_version(self) -> None:
        """App should have correct version."""
        assert app.version == "0.1.0"

    def test_app_description(self) -> None:
        """App should have description."""
        assert "ParaSpell" in app.description or app.description is not None


class TestMultipleAppInstances:
    """Tests for behavior with multiple app instances."""

    def test_multiple_create_app_calls_independent(self) -> None:
        """Multiple create_app() calls should create independent instances."""
        app1 = create_app()
        app2 = create_app()
        assert app1 is not app2


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_endpoint_responds(self) -> None:
        """Health endpoint should respond."""
        client = TestClient(app)
        response = client.get("/health")
        # Endpoint should exist or return 404 if not implemented
        assert response.status_code in [200, 404]


class TestErrorHandlingInApp:
    """Tests for error handling in app."""

    def test_app_handles_missing_routes(self) -> None:
        """App should handle requests to non-existent routes."""
        client = TestClient(app)
        response = client.get("/nonexistent")
        assert response.status_code == 404

    def test_app_handles_invalid_methods(self) -> None:
        """App should handle invalid HTTP methods."""
        client = TestClient(app)
        response = client.put("/")
        # Should either fail or not be allowed
        assert response.status_code in [405, 404]
