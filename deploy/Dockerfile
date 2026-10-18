# syntax=docker/dockerfile:1.7
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=UTC

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --gid 10001 gateway && \
    useradd --uid 10001 --gid gateway --create-home --shell /usr/sbin/nologin gateway

COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY --chown=gateway:gateway backend ./backend
COPY --chown=gateway:gateway frontend ./frontend
COPY --chown=gateway:gateway README.md LICENSE .env.example ./
COPY deploy/scripts/docker-entrypoint.sh /usr/local/bin/polaris-entrypoint

RUN chmod 0755 /usr/local/bin/polaris-entrypoint && \
    mkdir -p /app/backend/data/creds /app/backend/data/logs && \
    chown -R gateway:gateway /app

# Build identity belongs after dependency/application layers so a new immutable
# revision does not force network-bound package installation to run again.
ARG BUILD_DATE=""
ARG VERSION="dev"
ARG REVISION="unknown"

ENV BUILD_DATE=${BUILD_DATE} \
    BUILD_VERSION=${VERSION} \
    BUILD_REVISION=${REVISION}

LABEL org.opencontainers.image.title="Polaris" \
      org.opencontainers.image.description="Universal AI router for coding tools" \
      org.opencontainers.image.source="https://github.com/nguywnben/polaris" \
      org.opencontainers.image.url="https://github.com/nguywnben/polaris" \
      org.opencontainers.image.documentation="https://github.com/nguywnben/polaris#readme" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

EXPOSE 4283
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('PORT', '4283'); urllib.request.urlopen(f'http://127.0.0.1:{port}/ready', timeout=3).read()" || exit 1

ENTRYPOINT ["/usr/local/bin/polaris-entrypoint"]
CMD ["python", "backend/main.py"]
