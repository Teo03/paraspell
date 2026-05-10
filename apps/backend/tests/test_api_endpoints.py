"""API endpoint tests for /check/text and /check/file (Task 7 — FR-06, FR-07, NFR-07, NFR-09).

Coverage
--------
TestCheckText        — POST /check/text: schema, word_count, corrections, suggestions,
                       processing_time, offsets, validation errors.
TestCheckFile        — POST /check/file: .txt / .docx / .pdf accepted, misspellings
                       detected, processing_time present.
TestFileValidation   — oversized, unsupported extension, wrong MIME, missing extension.
TestCORS             — OPTIONS preflight, ACAO header on POST, env-var override.
"""

from __future__ import annotations

import io
from unittest import mock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# In-memory file helpers
# ---------------------------------------------------------------------------

def _make_txt_bytes(text: str) -> bytes:
    """Return UTF-8-encoded bytes for a plain-text upload."""
    return text.encode("utf-8")


def _make_docx_bytes(text: str) -> bytes:
    """Return in-memory .docx bytes containing *text* (uses python-docx)."""
    import docx

    doc = docx.Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_pdf_bytes() -> bytes:
    """Return a minimal valid PDF that pdfplumber can open (no text — zero words)."""
    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> >>\n"
        b"endobj\n"
    )

    off1 = len(header)
    off2 = off1 + len(obj1)
    off3 = off2 + len(obj2)
    xref_pos = off3 + len(obj3)

    xref = (
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        + f"{off1:010d} 00000 n \n".encode()
        + f"{off2:010d} 00000 n \n".encode()
        + f"{off3:010d} 00000 n \n".encode()
    )
    trailer = (
        b"trailer\n"
        b"<< /Size 4 /Root 1 0 R >>\n"
        b"startxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return header + obj1 + obj2 + obj3 + xref + trailer


# ---------------------------------------------------------------------------
# Shared TestClient fixture (lifespan runs once per module)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — initialises SpellChecker once for this file."""
    from app.main import create_app

    _app = create_app()
    with TestClient(_app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# TestCheckText
# ---------------------------------------------------------------------------

class TestCheckText:
    """POST /check/text endpoint tests."""

    # --- schema / happy-path ------------------------------------------------

    def test_response_has_required_schema_fields(self, client: TestClient) -> None:
        """Response must contain word_count, error_count, processing_time, corrections."""
        resp = client.post("/check/text", json={"text": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert "word_count" in data
        assert "error_count" in data
        assert "processing_time" in data
        assert "corrections" in data

    def test_word_count_matches_token_count(self, client: TestClient) -> None:
        """word_count should equal the number of word tokens in the input."""
        resp = client.post("/check/text", json={"text": "one two three four five"})
        assert resp.status_code == 200
        assert resp.json()["word_count"] == 5

    def test_clean_text_returns_no_corrections(self, client: TestClient) -> None:
        """Well-spelled text must produce zero corrections and error_count == 0."""
        resp = client.post("/check/text", json={"text": "the cat sat on the mat"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] == 0
        assert data["corrections"] == []

    def test_known_misspelling_is_detected(self, client: TestClient) -> None:
        """'speling' is a classic misspelling and must appear in corrections."""
        resp = client.post("/check/text", json={"text": "speling"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] >= 1
        originals = [c["original"] for c in data["corrections"]]
        assert "speling" in originals

    def test_suggestions_have_word_and_score(self, client: TestClient) -> None:
        """Each suggestion must have a 'word' string and a 'score' float in [0, 1]."""
        resp = client.post("/check/text", json={"text": "speling"})
        assert resp.status_code == 200
        corrections = resp.json()["corrections"]
        assert len(corrections) >= 1
        for suggestion in corrections[0]["suggestions"]:
            assert isinstance(suggestion["word"], str)
            assert isinstance(suggestion["score"], float)
            assert 0.0 <= suggestion["score"] <= 1.0

    def test_suggestions_capped_at_max_five(self, client: TestClient) -> None:
        """No correction may have more than 5 suggestions (UC-03)."""
        resp = client.post("/check/text", json={"text": "speling misteak"})
        assert resp.status_code == 200
        for correction in resp.json()["corrections"]:
            assert len(correction["suggestions"]) <= 5

    def test_processing_time_is_non_negative(self, client: TestClient) -> None:
        """processing_time must be >= 0 (FR-20)."""
        resp = client.post("/check/text", json={"text": "hello"})
        assert resp.status_code == 200
        assert resp.json()["processing_time"] >= 0.0

    def test_correction_offset_is_valid(self, client: TestClient) -> None:
        """offset of each correction must be >= 0 and within the input string."""
        text = "This has a speling errror in it"
        resp = client.post("/check/text", json={"text": text})
        assert resp.status_code == 200
        for correction in resp.json()["corrections"]:
            offset = correction["offset"]
            assert offset >= 0
            assert offset < len(text)

    def test_correction_offset_points_to_original_word(self, client: TestClient) -> None:
        """text[offset:offset+len(original)] must equal the original misspelled word."""
        text = "speling"
        resp = client.post("/check/text", json={"text": text})
        assert resp.status_code == 200
        for correction in resp.json()["corrections"]:
            word = correction["original"]
            offset = correction["offset"]
            assert text[offset: offset + len(word)] == word

    def test_multiple_misspellings_all_reported(self, client: TestClient) -> None:
        """Every distinct misspelled word should appear once in corrections."""
        resp = client.post("/check/text", json={"text": "speling misteak"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] >= 2

    def test_error_count_equals_corrections_length(self, client: TestClient) -> None:
        """error_count must equal len(corrections)."""
        resp = client.post("/check/text", json={"text": "speling misteak beleive"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] == len(data["corrections"])

    # --- validation errors --------------------------------------------------

    def test_empty_string_returns_422(self, client: TestClient) -> None:
        """Empty text must be rejected with 422 (Pydantic min_length=1)."""
        resp = client.post("/check/text", json={"text": ""})
        assert resp.status_code == 422

    def test_missing_text_field_returns_422(self, client: TestClient) -> None:
        """Omitting the 'text' field must return 422."""
        resp = client.post("/check/text", json={})
        assert resp.status_code == 422

    def test_wrong_content_type_returns_422(self, client: TestClient) -> None:
        """Sending plain text instead of JSON must return 422."""
        resp = client.post(
            "/check/text",
            content=b"hello world",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 422

    def test_null_text_returns_422(self, client: TestClient) -> None:
        """null text value must return 422."""
        resp = client.post("/check/text", json={"text": None})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestCheckFile
# ---------------------------------------------------------------------------

class TestCheckFile:
    """POST /check/file endpoint — file-type acceptance and spell-check results."""

    def test_txt_file_accepted(self, client: TestClient) -> None:
        """A valid .txt upload must return 200 with the expected schema."""
        payload = _make_txt_bytes("hello world")
        resp = client.post(
            "/check/file",
            files={"file": ("sample.txt", payload, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "word_count" in data
        assert "corrections" in data

    def test_docx_file_accepted(self, client: TestClient) -> None:
        """A valid .docx upload must return 200."""
        payload = _make_docx_bytes("hello world")
        resp = client.post(
            "/check/file",
            files={
                "file": (
                    "sample.docx",
                    payload,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert resp.status_code == 200
        assert "word_count" in resp.json()

    def test_pdf_file_accepted(self, client: TestClient) -> None:
        """A valid .pdf upload must return 200 (no text in PDF → word_count == 0)."""
        payload = _make_pdf_bytes()
        resp = client.post(
            "/check/file",
            files={"file": ("sample.pdf", payload, "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["word_count"] == 0

    def test_txt_misspelling_detected(self, client: TestClient) -> None:
        """Misspellings in a .txt upload must be reported in corrections."""
        payload = _make_txt_bytes("speling")
        resp = client.post(
            "/check/file",
            files={"file": ("sample.txt", payload, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] >= 1
        originals = [c["original"] for c in data["corrections"]]
        assert "speling" in originals

    def test_docx_misspelling_detected(self, client: TestClient) -> None:
        """Misspellings inside a .docx upload must be reported."""
        payload = _make_docx_bytes("speling misteak")
        resp = client.post(
            "/check/file",
            files={
                "file": (
                    "sample.docx",
                    payload,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert resp.status_code == 200
        assert resp.json()["error_count"] >= 1

    def test_txt_clean_text_no_corrections(self, client: TestClient) -> None:
        """A clean .txt file must return no corrections."""
        payload = _make_txt_bytes("the cat sat on the mat")
        resp = client.post(
            "/check/file",
            files={"file": ("clean.txt", payload, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error_count"] == 0
        assert data["corrections"] == []

    def test_file_response_has_processing_time(self, client: TestClient) -> None:
        """File endpoint response must include processing_time >= 0 (FR-20)."""
        payload = _make_txt_bytes("hello world")
        resp = client.post(
            "/check/file",
            files={"file": ("sample.txt", payload, "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["processing_time"] >= 0.0

    def test_octet_stream_mime_accepted_for_docx(self, client: TestClient) -> None:
        """application/octet-stream is an allowed fallback MIME for .docx files."""
        payload = _make_docx_bytes("hello")
        resp = client.post(
            "/check/file",
            files={"file": ("sample.docx", payload, "application/octet-stream")},
        )
        assert resp.status_code == 200

    def test_word_count_matches_txt_content(self, client: TestClient) -> None:
        """word_count via file endpoint should match the token count of the text."""
        payload = _make_txt_bytes("one two three four five")
        resp = client.post(
            "/check/file",
            files={"file": ("count.txt", payload, "text/plain")},
        )
        assert resp.status_code == 200
        assert resp.json()["word_count"] == 5


# ---------------------------------------------------------------------------
# TestFileValidation
# ---------------------------------------------------------------------------

class TestFileValidation:
    """POST /check/file — file validation rejections (NFR-08, NFR-09)."""

    def test_unsupported_extension_exe_rejected(self, client: TestClient) -> None:
        """A .exe file must be rejected with 400."""
        resp = client.post(
            "/check/file",
            files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    def test_unsupported_extension_csv_rejected(self, client: TestClient) -> None:
        """A .csv file must be rejected with 400."""
        resp = client.post(
            "/check/file",
            files={"file": ("data.csv", b"col1,col2\n1,2\n", "text/csv")},
        )
        assert resp.status_code == 400

    def test_no_extension_rejected(self, client: TestClient) -> None:
        """A file with no extension must be rejected with 400."""
        resp = client.post(
            "/check/file",
            files={"file": ("noextension", b"some text", "text/plain")},
        )
        assert resp.status_code == 400

    def test_wrong_mime_type_rejected(self, client: TestClient) -> None:
        """A .txt file sent with an image/jpeg MIME must be rejected with 400."""
        resp = client.post(
            "/check/file",
            files={"file": ("trick.txt", b"hello", "image/jpeg")},
        )
        assert resp.status_code == 400
        assert "Content-Type" in resp.json()["detail"]

    def test_oversized_file_rejected(self, client: TestClient) -> None:
        """A file exceeding MAX_UPLOAD_SIZE_MB must be rejected with 400."""
        # Use MAX_UPLOAD_SIZE_MB=0 so any non-empty payload is "too large",
        # avoiding the need to allocate a multi-MB test buffer.
        with mock.patch.dict("os.environ", {"MAX_UPLOAD_SIZE_MB": "0"}):
            resp = client.post(
                "/check/file",
                files={"file": ("large.txt", b"x" * 100, "text/plain")},
            )
        assert resp.status_code == 400
        assert "exceeds" in resp.json()["detail"].lower()

    def test_missing_file_field_returns_422(self, client: TestClient) -> None:
        """Sending no file at all must return 422 (missing required field)."""
        resp = client.post("/check/file")
        assert resp.status_code == 422

    def test_error_detail_contains_supported_formats(self, client: TestClient) -> None:
        """400 on bad extension should mention the supported formats."""
        resp = client.post(
            "/check/file",
            files={"file": ("bad.zip", b"PK\x03\x04", "application/zip")},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        # At least one supported extension must appear in the message.
        assert any(ext in detail for ext in (".txt", ".docx", ".pdf"))


# ---------------------------------------------------------------------------
# TestCORS
# ---------------------------------------------------------------------------

class TestCORS:
    """CORS header and preflight tests (NFR-11)."""

    def test_preflight_from_allowed_origin_succeeds(self, client: TestClient) -> None:
        """OPTIONS preflight from the default allowed origin must return 200."""
        resp = client.options(
            "/check/text",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert resp.status_code == 200

    def test_preflight_response_contains_acao_header(self, client: TestClient) -> None:
        """OPTIONS response must include Access-Control-Allow-Origin."""
        resp = client.options(
            "/check/text",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" in resp.headers

    def test_post_response_contains_acao_header(self, client: TestClient) -> None:
        """A regular POST from an allowed origin must carry the ACAO header."""
        resp = client.post(
            "/check/text",
            json={"text": "hello"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_acao_header_value_matches_origin(self, client: TestClient) -> None:
        """The ACAO header value must match the requesting origin."""
        origin = "http://localhost:5173"
        resp = client.post(
            "/check/text",
            json={"text": "hello"},
            headers={"Origin": origin},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin

    def test_cors_origins_env_var_respected(self) -> None:
        """CORS_ORIGINS env var must override the default allowed origins."""
        custom_origin = "http://custom.example.com"
        with mock.patch.dict("os.environ", {"CORS_ORIGINS": custom_origin}):
            from app.main import create_app  # noqa: PLC0415

            _app = create_app()
            with TestClient(_app) as custom_client:
                resp = custom_client.post(
                    "/check/text",
                    json={"text": "hello"},
                    headers={"Origin": custom_origin},
                )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == custom_origin

    def test_allow_methods_header_present_on_preflight(self, client: TestClient) -> None:
        """Preflight response must include Access-Control-Allow-Methods."""
        resp = client.options(
            "/check/text",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-methods" in resp.headers
