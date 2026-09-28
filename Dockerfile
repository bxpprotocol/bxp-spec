## BXP Protocol Reference Node — Docker image
## Usage:
##   docker build -t bxp-node .
##   docker run -p 5000:5000 -v bxp_data:/data bxp-node
## Configuration: see .env.example (pass with --env-file .env).

FROM python:3.12-slim

LABEL org.opencontainers.image.title="BXP Protocol Reference Node"
LABEL org.opencontainers.image.description="Open standard for atmospheric exposure data"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/bxpprotocol/bxp-spec"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BXP_DB_PATH=/data/bxp_data.db \
    BXP_NODE_ID=bxp-docker-node \
    BXP_NODE_TYPE=reference

# Unprivileged user; /data is the only writable location.
RUN useradd --system --uid 10001 --home-dir /app bxp \
    && mkdir -p /data && chown bxp /data

WORKDIR /app

# Install Python deps first (layer cache)
COPY reference-server/requirements.txt reference-server/
RUN pip install --no-cache-dir -r reference-server/requirements.txt

# Application code (the server imports the SDK's bxp_binary module)
COPY reference-server/ reference-server/
COPY sdk/python/ sdk/python/

WORKDIR /app/reference-server
USER bxp

# Data lives in a volume that does NOT overlap the code, so a new image
# always runs new code while keeping the existing database.
VOLUME ["/data"]
EXPOSE 5000

# Uses Python (already in the image) instead of installing curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/bxp/v2/health', timeout=4).status == 200 else 1)"

CMD ["python", "server.py"]
