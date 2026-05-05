"""Shared pytest fixtures for the backend test suite.

Two responsibilities:

1. **sys.path** — the CI command is ``pytest apps/backend`` run from the
   repo root, so ``app/`` isn't on the import path by default. We
   prepend the backend directory here so every test can do
   ``from app.engine.dictionary import Dictionary`` directly.

2. **Shared Dictionary instance** — loading the 370 k-word trie and
   validating the SQLite mapping costs ~5–100 ms per call. Most tests
   only need read-only access, so a single ``session``-scoped instance
   is shared. Tests that exercise mutable state (LRU eviction, pickle)
   build their own short-lived instance via ``Dictionary(...)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# sys.path bootstrap — make ``app.*`` importable when pytest is invoked
# from the repo root (``pytest apps/backend``).
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def dictionary():
    """One Dictionary instance shared across the whole test session.

    Reads the committed ``words.marisa`` and ``soundex.sqlite`` artifacts.
    Read-only — never mutate state on this instance; ask for a fresh one
    if you need a clean LRU or to point at non-default paths.
    """
    from app.engine.dictionary import Dictionary

    d = Dictionary()
    yield d
    d.close()
