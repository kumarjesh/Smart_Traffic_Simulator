FROM python:3.11-slim

# Install system dependencies & Eclipse SUMO
RUN apt-get update && apt-get install -y --no-install-recommends \
    sumo \
    sumo-tools \
    && rm -rf /var/lib/apt/lists/*

ENV SUMO_HOME=/usr/share/sumo
ENV PATH="${SUMO_HOME}/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV MALLOC_ARENA_MAX=2

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
