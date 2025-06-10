# Use a slim Python image
FROM python:3.11-slim

# Install compilers and runtimes
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    rustc \
    python3 \
    python3-pip \
    golang-go \
    bash \
    build-essential \
    ca-certificates \
    php \
    lua5.4 \
    ruby \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (cache dependencies)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy rest of the code
COPY . .

# Default command
CMD ["python", "main.py"]
