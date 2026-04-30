# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — dependency builder
# Installs Python packages into an isolated prefix so the final image
# receives only the compiled wheels, not pip/setuptools/build tooling.
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — runtime image
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create a non-root user (security best practice)
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy application source
COPY app ./app

# Hand ownership to the non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# --reload is intentionally kept for the sprint demo; remove for production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]