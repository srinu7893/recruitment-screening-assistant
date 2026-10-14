FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates poppler-utils tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY screening ./screening
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["python", "-m", "screening.server", "--host", "0.0.0.0"]
