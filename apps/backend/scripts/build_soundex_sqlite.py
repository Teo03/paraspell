"""Build the SQLite Soundex mapping table for ParaSpell (Part 2).

Twin of ``build_dict.py``. Reads the already-built ``words.marisa``
(canonical word source — guarantees the SQLite rows mirror the trie
exactly) and writes ``app/data/soundex.sqlite`` with one row per
``(soundex_code, word)`` pair.

Why a separate script (not folded into ``build_dict.py``)
---------------------------------------------------------
* Single responsibility — ``build_dict.py`` owns *what words exist*,
  this one owns *how words are phonetically grouped*.
* The Soundex algorithm or its index format may evolve independently
  of the word list (the Strategy comment in ``dictionary.py``).
* Re-running this script is cheap (~1 s) and doesn't require a network
  round-trip the way re-downloading the dwyl source would.

Schema
------
    CREATE TABLE soundex_words (
        code TEXT NOT NULL,
        word TEXT NOT NULL,
        PRIMARY KEY (code, word)
    ) WITHOUT ROWID;

* ``WITHOUT ROWID`` stores rows in the PK B-tree directly — saves ~30 %
  on disk for narrow rows like ours and removes one indirection per
  lookup (the production hot path is ``WHERE code = ?``).
* The composite PK ``(code, word)`` doubles as the lookup index — no
  separate ``CREATE INDEX`` needed; SQLite will range-scan on the
  leading column.

Run
---
From repo root, after ``words.marisa`` exists::

    python apps/backend/scripts/build_soundex_sqlite.py

Idempotent — destroys and rebuilds the SQLite file each invocation so
re-runs are deterministic and the on-disk size doesn't grow over time.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import marisa_trie


# Make ``app.engine.dictionary.soundex`` importable when the script is run
# as ``python apps/backend/scripts/build_soundex_sqlite.py`` from the repo
# root. Adding the backend root puts ``app/`` on sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.engine.dictionary import soundex  # noqa: E402  (after sys.path tweak)
from build_freq import load_frequencies  # noqa: E402  (sibling script)


DEFAULT_TRIE_PATH = _BACKEND_ROOT / "app" / "data" / "words.marisa"
DEFAULT_DB_PATH = _BACKEND_ROOT / "app" / "data" / "soundex.sqlite"

# Sanity bounds — same logic as build_dict.py: protect against committing
# a truncated build (e.g. partial trie load, IO error mid-stream).
MIN_EXPECTED_ROWS = 350_000
MAX_EXPECTED_ROWS = 400_000

# Schema v2 adds the ``frequency`` column. The runtime reads it via
# ``Dictionary.soundex_candidates`` and blends it into the ranking score
# (see ``worker._rank_suggestions``). Words not present in the frequency
# source default to 0 — the score-blend formula degrades cleanly: a
# zero-frequency candidate contributes no boost, falling back to pure
# Levenshtein ranking.
DDL = """
CREATE TABLE soundex_words (
    code      TEXT    NOT NULL,
    word      TEXT    NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (code, word)
) WITHOUT ROWID;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


logger = logging.getLogger("build_soundex_sqlite")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def load_trie(path: Path) -> marisa_trie.Trie:
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Run `python apps/backend/scripts/build_dict.py` "
            "first to produce the MARISA-trie."
        )
    trie = marisa_trie.Trie()
    trie.load(str(path))
    logger.info("loaded %s (%d keys)", path, len(trie))
    return trie


def build_rows(
    trie: marisa_trie.Trie,
    freqs: dict[str, int],
) -> list[tuple[str, str, int]]:
    """Compute ``(code, word, frequency)`` triples for every key in *trie*.

    Skips words whose Soundex code is empty (e.g. all-vowel inputs that
    jellyfish refuses) — these are unreachable from the worker's lookup
    anyway, so storing them would waste rows and slow lookups.

    Frequency defaults to 0 when the word is not in *freqs*. That's a
    common case: dwyl has many rare words Norvig's web corpus never sees.
    The score-blend formula treats freq=0 as "no boost", so the row is
    still findable; it just won't beat a more-common neighbour on ties.
    """
    rows: list[tuple[str, str, int]] = []
    skipped = 0
    matched = 0
    for w in trie.keys():
        code = soundex(w)
        if not code:
            skipped += 1
            continue
        freq = freqs.get(w, 0)
        if freq:
            matched += 1
        rows.append((code, w, freq))
    if skipped:
        logger.info("skipped %d words with empty soundex codes", skipped)
    logger.info(
        "frequency coverage: %d / %d words matched (%.1f%%)",
        matched,
        len(rows),
        100.0 * matched / max(len(rows), 1),
    )
    return rows


