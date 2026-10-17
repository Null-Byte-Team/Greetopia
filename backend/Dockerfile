FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/storage/smart_irrigation.db \
    PHOTO_DIR=/app/storage/photos \
    PORT=5000

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY entrypoint.sh ./entrypoint.sh
RUN mkdir -p /app/storage/photos && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','5000')+'/health/ready', timeout=3)" || exit 1
ENTRYPOINT ["/app/entrypoint.sh"]
