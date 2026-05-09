# ParaSpell Parallel Implementation Plan

## Executive Summary

This document outlines the implementation plan for the **text chunking and parallel processing** features of ParaSpell, addressing the core SRS requirements (FR-06, FR-07, NFR-03, NFR-07). The work involves transitioning from a sequential spell-checking pipeline to a fully parallelized architecture using Python's `ProcessPoolExecutor`.

**Status**: Planning phase complete. Ready for implementation.

---

## 1. Project Analysis

### 1.1 Current State

**Backend Structure** (FastAPI + Python):

```
apps/backend/
├── app/
│   ├── main.py              # FastAPI app setup, CORS, lifespan
│   ├── routers/
│   │   ├── spell.py         # /check/text endpoint (NOT YET IMPLEMENTED)
│   │   └── health.py        # /health endpoint
│   ├── schemas/
│   │   └── spell.py         # Pydantic models (SpellCheckRequest/Response, Correction, Suggestion)
│   └── engine/
│       ├── checker.py       # SpellChecker facade (SEQUENTIAL - needs parallelization)
│       ├── dictionary.py    # Dictionary loader (MARISA-trie + SQLite Soundex cache)
│       └── worker.py        # process_chunk() function (worker logic, READY for parallel)
├── routers/spell.py         # Missing - needs to be created
├── tests/
│   ├── test_worker.py       # Tests for worker.process_chunk()
│   ├── test_dictionary.py   # Tests for Dictionary class
│   └── test_soundex.py      # Tests for Soundex algorithm
├── requirements.txt         # Dependencies (FastAPI, marisa-trie, rapidfuzz, jellyfish, etc.)
└── data/
    ├── words.marisa         # 370k English dictionary (MARISA-trie)
    └── soundex.sqlite       # Soundex phonetic mappings (SQLite)
```

**Current Pipeline** (as of now):

```python
# In checker.py:
async def check(self, text: str) -> SpellCheckResponse:
    tokens = self._tokenise(text)
    chunks = self._split(tokens)          # ✓ Chunks are created

    corrections: list[Correction] = []
    for chunk in chunks:
        # ✗ SEQUENTIAL: processes one chunk at a time
        corrections.extend(process_chunk(chunk, self._dictionary))

    return SpellCheckResponse(...)
```

**Worker Design** (already complete):

- `process_chunk(chunk, dictionary)` → `list[Correction]`
- Stateless function suitable for pickling
- Performs: tokenization → Soundex filtering → Levenshtein ranking
- Error handling: currently `pass` on known words, raises on unknown

**Key Components Ready**:

- ✓ `Dictionary` class (MARISA-trie + SQLite + LRU cache)
- ✓ `process_chunk()` worker function
- ✓ Chunking logic (`_split()` method)
- ✓ Tokenization logic (`_tokenise()` method)
- ✓ Pydantic schemas (SpellCheckRequest, SpellCheckResponse, Correction, Suggestion)
- ✓ Test suite (conftest with fixtures, test_worker.py, etc.)
- ✗ ProcessPoolExecutor integration (to be implemented)
- ✗ Error handling in worker pool (to be implemented)
- ✗ Benchmarking infrastructure (to be implemented)

---

## 2. SRS Requirements Map

### Functional Requirements (FR)

- **FR-05**: Initiate spell check → `POST /check/text` endpoint (not yet created)
- **FR-06**: Parallel processing → **ProcessPoolExecutor in checker.py** (TODO)
- **FR-07**: Auto worker count → `os.cpu_count()` resolution (partially done)
- **FR-08-11**: Worker logic (Soundex, Levenshtein, suggestions) → **Already in worker.py** ✓

### Non-Functional Requirements (NFR)

- **NFR-01**: Response time: 1MB → 30s on 4-core → Enabled by parallelization
- **NFR-02**: Scalability: 20MB max → Handled by chunk size tuning
- **NFR-03**: Efficiency: ≥3x speedup on 5MB+ → **Benchmarking required** (TODO)
- **NFR-07**: Worker fault tolerance → **Error handling in executor** (TODO)

---

## 3. Implementation Tasks

### Task 1: Implement ProcessPoolExecutor Integration

