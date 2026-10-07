FROM python:3.12-slim

# ffmpeg para video y la fuente gruesa de las piezas (Inter Black)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-inter fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 ENTORNO=produccion
# Render define PORT; el trabajador sobrescribe este comando (ver render.yaml)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
