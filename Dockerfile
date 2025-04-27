# Using slim-bookworm for a smaller image size
FROM python:3.10-slim-bookworm as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for psycopg2 and potentially others
# Using --no-install-recommends reduces image size
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    # Clean up APT when done
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
# Using --no-cache-dir reduces image size
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user and group for security
RUN addgroup --system app && adduser --system --group app

# Switch to the non-root user
USER app

# Copy the application source code into the container
# Ensure correct ownership if needed (should be inherited if USER is set before COPY)
COPY ./src ./src

# Default command (can be overridden in docker-compose.yml)
# Expose the port the app runs on (informational)
EXPOSE 8000

# Default command to run the API server
# Use 0.0.0.0 to listen on all interfaces within the container
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
