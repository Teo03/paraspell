"""Build the MARISA-trie reference dictionary for ParaSpell (Part 2).

This script ingests a raw English word list, normalises it, and serialises
the result as a ``marisa_trie.Trie`` to ``app/data/words.marisa``. The trie
is the on-disk artifact every spell-check worker memory-maps at startup
(see SRS NFR-12 — single load contract).

Source
------
Default source is the public ``dwyl/english-words`` repository's
``words_alpha.txt`` (~370 099 lowercase ASCII words, no punctuation, no
Unicode), which matches the 370k figure cited in Petrushevski & Zdraveski
(ICAI'25) and quoted throughout the SRS / README.

Run
---
From repo root::

    python apps/backend/scripts/build_dict.py

Idempotent: re-running re-downloads only if the cached raw list is missing,
then rebuilds the trie deterministically. Commit the resulting
``words.marisa`` so production images don't need network at build time.

Why MARISA over a Python ``set``
--------------------------------
* ~10x smaller resident size — important because every worker process holds
  its own copy after fork (NFR-13, .env.example WORKER_COUNT note).
* Keys are stored once, shared across processes via mmap (Linux COW).
* O(len(word)) membership checks, identical Big-O to set but with a much
  smaller constant on cache-cold lookups.
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path

import marisa_trie


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# dwyl/english-words is MIT-licensed and ships words_alpha.txt as the
# "alphabetic only" subset — exactly the input the Soundex / Levenshtein
# pipelines expect (see app/engine/checker.py).
WORDLIST_URL = (
    "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
)

# Repo-relative paths. The script lives at apps/backend/scripts/, so the
# backend root is one directory up.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_PATH = BACKEND_ROOT / "scripts" / "words_alpha.txt"
DEFAULT_OUT_PATH = BACKEND_ROOT / "app" / "data" / "words.marisa"
DEFAULT_BLOCKLIST_PATH = BACKEND_ROOT / "scripts" / "dict_blocklist.txt"

# Sanity bounds for the normalised word list — protects against silently
# committing a truncated or corrupted dictionary. Blocklist removes ~10
# entries so the lower bound has a few entries of slack vs. the raw 370 k.
MIN_EXPECTED_WORDS = 350_000
MAX_EXPECTED_WORDS = 400_000


logger = logging.getLogger("build_dict")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def fetch_raw(raw_path: Path, url: str, force: bool) -> Path:
    """Download the raw word list to *raw_path* if absent (or *force*)."""
    if raw_path.exists() and not force:
        logger.info("raw word list already cached at %s", raw_path)
        return raw_path

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading word list from %s", url)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 — fixed URL
        data = resp.read()
    raw_path.write_bytes(data)
    logger.info("wrote %d bytes to %s", len(data), raw_path)
    return raw_path


def load_blocklist(blocklist_path: Path) -> frozenset[str]:
    """Read *blocklist_path* — one lowercase word per line, ``#`` comments.

    Returns an empty set if the file doesn't exist (blocklist is optional).
    Used by ``normalise`` to drop common typo/archaic spellings that the
    source word list includes as "valid". See the file's header comment
    for the selection rule.
    """
    if not blocklist_path.is_file():
        logger.info("no blocklist at %s — skipping filter", blocklist_path)
        return frozenset()

    entries: set[str] = set()
    with blocklist_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            word = line.split("#", 1)[0].strip().lower()
            if word:
                entries.add(word)
    logger.info("loaded %d blocklist entries from %s", len(entries), blocklist_path)
    return frozenset(entries)


def normalise(raw_path: Path, blocklist: frozenset[str] = frozenset()) -> list[str]:
    """Read *raw_path* and return a sorted, deduped, ASCII-lowercase list.

    The pipeline:
      1. strip surrounding whitespace
      2. drop empties
      3. lowercase (the source is already lowercase but we don't trust it)
      4. keep only words that are pure a-z — drops digits, hyphens, accents
      5. dedupe via ``set``
      6. drop any word in *blocklist* (typo/archaic entries the source
         marks as valid — see scripts/dict_blocklist.txt)
      7. sort for deterministic trie output (MARISA stores in lex order
         internally, but sorting the input makes the build reproducible
         and the file byte-stable across machines).
    """
    with raw_path.open("r", encoding="utf-8") as fh:
        candidates = (line.strip().lower() for line in fh)
        words = {w for w in candidates if w and w.isascii() and w.isalpha()}

    if blocklist:
        before = len(words)
        words -= blocklist
        logger.info("blocklist removed %d entries", before - len(words))

    if not (MIN_EXPECTED_WORDS <= len(words) <= MAX_EXPECTED_WORDS):
        raise RuntimeError(
            f"normalised word count {len(words):,} is outside the expected "
            f"range [{MIN_EXPECTED_WORDS:,}, {MAX_EXPECTED_WORDS:,}]. "
            "The source may have changed; review before committing."
        )

    return sorted(words)


def build_trie(words: list[str], out_path: Path) -> marisa_trie.Trie:
    """Build a MARISA-trie from *words* and save it to *out_path*."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    trie = marisa_trie.Trie(words)
    trie.save(str(out_path))
    return trie


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--url",
        default=WORDLIST_URL,
        help="Word list URL (default: dwyl/english-words words_alpha.txt).",
    )
    parser.add_argument(
        "--raw",
        type=Path,
        default=DEFAULT_RAW_PATH,
        help="Path to cache the raw word list.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help="Output path for the serialised .marisa file.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download even if the raw list is already cached.",
    )
    parser.add_argument(
        "--blocklist",
        type=Path,
        default=DEFAULT_BLOCKLIST_PATH,
        help="Path to blocklist file (one word per line). Missing file → no filter.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    raw_path = fetch_raw(args.raw, args.url, args.force_download)
    blocklist = load_blocklist(args.blocklist)
    words = normalise(raw_path, blocklist=blocklist)
    logger.info("normalised %d unique words", len(words))

    trie = build_trie(words, args.out)
    size_kb = args.out.stat().st_size / 1024
    logger.info(
        "wrote %s (%.1f KB, %d keys)",
        args.out,
        size_kb,
        len(trie),
    )

    # Quick sanity probes — surfaces a regression before commit.
    for sample in ("hello", "world", "python", "spell"):
        if sample not in trie:
            raise RuntimeError(f"sanity probe failed: {sample!r} not in trie")
    for sample in ("asdfghjkl", "qzxqzx"):
        if sample in trie:
            raise RuntimeError(f"sanity probe failed: {sample!r} unexpectedly in trie")
    # Blocklist enforcement — every blocklist entry must be gone from the trie.
    for sample in blocklist:
        if sample in trie:
            raise RuntimeError(f"blocklist failed: {sample!r} still in trie")

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
