# syntax=docker/dockerfile:1
# docspecsite images: Python (from .python-version, installed by uv), git and
# the vendored Mermaid bundle, plus docspecsite itself. Two targets:
# - runtime (the last stage, so the default): docspecsite installed as a
#   package. Projects build it from this repo's git URL at a release tag and
#   bind-mount their repo at /repo.
# - dev: the development tools, with docspecsite installed editable from
#   /repo, where compose.yaml mounts this repo's source.
# See docs/architecture/docs-tooling.md#docker-image and DSS-0002. No Python
# version appears here on purpose.
FROM ghcr.io/astral-sh/uv:0.13.7-debian-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Python and the virtual environment live under /opt, outside the /repo bind
# mount, so the mount does not hide them. UV_LINK_MODE=copy because the uv
# cache is a separate cache mount; bytecode is compiled at install time, since
# the container user cannot write it under /opt.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Vendored Mermaid for the docs site (remote ADD files are mode 600; the chmod
# in each target makes them readable).
ADD --checksum=sha256:336df803d87a38b70a01e736e666c8f7601d2ce42f5e47c8fafe5d721074b9a3 \
    https://cdn.jsdelivr.net/npm/mermaid@12.3.0/dist/mermaid.min.js /opt/docspecsite-vendor/mermaid/mermaid.min.js
ADD --checksum=sha256:ec9fb67dcb25eccc416ed56e1aab819222c805a2a4bfe4cb19e7556bf2ffde80 \
    https://cdn.jsdelivr.net/npm/mermaid@12.3.0/LICENSE /opt/docspecsite-vendor/mermaid/LICENSE
ENV DOCSPECSITE_VENDOR_DIR=/opt/docspecsite-vendor

# Containers run as the host user (no home directory): trust the bind-mounted
# repo system-wide, not per user.
RUN git config --system --add safe.directory /repo


FROM base AS dev

# Every dependency group, and docspecsite installed editable: /opt/venv points
# at /repo/src, which the bind mount replaces with the live source at run time.
WORKDIR /repo

# Dependencies first, so a change to the source does not reinstall them.
COPY .python-version pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen \
    && chmod -R a+rX /opt


FROM base AS runtime

WORKDIR /opt/docspecsite

# Dependencies first, so a change to the source does not reinstall them.
COPY .python-version pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# docspecsite itself, installed as a regular (non-editable) package: the
# checked repo, not this source, is what gets mounted at run time.
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable \
    && chmod -R a+rX /opt

WORKDIR /repo

ENTRYPOINT ["docspecsite"]
