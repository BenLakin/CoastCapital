FROM python:3.11-slim

LABEL maintainer="CoastCapital Finance Platform"
LABEL description="FinanceAgent - World Class Stock Trading Platform"

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p logs models_cache

# Non-root user for security
RUN useradd -m -u 1000 financeapp && \
    chown -R financeapp:financeapp /app
USER financeapp

# Expose port
EXPOSE 5000

# Entrypoint
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--log-level", "info", "wsgi:app"]
