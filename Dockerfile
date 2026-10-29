# syntax=docker/dockerfile:1
FROM python:3.13-slim as builder

ENV PIPENV_VENV_IN_PROJECT=1

# Copy your application source to the container
WORKDIR /usr/src/
ADD . /usr/src/

# Install build deps, then install pipenv & dependencies
RUN set -ex \
    && BUILD_DEPS=" \
        build-essential \
        curl \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && python -m pip install --upgrade pip \
    && pip install pipenv \
    && pipenv sync --dev \
    # Optionally run tests here:
    # && pipenv run pytest \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*


FROM python:3.13-slim as runtime

# ✅ Install CA certificates so TLS works with Let's Encrypt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/src/ /usr/src/
WORKDIR /usr/src/

RUN useradd --create-home --shell /bin/bash opensensor-api
USER opensensor-api

ENV TZ=UTC

# Start opensensor API
# Public Sentry ingestion key; upload credentials are never part of the image.
ARG SENTRY_RELEASE
ENV SENTRY_DSN=https://f342f997ac7c582759f18b6d46a71956@o4512337837686784.ingest.us.sentry.io/4512337894637568 \
    SENTRY_ENVIRONMENT=production \
    SENTRY_RELEASE=${SENTRY_RELEASE}

CMD ["/usr/src/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--timeout-keep-alive", "30", "--log-level", "info"]