**File**: [apps/backend/app/engine/checker.py](apps/backend/app/engine/checker.py)

**Current Code**:

```python
async def check(self, text: str) -> SpellCheckResponse:
    tokens = self._tokenise(text)
    chunks = self._split(tokens)

    corrections: list[Correction] = []
    for chunk in chunks:
        corrections.extend(process_chunk(chunk, self._dictionary))

    return SpellCheckResponse(...)
```

**Changes**:

1. Import `ProcessPoolExecutor` from `concurrent.futures`
2. Replace sequential `for` loop with executor submission
3. Submit each chunk as a future to the pool
4. Collect all futures and await results
5. Preserve error handling (catch exceptions, log, return partial results)
6. Preserve original word order and positions

**Key Design Decisions**:

- Use `ProcessPoolExecutor` (not `ThreadPoolExecutor`):
  - Threads can't bypass Python's GIL
  - ProcessPoolExecutor leverages OS-level parallelism
  - Dictionary is fork-safe (read-only after init, uses Linux COW)
- Worker count: `self._worker_count = os.cpu_count() or 1` (already in **init**)
- Pool lifetime: Create per request? Or singleton?
  - **Decision**: Singleton (one pool per application lifecycle) for efficiency
  - Avoid repeated pool creation/teardown overhead
- Executor shutdown: Handle in FastAPI lifespan context manager

**Expected Code Structure**:

```python
from concurrent.futures import ProcessPoolExecutor
import asyncio
import logging

logger = logging.getLogger(__name__)

class SpellChecker:
    def __init__(self) -> None:
        self._dictionary = Dictionary()
        self._worker_count = self._resolve_int("WORKER_COUNT", os.cpu_count() or 1)
        self._chunk_size = self._resolve_int("CHUNK_SIZE", 0)
        self._executor = ProcessPoolExecutor(max_workers=self._worker_count)

    async def check(self, text: str) -> SpellCheckResponse:
        tokens = self._tokenise(text)
        chunks = self._split(tokens)

        # Submit chunks to executor
        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(self._executor, process_chunk, chunk, self._dictionary)
            for chunk in chunks
        ]

        # Await all futures (with timeout/error handling)
        corrections: list[Correction] = []
        for future in asyncio.as_completed(futures):
            try:
                result = await future
                corrections.extend(result)
            except Exception as e:
                logger.exception(f"Worker failed: {e}")
                # Continue with partial results

        return SpellCheckResponse(
            word_count=len(tokens),
            error_count=len(corrections),
            corrections=corrections,
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)
```

**Wire in FastAPI Lifespan**:

```python
# In main.py
@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    checker = get_checker()  # Initialize
    yield
    checker.shutdown()  # Cleanup
```

---

### Task 2: Implement Worker Error Handling

**File**: [apps/backend/app/engine/worker.py](apps/backend/app/engine/worker.py)

**Current Code**:

```python
def process_chunk(chunk, dictionary) -> list[Correction]:
    corrections: list[Correction] = []
    for word, offset in chunk:
        if dictionary.contains(word):
            continue  # Known word, skip
        suggestions = _rank_suggestions(word, dictionary)
        corrections.append(Correction(original=word, offset=offset, suggestions=suggestions))
    return corrections
```

**Changes**:

1. Wrap the entire function body in `try/except`
2. Log exceptions with full context (word, offset, chunk size)
3. Return partial result (corrections found before failure)
4. Do NOT re-raise (return gracefully to caller)

**Expected Code Structure**:

```python
import logging

logger = logging.getLogger(__name__)

def process_chunk(
    chunk: list[tuple[str, int]],
    dictionary: Dictionary,
) -> list[Correction]:
    """Check a chunk of (word, offset) pairs with fault tolerance."""
    corrections: list[Correction] = []

    try:
        for word, offset in chunk:
            try:
                if dictionary.contains(word):
                    continue
                suggestions = _rank_suggestions(word, dictionary)
                corrections.append(
                    Correction(original=word, offset=offset, suggestions=suggestions)
                )
            except Exception as e:
                logger.warning(f"Failed to process word '{word}' at offset {offset}: {e}")
                # Continue with next word instead of crashing chunk
                continue
    except Exception as e:
        logger.exception(f"Chunk processing failed ({len(chunk)} words): {e}")
        # Return partial result instead of raising

    return corrections
```

