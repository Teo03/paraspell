"""Minimal FastAPI hello-world for docker-compose verification.

This is a placeholder so docker-compose has a backend service to start.
The full NFR-12 modular structure (api / engine / dictionary / workers) and
the production Dockerfile are owned by separate Trello cards and will replace
this scaffold.
"""

from fastapi import FastAPI

app = FastAPI(title="ParaSpell API", version="0.0.0")


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "ParaSpell", "status": "hello-world"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
