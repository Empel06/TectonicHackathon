FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    TRUST_RUNTIME_DIR=/app/runtime \
    DEMO_MODE=true

# Every dependency pinned with a SHA-256 hash (requirements.lock): a tampered package fails the build
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY core/ core/
COPY app/ app/
COPY ui/ ui/
COPY config/ config/
COPY .streamlit/ .streamlit/
COPY data/ data/
COPY tests/ tests/

# Run as an unprivileged user; only the runtime folder (event log) is writable
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/runtime && chown appuser /app/runtime
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false", "--server.enableXsrfProtection=true"]
