# Dockerfile for SmartCrop AI gRPC Microservice
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=50051

WORKDIR /app

# Install minimal OS dependencies for PyTorch & OpenCV/Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and PyTorch model
COPY . .

# Expose gRPC port
EXPOSE 50051

# Start the gRPC server
CMD ["python", "server.py"]
