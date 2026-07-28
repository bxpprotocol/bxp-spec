## BXP Protocol Reference Node — Docker image
## Usage:
##   docker build -t bxp-node .
##   docker run -p 5000:5000 -e AQICN_TOKEN=your_token \
##              -v bxp_data:/app/reference-server bxp-node

FROM python:3.12-slim

LABEL org.opencontainers.image.title="BXP Protocol Reference Node"
LABEL org.opencontainers.image.description="Open standard for atmospheric exposure data"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/bxpprotocol/bxp-spec"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY reference-server/requirements.txt reference-server/
RUN pip install --no-cache-dir -r reference-server/requirements.txt

# Copy application
COPY reference-server/ reference-server/
COPY sdk/ sdk/
COPY cli/ cli/
COPY spec/ spec/
COPY datasets/ datasets/
COPY README.md .

WORKDIR /app/reference-server

# SQLite database lives in a volume
VOLUME ["/app/reference-server"]

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/bxp/v2/health || exit 1

ENV BXP_NODE_ID=bxp-docker-node
ENV BXP_NODE_TYPE=reference

CMD ["python", "server.py"]
