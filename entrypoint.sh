#!/bin/sh
set -e

# Standardwert falls nicht gesetzt
CRON_SCHEDULE="${CRON_SCHEDULE:-0 3 * * *}"

echo "Cron-Schedule: ${CRON_SCHEDULE}"

# Umgebungsvariablen als KEY="VALUE"-Zeilen in die Crontab schreiben.
# Cron unterstützt das nativ – kein xargs, kein Splitting-Problem.
ENV_LINES=""
while IFS='=' read -r key value; do
    # Nur relevante Variablen übernehmen, interne Shell-Vars überspringen
    case "$key" in
        LMS_HOST|LMS_PLAYER_ID|LMS_TIMEOUT|PLAYLIST_FILE|MUSIC_BASE_PATH|MUSIC_SYNC_PATH|SYNC_ON_START|CRON_SCHEDULE|PATH|HOME|LANG|TZ)
            ENV_LINES="${ENV_LINES}${key}=\"${value}\"
"
            ;;
    esac
done <<EOF
$(printenv)
EOF

# Crontab-Datei erzeugen: erst Env-Variablen, dann der Job
{
    printf '%s' "$ENV_LINES"
    echo "${CRON_SCHEDULE} root python /app/sync.py >> /proc/1/fd/1 2>&1"
} > /etc/cron.d/lyrion-sync

chmod 0644 /etc/cron.d/lyrion-sync

echo "Crontab geschrieben:"
cat /etc/cron.d/lyrion-sync

# Einmaliger Sofort-Lauf beim Start (optional, per SYNC_ON_START steuerbar)
if [ "${SYNC_ON_START:-true}" = "true" ]; then
    echo "SYNC_ON_START aktiv – führe Sync sofort aus …"
    python /app/sync.py || true
fi

# Cron im Vordergrund starten (Logs landen in stdout → docker logs)
exec cron -f
