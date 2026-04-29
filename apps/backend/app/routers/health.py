from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by docker-compose healthcheck (NFR-11)."""
    return {"status": "ok"}
