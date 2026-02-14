FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy everything needed for install
COPY pyproject.toml .
COPY src/ ./src/

# Install the package (includes dependencies)
RUN pip install --no-cache-dir .

# Run the application
CMD ["uvicorn", "skippy.main:app", "--host", "0.0.0.0", "--port", "8000"]
