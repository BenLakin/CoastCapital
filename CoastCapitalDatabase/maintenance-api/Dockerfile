FROM python:3.12-slim

WORKDIR /app

# Install MySQL client tools for shell-level fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
      default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /app/logs

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
