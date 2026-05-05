"""Dictionary loader (NFR-12 / engine layer).

Owns three things, all read-only after construction:

  1. ``_words``   — ``marisa_trie.Trie`` of the 370 k reference words
                    (membership: O(len(w)), ~1 MB on disk, mmap'd).
  2. ``_db_path`` — Path to the prebuilt ``soundex.sqlite`` mapping table
                    (one row per (code, word) pair, see scripts/
                    build_soundex_sqlite.py).
  3. ``_cache``   — per-process LRU cache of (code → tuple[str, ...]),
                    populated lazily on the first lookup of each code.

Why SQLite instead of a Python dict
-----------------------------------
The earlier in-memory dict version was fine but eagerly materialised the
entire ~370 k-row mapping in every forked worker's address space. Switching
to SQLite (build artifact) + LRU cache (runtime) means:

  * the on-disk mapping is portable and inspectable (``sqlite3 soundex.sqlite``);
  * each worker only pages in the soundex codes it actually queries;
  * the working set adapts to input — a request that touches 200 typos
    pulls ~200 buckets into the cache, not all 5,957;
  * the mapping is decoupled from the algorithm — a future Metaphone
    backend can just point at a different SQLite file.

Hybrid model — boot-time validation, lazy connection, LRU cache
---------------------------------------------------------------
* ``__init__`` validates that the trie + SQLite files exist but does NOT
  open a SQLite connection. SQLite connections are not fork-safe — they
  carry file descriptors and an in-memory state machine that gets shared
  rather than duplicated when ``ProcessPoolExecutor`` forks.
* ``_get_conn()`` opens (and caches) a connection per *process*, keyed by
  ``os.getpid()``. After fork, child processes detect the PID change and
  open their own.
* ``soundex_candidates(word)`` is wrapped by an LRU on the *code*, not the
  word — many misspellings collapse to the same code (the whole point of
  Soundex), so the cache hits often even on cold input.

Design pattern note
-------------------
* **Strategy** — the phonetic match is a swappable strategy. Drop in a
  new soundex.sqlite (built by a different ``build_soundex_*.py``) and
  the worker code is unchanged.
* **Repository / Facade** — Dictionary is the engine's single import
  point for "anything word-list shaped" (NFR-12).
* **Lazy initialization** — the SQLite connection is created on demand
  per process to keep fork-safety guarantees.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import jellyfish
import marisa_trie
from rapidfuzz.distance import Levenshtein as _Levenshtein


logger = logging.getLogger(__name__)


# Default locations. Resolved relative to this file so ``Dictionary()`` works
# the same in tests, ``python -m app.main``, and the Docker image.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_TRIE_PATH = _DATA_DIR / "words.marisa"
_DEFAULT_DB_PATH = _DATA_DIR / "soundex.sqlite"

# LRU cache size — number of distinct soundex codes whose candidate lists
# are kept hot per worker. The full universe is ~6 k codes; 1 024 covers
# the vast majority of real English text (common consonant skeletons
# appear repeatedly). Tunable via SOUNDEX_CACHE_SIZE so the Part 3
# benchmark task can sweep this.
_DEFAULT_CACHE_SIZE = int(os.getenv("SOUNDEX_CACHE_SIZE", "1024"))

# Maximum edit distance used by get_candidates() for candidate filtering and
# ranking. Mirrors the same env var read by worker.py so both layers are
# configured identically from .env.
_MAX_EDIT_DISTANCE: int = int(os.getenv("MAX_EDIT_DISTANCE", "3"))


def soundex(word: str) -> str:
    """Return the American Soundex code for *word* (4 chars, uppercase).

    Thin wrapper around ``jellyfish.soundex`` — the C implementation of
    the Russell/Odell algorithm:

      1. keep the first letter
      2. drop a/e/i/o/u/y/h/w
      3. map remaining consonants → digits
      4. collapse adjacent duplicates
      5. pad with ``0`` (or truncate) to exactly 4 chars

    Module-level so the build script and the runtime use byte-identical
    normalisation. Empty / non-alpha / unfoldable input → ``""``.
    """
    if not word:
        return ""
    try:
        return jellyfish.soundex(word)
    except (ValueError, UnicodeError):
        return ""


class Dictionary:
    """In-memory MARISA-trie + SQLite-backed Soundex mapping.

    Public contract:
        lookup(word)                     -> bool
        get_candidates(word, top_n)      -> list[str]   (ranked)
        contains(word)                   -> bool        (lower-level alias)
        soundex_candidates(word)         -> list[str]   (unranked bucket)
        __len__()                        -> int
        iter_words()                     -> Iterable[str]
        close()                          -> None
    """

    def __init__(
        self,
        trie_path: str | os.PathLike[str] | None = None,
        db_path: str | os.PathLike[str] | None = None,
        cache_size: int | None = None,
    ) -> None:
        self._trie_path = self._resolve_path(trie_path, "DICT_PATH", _DEFAULT_TRIE_PATH)
        self._db_path = self._resolve_path(db_path, "SOUNDEX_DB_PATH", _DEFAULT_DB_PATH)

        self._words: marisa_trie.Trie = self._load_trie(self._trie_path)
        self._validate_db(self._db_path)

        # Per-process state — re-created lazily after fork. ``_conn_pid``
        # carries the PID that opened ``_conn``; if it ever differs from
        # ``os.getpid()`` we close + reopen.
        self._conn: sqlite3.Connection | None = None
        self._conn_pid: int | None = None

        # Build the per-instance LRU. Wrapping ``_fetch_bucket`` at __init__
        # gives us a fresh cache per Dictionary instance (avoids cross-test
        # pollution) and the right scoping after fork — children inherit
        # the parent's cache contents via COW, then diverge as they query.
        cache_size = cache_size if cache_size is not None else _DEFAULT_CACHE_SIZE
        self._cache_size = cache_size
        self._fetch_bucket = lru_cache(maxsize=cache_size)(self._fetch_bucket_uncached)

        logger.info(
            "Dictionary ready: %d trie keys, soundex db=%s, cache=%d",
            len(self._words),
            self._db_path,
            cache_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def contains(self, word: str) -> bool:
        """Return True if *word* (case-insensitive) is in the dictionary."""
        if not word:
            return False
        return word.lower() in self._words


    def lookup(self, word: str) -> bool:
        """Return ``True`` if *word* is a correctly spelled dictionary word.

        This is the primary membership check for callers that don't need to
        know about the underlying trie implementation.  Semantically identical
        to ``contains()`` — prefer ``lookup`` at call sites in routers and
        tests; prefer ``contains`` inside engine internals where the trie
        context is already established.

        Parameters
        ----------
        word:
            Surface form as typed by the user.  Case-insensitive.

        Returns
        -------
        bool
            ``True`` if *word* exists in the 370 k-word reference list.
        """
        return self.contains(word)

    def soundex_candidates(self, word: str) -> list[str]:
        """Return every dictionary word that shares *word*'s Soundex code.

        Cache key is the *code*, not the word — `recieve`, `recieved`, and
        `reseive` all collapse to ``R210`` and share a single cache entry.
        Returns a fresh list (not the cached tuple) so callers can mutate
        / sort without poisoning the cache.
        """
        code = soundex(word)
        if not code:
            return []
        return list(self._fetch_bucket(code))


    def get_candidates(self, word: str, top_n: int) -> list[str]:
        """Return the top-*n* ranked correction candidates for *word*.

        This is the high-level lookup method that the engine and tests
        should use in preference to calling ``soundex_candidates`` and
        running Levenshtein manually.

        Pipeline
        --------
        1. **Soundex filter** — fetches every dictionary word that shares
           *word*\'s Soundex code (O(1) LRU hit after the first query for
           a given code; O(SQL) on a miss).
        2. **Length pre-filter** — drops candidates where
           ``|len(candidate) - len(word)| > MAX_EDIT_DISTANCE``  (no C call,
           no allocation — just integer arithmetic).
        3. **Levenshtein ranking** — scores surviving candidates with
           ``rapidfuzz`` (C extension, GIL-released).  Uses ``score_cutoff``
           so rapidfuzz bails out early for distant pairs.
        4. **Top-N slice** — returns at most *top_n* words, best match first.

        The ranking formula ``1 - dist / max(len(query), len(candidate))``
        maps edit distance to a [0, 1] similarity score that matches the
        ``Suggestion.score`` field in the API schema — zero extra work for
        the router layer.

        Parameters
        ----------
        word:
            The misspelled word to find corrections for.  May be mixed-case;
            comparison is always lowercased.
        top_n:
            Maximum number of candidates to return.  Pass
            ``int(os.getenv("MAX_SUGGESTIONS", "5"))`` at call sites that
            want to respect the SRS UC-03 / §5.2.4 limit.

        Returns
        -------
        list[str]
            Up to *top_n* correctly spelled words ordered best-first.
            Empty list when the Soundex bucket is empty or no candidate
            survives the distance filter.
        """
        if top_n <= 0:
            return []

        query = word.lower()
        pool = self.soundex_candidates(query)
        if not pool:
            return []

        qlen = len(query)
        scored: list[tuple[float, int, str]] = []  # (score, dist, word)

        for candidate in pool:
            # Cheap length pre-filter — no allocation, no C call.
            if abs(len(candidate) - qlen) > _MAX_EDIT_DISTANCE:
                continue

            # score_cutoff lets rapidfuzz bail out early once distance
            # exceeds the threshold, saving cycles on large buckets.
            dist = _Levenshtein.distance(
                query, candidate, score_cutoff=_MAX_EDIT_DISTANCE
            )
            if dist > _MAX_EDIT_DISTANCE:
                continue

            score = 1.0 - dist / max(qlen, len(candidate))
            scored.append((score, dist, candidate))

        # Highest score first; tie-break on shorter distance then
        # alphabetical order (bucket is pre-sorted by SQL, so stable).
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        return [cand for _, _, cand in scored[:top_n]]

    def __len__(self) -> int:
        return len(self._words)

    def __contains__(self, word: object) -> bool:
        return isinstance(word, str) and self.contains(word)

    def iter_words(self) -> Iterable[str]:
        """Iterate every key in the trie."""
        return iter(self._words.keys())

    def cache_info(self) -> dict[str, int]:
        """Return LRU cache stats — useful for the benchmark task."""
        info = self._fetch_bucket.cache_info()
        return {
            "hits": info.hits,
            "misses": info.misses,
            "maxsize": info.maxsize,
            "currsize": info.currsize,
        }

    def close(self) -> None:
        """Close the SQLite connection (idempotent)."""
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                self._conn_pid = None

    # ------------------------------------------------------------------
    # Pickling
    # ------------------------------------------------------------------
    #
    # ``ProcessPoolExecutor.submit(fn, ..., dictionary)`` pickles every
    # argument and ships it through a queue, even with the ``fork`` start
    # method. The bound ``functools.lru_cache`` wrapper and the live
    # ``sqlite3.Connection`` are not picklable, and *should not* be — the
    # cache is per-process and the connection carries an FD that musn't
    # cross processes. On restore in the child we re-load the trie (mmap,
    # cheap if the file is in the page cache from the parent's load) and
    # rebuild a fresh LRU. The connection stays lazy.
    #
    # NB. For high-throughput parallel use the better pattern is the
    # ``initializer`` arg of ``ProcessPoolExecutor``: build Dictionary
    # once per worker at pool startup and stash it in a module-global,
    # so the work function is just ``def task(chunk):`` — no
    # per-submit pickle round-trip. This pickle path is the safety net.

    def __getstate__(self) -> dict[str, object]:
        return {
            "trie_path": str(self._trie_path),
            "db_path": str(self._db_path),
            "cache_size": self._cache_size,
        }

    def __setstate__(self, state: dict[str, object]) -> None:
        self._trie_path = Path(state["trie_path"])  # type: ignore[arg-type]
        self._db_path = Path(state["db_path"])  # type: ignore[arg-type]
        self._cache_size = int(state["cache_size"])  # type: ignore[arg-type]
        self._words = self._load_trie(self._trie_path)
        self._validate_db(self._db_path)
        self._conn = None
        self._conn_pid = None
        self._fetch_bucket = lru_cache(maxsize=self._cache_size)(
            self._fetch_bucket_uncached
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(
        explicit: str | os.PathLike[str] | None,
        env_var: str,
        default: Path,
    ) -> Path:
        if explicit is not None:
            return Path(explicit)
        env_path = os.getenv(env_var)
        if env_path:
            return Path(env_path)
        return default

    @staticmethod
    def _load_trie(path: Path) -> marisa_trie.Trie:
        if not path.is_file():
            raise FileNotFoundError(
                f"MARISA-trie file not found at {path}. "
                "Run `python apps/backend/scripts/build_dict.py` to generate it."
            )
        trie = marisa_trie.Trie()
        trie.load(str(path))
        return trie

    @staticmethod
    def _validate_db(path: Path) -> None:
        """Confirm the SQLite file exists and has the expected schema.

        Just a stat + light-weight ``SELECT name FROM sqlite_master`` —
        full row-count checks belong in the build script's smoke probe.
        We only want to fail fast at startup if a deploy is missing the
        artifact, rather than waiting for the first misspelling.
        """
        if not path.is_file():
            raise FileNotFoundError(
                f"Soundex SQLite file not found at {path}. "
                "Run `python apps/backend/scripts/build_soundex_sqlite.py` to "
                "generate it."
            )
        # Read-only validation; closes immediately. Connection is reopened
        # per worker post-fork in ``_get_conn``.
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='soundex_words'"
            ).fetchone()
            if row is None:
                raise RuntimeError(
                    f"{path} does not contain table 'soundex_words'. "
                    "Rebuild it with build_soundex_sqlite.py."
                )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Per-process SQLite connection (fork-safe)
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return a connection scoped to the *current* process.

        Detects fork by comparing ``os.getpid()`` with the PID that
        opened the cached connection. If they differ, we close the
        inherited handle (it shouldn't be used in this process) and
        open a fresh one.

        ``check_same_thread=False`` is safe here because the engine's
        threading model is process-based: each worker is single-threaded
        within itself, and the connection is private to that process.
        """
        pid = os.getpid()
        if self._conn is None or self._conn_pid != pid:
            if self._conn is not None:
                # Inherited from the parent — drop it without ``close()``,
                # which would fsync against a shared FD.
                self._conn = None
            uri = f"file:{self._db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            # Read-only access pattern → these pragmas trade nothing.
            self._conn.execute("PRAGMA query_only = ON")
            self._conn.execute("PRAGMA temp_store = MEMORY")
            self._conn_pid = pid
        return self._conn

    def _fetch_bucket_uncached(self, code: str) -> tuple[str, ...]:
        """Run the SQL ``WHERE code = ?`` lookup. Cached by ``_fetch_bucket``.

        Returns a tuple (immutable) — the LRU stores it directly and
        ``soundex_candidates`` makes a fresh ``list`` for the caller.
        Sorted in SQL so output ordering is deterministic across machines
        (matches the alphabetic order the in-memory version produced, so
        existing test fixtures keep working).
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT word FROM soundex_words WHERE code = ? ORDER BY word",
            (code,),
        ).fetchall()
        return tuple(w for (w,) in rows)
