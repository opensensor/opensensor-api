# syntax=docker/dockerfile:1
FROM python:3.11-slim as builder

ENV PIPENV_VENV_IN_PROJECT=1

# Copy your application source to the container
# (make sure you create a .dockerignore file if any large files or directories should be excluded)
WORKDIR /usr/src/
ADD . /usr/src/

# Install build deps, then run `pip install`, then remove unneeded build deps all in a single step.
# Correct the path to your production requirements file, if needed.
WORKDIR /usr/src/
RUN set -ex \
    && BUILD_DEPS=" \
    build-essential \
    curl \
     \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && python -m pip install --upgrade pip \
    && pip install pipenv \
    && pipenv sync --dev \
    # && pipenv run pytest \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*


FROM python:3.11-slim as runtime


COPY --from=builder /usr/src/ /usr/src/
WORKDIR /usr/src/

RUN useradd --create-home --shell /bin/bash opensensor-api
USER opensensor-api

# Start opensensor API
CMD ["/usr/src/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010", "--reload"]
