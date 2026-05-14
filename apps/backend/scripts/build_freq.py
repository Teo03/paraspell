"""Load word-frequency data for ParaSpell ranking (Part 2 augmentation).

This module owns the *frequency* data that the ranking pipeline blends into
its score (see ``app.engine.worker._rank_suggestions``). It's a peer to
``build_dict.py`` and ``build_soundex_sqlite.py``: those decide *which words
exist* and *which words share a Soundex bucket*; this one decides *how
common each word is in real English text*.

Source
------
Peter Norvig's ``count_1w.txt`` from norvig.com/ngrams — 333 333 lowercase
ASCII words with Google Web 1T n-gram counts. Single text file, one
``word\\tcount`` line per word, ~5 MB, public-domain redistribution of the
LDC release. Same vintage as the wordfreq library's web component, but
self-contained: we download once at build time, parse once, then ship the
counts inside the existing ``soundex.sqlite`` artifact. No new runtime
dependency.

Why Norvig and not (Wikipedia, books, COCA, …)
----------------------------------------------
* It's a *single file* with a stable URL — fits the same "cache + parse"
  pattern as the dwyl word list, no corpus pre-processing pipeline.
* Coverage is wide enough that almost every dwyl word has a non-zero count,
  which is what the score-blend formula needs (zero-frequency candidates
  fall back to pure edit-distance ranking — fine, but loses the win).
* Tradeoff acknowledged: web counts include typo-as-token entries, so
  e.g. ``untill`` has a non-trivial count. That's why ranking uses
  frequency as a *boost* (not absolute truth) and dictionary filtering
  uses an explicit blocklist (this script does *not* filter dwyl — that's
  ``build_dict.py``'s job, via ``dict_blocklist.txt``).

Run
---
This module is library-shaped; call ``load_frequencies()`` from another
build script. The CLI entrypoint just prints a small summary, useful when
debugging the cache file:

    python apps/backend/scripts/build_freq.py
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path


# Norvig publishes the file at this stable URL and has done so since at
# least 2008; it's referenced in his "Beautiful Data" chapter on spelling.
FREQ_URL = "https://norvig.com/ngrams/count_1w.txt"

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = _BACKEND_ROOT / "scripts" / "count_1w.txt"

# Sanity bounds — protect against silently shipping a truncated download.
# Norvig's file has 333 333 entries; allow some wiggle if the source ever
# updates within the same order of magnitude.
MIN_EXPECTED_ENTRIES = 300_000
MAX_EXPECTED_ENTRIES = 400_000


logger = logging.getLogger("build_freq")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_frequencies(
    cache_path: Path = DEFAULT_CACHE_PATH,
    url: str = FREQ_URL,
    force_download: bool = False,
) -> dict[str, int]:
    """Return ``{word: count}`` mapping from Norvig's count_1w.txt.

    Downloads the source on first call (or when *force_download* is True)
    and caches it at *cache_path* — same pattern ``build_dict.py`` uses
    for the dwyl word list. Re-runs read from the cached file (fast).

    The returned dict is keyed by lowercase ASCII word; lookups must
    lowercase the input the same way ``build_dict.py`` normalises words
    so the two artifacts stay in sync.
    """
    _ensure_cached(cache_path, url, force_download)
    return _parse(cache_path)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def _ensure_cached(cache_path: Path, url: str, force_download: bool) -> None:
    if cache_path.exists() and not force_download:
        logger.info("frequency file already cached at %s", cache_path)
        return

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading frequency data from %s", url)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 — fixed URL
        data = resp.read()
    cache_path.write_bytes(data)
    logger.info("wrote %d bytes to %s", len(data), cache_path)


def _parse(cache_path: Path) -> dict[str, int]:
    """Parse ``word\\tcount`` lines into a dict.

    Skips blank / malformed lines silently — the upstream file is clean,
    but defensively handling the rare empty trailing newline costs nothing.
    """
    freqs: dict[str, int] = {}
    with cache_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            word, count = parts
            if not word:
                continue
            try:
                freqs[word.lower()] = int(count)
            except ValueError:
                continue

    if not (MIN_EXPECTED_ENTRIES <= len(freqs) <= MAX_EXPECTED_ENTRIES):
        raise RuntimeError(
            f"frequency entry count {len(freqs):,} outside expected "
            f"[{MIN_EXPECTED_ENTRIES:,}, {MAX_EXPECTED_ENTRIES:,}]. "
            "The source may have changed; review before committing."
        )

    return freqs


# ---------------------------------------------------------------------------
# CLI — debug/inspection helper
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Path to the cached count_1w.txt.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download even if the cache is present.",
    )
    parser.add_argument(
        "--probe",
        nargs="*",
        default=("the", "their", "thier", "smal", "small", "recieve", "receive"),
        help="Words to print frequencies for (for sanity-checking the build).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    freqs = load_frequencies(args.cache, force_download=args.force_download)
    logger.info("loaded %d frequency entries", len(freqs))
    for word in args.probe:
        logger.info("  %-12s -> %s", word, f"{freqs.get(word, 0):,}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
