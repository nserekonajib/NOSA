FROM python:3.12

WORKDIR /app

# Install system dependencies for pycairo and other libs
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libcairo2-dev \
    libgirepository1.0-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY r.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r r.txt

# Copy project files
COPY . .

CMD ["python", "app.py"]
