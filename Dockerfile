FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

WORKDIR /src

COPY pyproject.toml uv.lock README.md LICENSE MANIFEST.in ./
COPY CHANGELOG.md CONTRIBUTING.md SECURITY.md .env.example ./
COPY compose.yaml Dockerfile Makefile ./
COPY application ./application
COPY core ./core
COPY data ./data
COPY domain ./domain
COPY deploy ./deploy
COPY docs ./docs
COPY evaluation ./evaluation
COPY models ./models
COPY observability ./observability
COPY persistence ./persistence
COPY policy ./policy
COPY scripts ./scripts
COPY strategies ./strategies
COPY utils ./utils
COPY main.py config.yaml ./

RUN python -m pip install "uv==0.11.32" \
    && uv sync --locked --extra dev --extra reporting \
    && .venv/bin/python -m build --no-isolation --wheel --outdir /dist \
    && uv export --locked --no-dev --extra reporting --no-emit-project \
       --format requirements.txt --output-file /dist/requirements.lock

FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 65532 jbf \
    && useradd --system --uid 65532 --gid 65532 --home-dir /nonexistent jbf \
    && mkdir -p /app/outputs /app/reports \
    && chown -R 65532:65532 /app

COPY --from=builder /dist/requirements.lock /tmp/requirements.lock
COPY --from=builder /dist/jailbreak_framework-*.whl /tmp/
COPY --from=builder /src/config.yaml /app/config.yaml

RUN python -m pip install --require-hashes -r /tmp/requirements.lock \
    && python -m pip install --no-deps /tmp/jailbreak_framework-*.whl \
    && rm -f /tmp/requirements.lock /tmp/jailbreak_framework-*.whl

USER 65532:65532

VOLUME ["/app/outputs", "/app/reports"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "main", "health", "--profile", "production"]

ENTRYPOINT ["python", "-m", "main"]
CMD ["--help"]
