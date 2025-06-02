# DNS Server Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY config/ config/
COPY web/ web/

# Install gosu for potential privilege dropping (keep for future use)
RUN apt-get update && apt-get install -y gosu && rm -rf /var/lib/apt/lists/*

# Create directories with permissions that work for any user
RUN mkdir -p logs cache && \
    chmod -R 777 logs cache && \
    chmod -R 755 /app

# Expose ports
EXPOSE 9953/udp 9953/tcp 9980/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9980/api/status || exit 1

# Default command
CMD ["python", "src/dns_server/main.py", "--config", "config/default.yaml"]
