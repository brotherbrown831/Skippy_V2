FROM node:20-slim

# Install build tools for native module compilation and git (required by npm for some deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 make g++ git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package manifests, lock file, and npm config for layer caching
COPY package.json package-lock.json .npmrc ./

# Install dependencies using the lock file (deterministic)
RUN npm ci

# Copy application source
COPY src/ ./src/

# Create session directory (will be mounted as a Docker volume)
RUN mkdir -p /app/sessions

# Run as non-root user for security
RUN addgroup --system skippy && adduser --system --ingroup skippy skippy
RUN chown -R skippy:skippy /app
USER skippy

CMD ["node", "src/index.js"]
