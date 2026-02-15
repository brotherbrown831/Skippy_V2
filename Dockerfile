FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy everything needed for install
COPY pyproject.toml .
COPY src/ ./src/
COPY tests/ ./tests/

# Install the package (includes dependencies and dev tools for testing)
RUN pip install --no-cache-dir ".[dev]"

# Run the application
CMD ["uvicorn", "skippy.main:app", "--host", "0.0.0.0", "--port", "8000"]
