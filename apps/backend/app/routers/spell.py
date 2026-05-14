"""Spell-check router (NFR-12).

Endpoints
---------
POST /check/text   – check a plain-text body (UC-01)
POST /check/file   – check an uploaded .txt / .docx / .pdf file (UC-02)
                     max upload size: MAX_UPLOAD_SIZE_MB env var (default 20 MB)
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.engine.checker import SpellChecker, get_checker
from app.preprocessing.extractor import SUPPORTED_EXTENSIONS, extract_text
from app.schemas.spell import SpellCheckRequest, SpellCheckResponse

router = APIRouter(prefix="/check", tags=["spell"])

# MIME types that correspond to the supported extensions (NFR-09).
_ALLOWED_MIME: frozenset[str] = frozenset(
    {
        "text/plain",                                                              # .txt
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/pdf",                                                         # .pdf
        "application/octet-stream",  # generic fallback some clients send for .docx
    }
)


@router.post("/text", response_model=SpellCheckResponse)
async def check_text(
    payload: SpellCheckRequest,
    checker: SpellChecker = Depends(get_checker),
) -> SpellCheckResponse:
    """Check a JSON body ``{"text": "..."}`` for spelling errors (UC-01)."""
    return await checker.check(payload.text)


@router.post("/file", response_model=SpellCheckResponse)
async def check_file(
    file: UploadFile = File(...),
    checker: SpellChecker = Depends(get_checker),
) -> SpellCheckResponse:
    """Check an uploaded .txt / .docx / .pdf file for spelling errors (UC-02).

    Validation order (NFR-08 / NFR-09):
    1. Filename extension must be in SUPPORTED_EXTENSIONS.
    2. Content-Type must be in _ALLOWED_MIME (if the client supplies one).
    3. File size must not exceed MAX_UPLOAD_SIZE_MB.
    Text is extracted by ``app.preprocessing.extractor.extract_text``, then
    handed off to the spell-check engine unchanged.
    """
    filename: str = file.filename or ""

    # --- 1. Extension check (NFR-09) ----------------------------------------
    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Accepted formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
            ),
        )

    # --- 2. MIME check (NFR-09) — permissive: skip if client omits header ----
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type and content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unexpected Content-Type '{content_type}' for a '{ext}' file.",
        )

    # --- 3. Size check (NFR-02 / NFR-08) -------------------------------------
    max_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
    max_bytes = max_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {max_mb} MB limit.",
        )

    # --- 4. Extract plain text and spell-check --------------------------------
    text = extract_text(content, filename)
    result = await checker.check(text)
    # Echo the extracted text so the frontend can apply corrections at the
    # returned offsets (offsets index into this string, not the raw upload).
    return result.model_copy(update={"extracted_text": text})
