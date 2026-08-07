# api — built from THIS app's own package, never from a shared
# infra Dockerfile: the version floor lives in pyproject.toml, and a build that
# installed it anywhere else would make the declared floor a lie.
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="api" \
      org.opencontainers.image.description="api — a DNA runtime face"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DNA_API_HOST=0.0.0.0 \
    DNA_API_PORT=8080

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["api"]
