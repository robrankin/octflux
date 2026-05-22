# syntax=docker/dockerfile:1
#
#   docker compose up -d --build
#
# Mounts config at /config/config.yaml; secrets via the environment (.env).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OCTFLUX_LOG_FORMAT=json

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN pip install .

RUN useradd --create-home --uid 10001 octflux && chown -R octflux:octflux /app
USER octflux

EXPOSE 8088

ENTRYPOINT ["octflux"]
CMD ["--config", "/config/config.yaml"]
