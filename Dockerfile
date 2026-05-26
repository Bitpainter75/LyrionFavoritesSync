FROM python:3.12-slim

# System-Tools: rsync + cron + sed
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        rsync \
        cron \
        procps \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python-Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Skript
COPY sync.py .

# Cron-Wrapper: liest CRON_SCHEDULE zur Laufzeit aus der Umgebung
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Daten-Verzeichnis für die Playlist
RUN mkdir -p /data

ENTRYPOINT ["/entrypoint.sh"]
