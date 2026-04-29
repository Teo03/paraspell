"""Spell-check router (NFR-12).

Endpoints
---------
POST /check/text   – check a plain-text body (UC-02)
POST /check/file   – check an uploaded file, max MAX_UPLOAD_SIZE_MB (NFR-02, NFR-08)
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.engine.checker import SpellChecker, get_checker
from app.schemas.spell import SpellCheckRequest, SpellCheckResponse

router = APIRouter(prefix="/check", tags=["spell"])


@router.post("/text", response_model=SpellCheckResponse)
async def check_text(
    payload: SpellCheckRequest,
    checker: SpellChecker = Depends(get_checker),
) -> SpellCheckResponse:
    """Check a JSON body ``{"text": "..."}`` for spelling errors."""
    return await checker.check(payload.text)


@router.post("/file", response_model=SpellCheckResponse)
async def check_file(
    file: UploadFile = File(...),
    checker: SpellChecker = Depends(get_checker),
) -> SpellCheckResponse:
    """Check an uploaded plain-text file for spelling errors (NFR-02, NFR-08)."""
    import os

    max_bytes = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20")) * 1024 * 1024
    content = await file.read(max_bytes + 1)

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds the {os.getenv('MAX_UPLOAD_SIZE_MB', '20')} MB limit.",
        )

    text = content.decode("utf-8", errors="replace")
    return await checker.check(text)
