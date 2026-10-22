# Verified 2026-10-22. Override deliberately when upgrading the base image.
ARG PYTHON_BASE_IMAGE=python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml requirements.lock README.md ./
COPY backend/src ./backend/src
COPY backend/migrations ./backend/migrations
COPY alembic.ini ./

RUN python -m pip install --no-cache-dir --requirement requirements.lock \
    && python -m pip install --no-cache-dir --no-deps . \
    && addgroup --system --gid 10001 jarvis \
    && adduser --system --uid 10001 --ingroup jarvis --no-create-home jarvis

USER 10001:10001

EXPOSE 8080

CMD ["uvicorn", "jarvis.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--timeout-graceful-shutdown", "25"]
