FROM python:3.11-slim

# Install system dependencies & Eclipse SUMO
RUN apt-get update && apt-get install -y --no-install-recommends \
    sumo \
    sumo-tools \
    && rm -rf /var/lib/apt/lists/*

ENV SUMO_HOME=/usr/share/sumo
ENV PATH="${SUMO_HOME}/bin:${PATH}"

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

EXPOSE 8000

CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "8000"]
