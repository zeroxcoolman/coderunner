# Use a slim Python image
FROM python:3.11-slim

# Install compilers and runtimes
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \                          # C++ compiler
    rustc \
    python3 \
    python3-pip \
    golang-go \
    bash \
    build-essential \
    ca-certificates \
    openjdk-17-jdk \               # Java JDK
    nodejs \                      # Node.js runtime
    npm \                         # Node package manager (sometimes needed)
    ruby \                        # Ruby interpreter
    php \                         # PHP interpreter
    swift \                       # Swift compiler/interpreter
    kotlin \                      # Kotlin compiler
    lua5.3 \                      # Lua interpreter (version 5.3)
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
