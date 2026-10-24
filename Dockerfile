FROM python:3.11-slim

# OpenCV (used by the OCR engine) needs these system libraries
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# Customer data and logs live on mounted volumes, never inside the image
ENV DATA_DIR=/data LOG_DIR=/logs APP_ENV=production
RUN useradd --create-home appuser && mkdir -p /data /logs && chown appuser /data /logs
USER appuser

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["python", "-m", "app.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
