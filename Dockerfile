# ── Intellifox AI — Production Dockerfile (Vertex AI / GCP only) ─────────────
FROM python:3.11-slim

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install Python deps first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .
COPY index.html .
COPY banking_knowledge.json .

# Fix ownership
RUN chown -R appuser:appuser /app
USER appuser

# Cloud Run sets PORT automatically; these are production defaults
ENV PORT=8080 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_RELOAD=0 \
    RUN_ENV=production

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "main.py"]
