
# Use Python 3.14 to match our development environment.
FROM python:3.14-slim

# Prevent Python from writing .pyc files and buffer-freeze in logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory inside the container.
WORKDIR /app

# Copy dependency definitions first for Docker layer caching.
COPY requirements.txt .

# Install production dependencies without retaining pip's cache.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI application.
COPY app/ ./app/

# Run the API as a non-root user.
RUN useradd --create-home appuser
USER appuser

# Document the port on which Uvicorn listens.
EXPOSE 8000

# Listen on all container interfaces, not just localhost.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