def populate(db_path: Path, rows: list[tuple[str, str, int]]) -> None:
    """Create the SQLite file fresh and bulk-insert *rows*."""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        # Bulk-insert pragmas — safe because this is a one-shot build, not
        # a live database. Every flag here is reset by closing the conn.
        conn.executescript("""
            PRAGMA journal_mode = MEMORY;
            PRAGMA synchronous  = OFF;
            PRAGMA temp_store   = MEMORY;
            PRAGMA cache_size   = -64000;   -- 64 MB page cache for the build
        """)
        conn.executescript(DDL)

        with conn:  # implicit transaction
            conn.executemany(
                "INSERT INTO soundex_words(code, word, frequency) VALUES (?, ?, ?)",
                rows,
            )

            # Distinct count is cheap on the data we just inserted; storing
            # it in `meta` avoids a SELECT COUNT(DISTINCT code) at runtime.
            distinct_codes = len({code for code, _, _ in rows})
            meta = [
                ("schema_version", "2"),
                ("source_trie", DEFAULT_TRIE_PATH.name),
                ("word_count", str(len(rows))),
                ("code_count", str(distinct_codes)),
                ("built_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ]
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                meta,
            )

        # ANALYZE so the query planner has stats; VACUUM compacts the file
        # to its final stable size (commit-friendly diffs).
        conn.execute("ANALYZE")
        conn.execute("VACUUM")
    finally:
        conn.close()

    logger.info(
        "wrote %s (%.1f KB, %d rows, %d codes)",
        db_path,
        db_path.stat().st_size / 1024,
        len(rows),
        distinct_codes,
    )


# ---------------------------------------------------------------------------
# Smoke probes — surface a regression before the file ships
# ---------------------------------------------------------------------------

def smoke_probe(db_path: Path) -> None:
    """Open the freshly built DB read-only and run a few sanity queries."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Row count within expected range.
        (count,) = conn.execute("SELECT COUNT(*) FROM soundex_words").fetchone()
        if not (MIN_EXPECTED_ROWS <= count <= MAX_EXPECTED_ROWS):
            raise RuntimeError(
                f"row count {count:,} outside expected "
                f"[{MIN_EXPECTED_ROWS:,}, {MAX_EXPECTED_ROWS:,}]."
            )

        # Known phonetic equivalence classes from Part 2's algorithm tests.
        for query, must_contain in (
            ("R210", ("receive", "recipe")),                # 'recieve' typo class
            ("S163", ("separate",)),                        # 'seperate' typo class
            ("D153", ("definitely",)),                      # 'definately' typo class
            ("W643", ("world",)),                           # 'worlld' typo class
        ):
            words = {
                w for (w,) in conn.execute(
                    "SELECT word FROM soundex_words WHERE code = ?", (query,)
                )
            }
            for w in must_contain:
                if w not in words:
                    raise RuntimeError(
                        f"smoke probe failed: {w!r} missing from bucket {query}"
                    )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--trie",
        type=Path,
        default=DEFAULT_TRIE_PATH,
        help="Source MARISA-trie file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Output SQLite file.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    trie = load_trie(args.trie)
    freqs = load_frequencies()
    logger.info("loaded %d frequency entries", len(freqs))
    rows = build_rows(trie, freqs)

    if not (MIN_EXPECTED_ROWS <= len(rows) <= MAX_EXPECTED_ROWS):
        raise RuntimeError(
            f"row count {len(rows):,} outside expected "
            f"[{MIN_EXPECTED_ROWS:,}, {MAX_EXPECTED_ROWS:,}]. Aborting."
        )

    populate(args.out, rows)
    smoke_probe(args.out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