**Rationale**:

- Inner try/except: Catch errors on individual words (graceful degradation)
- Outer try/except: Catch unexpected errors from Dictionary or Levenshtein (prevent process death)
- **Important**: Do NOT raise exceptions back to executor; always return a valid `list[Correction]`
- Logging: Helps debug issues without blocking the request

---

### Task 3: Implement Benchmarking Infrastructure

**New File**: [apps/backend/scripts/benchmark.py](apps/backend/scripts/benchmark.py)

**Purpose**:

- Compare parallel vs. sequential execution on 1MB and 5MB test files
- Verify ≥3x speedup requirement (NFR-03)
- Generate benchmark.md report

**Test Inputs**:

- Generate synthetic test files (1MB and 5MB of repeated English text with intentional typos)
- Measure both single-threaded baseline and parallel execution

**Metrics**:

```
- Input size (bytes)
- Word count
- Misspelling count
- Sequential time (s)
- Parallel time (s)
- Speedup ratio (sequential / parallel)
- Pass/Fail (speedup ≥ 3x?)
```

**Expected Code Structure**:

```python
import asyncio
import time
import tempfile
from pathlib import Path

from app.engine.checker import SpellChecker
from app.engine.worker import process_chunk
from app.engine.dictionary import Dictionary

def generate_test_text(size_mb: int) -> str:
    """Generate synthetic test text with typos."""
    base_text = "The quick brown fox jumps over the lazy dog. " * 1000
    # Add typos: "recieve", "seperate", "definately", etc.
    return (base_text * (size_mb * 1024 // len(base_text.encode()))) + "\nrecieve seperate definately occassion\n"

async def benchmark_parallel(text: str, num_runs: int = 3) -> dict:
    """Benchmark parallel spell checking."""
    checker = SpellChecker()
    times = []
    for _ in range(num_runs):
        start = time.perf_counter()
        result = await checker.check(text)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    checker.shutdown()
    return {"times": times, "avg": sum(times) / len(times), "errors": result.error_count}

def benchmark_sequential(text: str, num_runs: int = 3) -> dict:
    """Benchmark sequential spell checking."""
    from app.engine.checker import SpellChecker as SeqChecker
    # Temporarily disable parallelization...
    checker = SeqChecker()
    checker._worker_count = 1  # Force sequential
    times = []
    for _ in range(num_runs):
        start = time.perf_counter()
        result = checker.check(text)  # Blocking call
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return {"times": times, "avg": sum(times) / len(times), "errors": result.error_count}

if __name__ == "__main__":
    for size_mb in [1, 5]:
        print(f"\n{'='*60}")
        print(f"Benchmarking {size_mb}MB input...")
        print(f"{'='*60}")

        text = generate_test_text(size_mb)
        print(f"Generated {len(text)} bytes, {len(text.split())} words")

        seq_result = benchmark_sequential(text)
        par_result = asyncio.run(benchmark_parallel(text))

        speedup = seq_result["avg"] / par_result["avg"]
        print(f"Sequential: {seq_result['avg']:.3f}s")
        print(f"Parallel:   {par_result['avg']:.3f}s")
        print(f"Speedup:    {speedup:.2f}x")
        print(f"Status:     {'✓ PASS' if speedup >= 3.0 else '✗ FAIL'} (target: ≥3x)")
```

**Output**: `benchmark.md` with detailed results table

---

### Task 4: Create `/check/text` Endpoint

**File**: [apps/backend/app/routers/spell.py](apps/backend/app/routers/spell.py)

**Purpose**: Expose the spell checker to clients via REST API

**Expected Code Structure**:

```python
from fastapi import APIRouter, HTTPException
from app.engine.checker import get_checker
from app.schemas.spell import SpellCheckRequest, SpellCheckResponse

router = APIRouter(prefix="/check", tags=["spell"])

@router.post("/text", response_model=SpellCheckResponse)
async def check_text(request: SpellCheckRequest) -> SpellCheckResponse:
    """Spell-check plain text input."""
    checker = get_checker()
    return await checker.check(request.text)
```

