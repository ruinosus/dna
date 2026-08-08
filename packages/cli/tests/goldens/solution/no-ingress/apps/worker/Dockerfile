# worker — built from THIS app's own package, never from a shared
# infra Dockerfile: the version floor lives in pyproject.toml, and a build that
# installed it anywhere else would make the declared floor a lie.
#
# ⚠️ This file exists only because worker OWNS the code
# (`owns_code: true`). N services can run this ONE image — the identity doors
# are three services over one image — and each of them renders its own wiring
# with its own sleep answer.
#
# ⭐ `ingress: none` — worker does NOT serve. This image binds
# nothing and EXPOSEs nothing: there is no port here to bake a default for,
# and an EXPOSE would document a door that does not exist.
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="worker" \
      org.opencontainers.image.description="the queue worker — it answers nobody"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

CMD ["worker"]
