# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm

ARG NCA_UPSTREAM_COMMIT=d9bb5679e203e6b5d3b3c2b9ab848a289c645024
ARG TORCH_VERSION=2.6.0

LABEL org.opencontainers.image.title="No-Code Architects Toolkit for Railway" \
      org.opencontainers.image.source="https://github.com/hallcyn/no-code-architects-toolkit" \
      org.opencontainers.image.licenses="GPL-2.0-or-later" \
      io.hallcyn.nca.upstream="https://github.com/stephengpope/no-code-architects-toolkit" \
      io.hallcyn.nca.upstream-commit="${NCA_UPSTREAM_COMMIT}"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    XDG_CACHE_HOME=/app/cache \
    WHISPER_CACHE_DIR=/app/cache/whisper \
    PORT=8080 \
    GUNICORN_WORKERS=1 \
    GUNICORN_TIMEOUT=600 \
    GUNICORN_KEEPALIVE=80 \
    MAX_QUEUE_LENGTH=5 \
    LOCAL_STORAGE_PATH=/tmp/nca-toolkit

# Fetch the exact upstream source revision while keeping git/build metadata out
# of the resulting image. Debian's FFmpeg build provides the media stack needed
# by NCA without shipping an entire CUDA toolchain.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fontconfig \
        fonts-liberation \
        git \
    && git init /app \
    && git -C /app remote add origin https://github.com/stephengpope/no-code-architects-toolkit.git \
    && git -C /app fetch --depth 1 origin "${NCA_UPSTREAM_COMMIT}" \
    && git -C /app checkout --detach FETCH_HEAD \
    && test "$(git -C /app rev-parse HEAD)" = "${NCA_UPSTREAM_COMMIT}" \
    && rm -rf /app/.git \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep PyTorch explicitly CPU-only. Installing it first satisfies both the
# upstream `torch` requirement and openai-whisper without pulling NVIDIA/CUDA
# wheels into a CPU-only Railway service.
RUN sed -E '/^(torch|openai-whisper)$/d' requirements.txt > /tmp/nca-requirements.txt \
    && python -m pip install --upgrade pip \
    && python -m pip install \
        "torch==${TORCH_VERSION}" \
        --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r /tmp/nca-requirements.txt \
    && python -m pip install openai-whisper playwright jsonschema \
    && rm -f /tmp/nca-requirements.txt

# Playwright needs its browser plus a small set of system libraries. Keeping
# the shared browser outside a user's home makes it readable by the runtime
# user and avoids per-user duplication.
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/ms-playwright \
    && mkdir -p /usr/share/fonts/custom \
    && cp -a /app/fonts/. /usr/share/fonts/custom/ \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/* /tmp/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p "${XDG_CACHE_HOME}" "${WHISPER_CACHE_DIR}" "${LOCAL_STORAGE_PATH}" \
    && chown -R appuser:appuser /app "${XDG_CACHE_HOME}" "${LOCAL_STORAGE_PATH}"

COPY --chown=appuser:appuser railway_app.py railway_storage.py /app/
COPY --chmod=0755 entrypoint.sh /usr/local/bin/nca-railway-entrypoint

USER appuser

# OpenAI Whisper resolves its default download directory from XDG_CACHE_HOME.
# NCA calls whisper.load_model("base") without a custom path, so preloading the
# model here makes production calls reuse this exact baked checkpoint.
RUN python -c "import whisper; whisper.load_model('base')"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8080') + '/healthz', timeout=3)" || exit 1

CMD ["/usr/local/bin/nca-railway-entrypoint"]
