# syntax=docker/dockerfile:1
#
# Railway wrapper around the official No-Code Architects Toolkit image.
# Keep the upstream image pinned by digest for reproducible deploys.
FROM stephengpope/no-code-architects-toolkit:latest@sha256:4b4e8702f9e4538280cabe32e850965cb988923aad8731c721d7922abbae3b6f

USER root

COPY --chown=appuser:appuser railway_app.py railway_storage.py /app/
COPY --chmod=0755 entrypoint.sh /usr/local/bin/nca-railway-entrypoint

USER appuser
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GUNICORN_WORKERS=1 \
    GUNICORN_TIMEOUT=600 \
    GUNICORN_KEEPALIVE=80 \
    MAX_QUEUE_LENGTH=5 \
    LOCAL_STORAGE_PATH=/tmp/nca-toolkit

EXPOSE 8080

CMD ["/usr/local/bin/nca-railway-entrypoint"]