---

## 4. Testing Strategy

### Unit Tests (Existing)

- `test_worker.py`: Tests `process_chunk()` with known/unknown words, suggestion ranking
- `test_dictionary.py`: Tests Dictionary.contains(), soundex_candidates(), get_candidates()
- `test_soundex.py`: Tests Soundex algorithm edge cases

**Running Tests**:

```bash
cd apps/backend
pytest tests/ -v
```

### Integration Tests (New)

- Test `/check/text` endpoint
- Test error handling with malformed input
- Test concurrent requests (multiple spell checks in parallel)

**Test Commands**:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_worker.py -v
```

### Performance Tests (Benchmark)

```bash
python apps/backend/scripts/benchmark.py
```

---

## 5. Implementation Order

1. **Create edi-parallel branch** ← Isolate changes
2. **Task 2: Worker Error Handling** ← Low-risk, enables graceful degradation
3. **Task 1: ProcessPoolExecutor Integration** ← Core feature
4. **Task 4: Wire endpoint** ← Expose to API
5. **Run existing tests** ← Verify no regressions
6. **Task 3: Benchmarking** ← Validate performance requirements
7. **Final validation** ← All tests pass, SRS compliance verified

---

## 6. Risk Mitigation

### Risk 1: Fork-safety issues with Dictionary

**Mitigation**:

- Dictionary is intentionally fork-safe (read-only after init, uses Linux COW)
- Don't modify self.\_dictionary in workers
- Test with real ProcessPoolExecutor (not mocked)

### Risk 2: Performance regression

**Mitigation**:

- Benchmark baseline before changes
- Run tests frequently to catch regressions early
- Profile with `cProfile` if needed

### Risk 3: Unforeseen exceptions in worker pool

**Mitigation**:

- Comprehensive try/except in process_chunk()
- Log all exceptions
- Return partial results (graceful degradation)

### Risk 4: Executor pool shutdown issues

**Mitigation**:

- Use FastAPI lifespan context manager for cleanup
- Ensure `shutdown(wait=True)` is called
- Test shutdown behavior explicitly

---

## 7. Success Criteria

✓ All existing tests pass (no regressions)  
✓ ProcessPoolExecutor integration complete  
✓ Error handling prevents request crashes  
✓ Benchmarks show ≥3x speedup on 5MB+ inputs  
✓ `/check/text` endpoint functional  
✓ Code follows SRS architecture (NFR-12: modular design)  
✓ Branch ready for code review and merge to main

---

## 8. Git Workflow

```bash
# Create feature branch
git checkout -b edi-parallel

# Make changes, commit frequently
git add apps/backend/app/engine/checker.py
git commit -m "feat: add ProcessPoolExecutor integration (FR-06, FR-07)"

# Push to remote
git push origin edi-parallel

# After review, merge to main
git checkout main
git merge edi-parallel
```

---

## 9. Files Modified/Created

| File                                                                     | Status | Why                                     |
| ------------------------------------------------------------------------ | ------ | --------------------------------------- |
| [apps/backend/app/engine/checker.py](apps/backend/app/engine/checker.py) | Modify | Add ProcessPoolExecutor, error handling |
| [apps/backend/app/engine/worker.py](apps/backend/app/engine/worker.py)   | Modify | Add try/except, logging                 |
| [apps/backend/app/routers/spell.py](apps/backend/app/routers/spell.py)   | Create | `/check/text` endpoint                  |
| [apps/backend/app/main.py](apps/backend/app/main.py)                     | Modify | Add executor shutdown to lifespan       |
| [apps/backend/scripts/benchmark.py](apps/backend/scripts/benchmark.py)   | Create | Benchmark infrastructure                |
| [benchmark.md](benchmark.md)                                             | Create | Benchmark results report                |

---

## 10. Next Steps

1. **Review this plan** with the team
2. **Approve** the approach
3. **Start implementation** with Task 2 (Worker Error Handling)
4. **Commit to edi-parallel branch** frequently
5. **Run tests after each task** to catch issues early
6. **Update this document** with actual results and timings
