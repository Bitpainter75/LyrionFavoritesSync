#!/usr/bin/env python3
"""
LMS Favorites → rsync Playlist Sync
Liest Favoriten-Alben aus dem Lyrion Music Server und erstellt
eine rsync-Filter-Playlist, danach werden die Dateien synchronisiert.
"""

import os
import sys
import re
import glob
import subprocess
import urllib.parse
import logging
from datetime import datetime, timedelta
import requests

# ---------------------------------------------------------------------------
# Konfiguration aus Environment-Variablen
# ---------------------------------------------------------------------------
LMS_HOST        = os.environ.get("LMS_HOST",        "http://10.3.3.34:9002")
LMS_PLAYER_ID   = os.environ.get("LMS_PLAYER_ID",   "38:05:25:37:c0:40")
PLAYLIST_FILE   = os.environ.get("PLAYLIST_FILE",   "/data/playlist.txt")
MUSIC_BASE_PATH = os.environ.get("MUSIC_BASE_PATH", "/music")
MUSIC_SYNC_PATH = os.environ.get("MUSIC_SYNC_PATH", "/sync")
LMS_TIMEOUT     = int(os.environ.get("LMS_TIMEOUT", "10"))   # Sekunden

LOG_DIR = os.path.dirname(PLAYLIST_FILE)

# ---------------------------------------------------------------------------
# Logging  — stdout + pro Lauf eine neue Datei mit Zeitstempel (5 Tage)
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(message)s"
LOG_DATE   = "%Y-%m-%d %H:%M:%S"

def setup_logging() -> None:
    """Legt eine neue Log-Datei für diesen Lauf an und räumt alte auf."""
    os.makedirs(LOG_DIR, exist_ok=True)

    # Dateiname: 2026-05-26_14-30-00_lyrion-sync.log
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file  = os.path.join(LOG_DIR, f"{timestamp}_lyrion-sync.log")

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE)

    file_handler    = logging.FileHandler(log_file, encoding="utf-8")
    console_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

    # Alte Log-Dateien löschen (älter als 5 Tage)
    cutoff = datetime.now() - timedelta(days=5)
    for old in glob.glob(os.path.join(LOG_DIR, "*_lyrion-sync.log")):
        try:
            # Datum aus dem Dateinamen parsen: YYYY-MM-DD_HH-MM-SS_...
            basename  = os.path.basename(old)
            date_part = "_".join(basename.split("_")[:2])   # "2026-05-26_14-30-00"
            file_dt   = datetime.strptime(date_part, "%Y-%m-%d_%H-%M-%S")
            if file_dt < cutoff:
                os.remove(old)
                logging.getLogger("lyrion-sync").info("Altes Log gelöscht: %s", basename)
        except (ValueError, OSError):
            pass   # unbekanntes Format → ignorieren

setup_logging()
log = logging.getLogger("lyrion-sync")

JSONRPC_URL = f"{LMS_HOST}/jsonrpc.js"
HEADERS     = {"Content-Type": "application/json"}

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def lms_post(payload: dict) -> dict:
    """Sendet einen JSON-RPC-Request an den LMS. Wirft bei Fehler eine Exception."""
    resp = requests.post(
        JSONRPC_URL,
        headers=HEADERS,
        json=payload,
        timeout=LMS_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def check_lms_reachable() -> bool:
    """Gibt True zurück wenn der LMS erreichbar ist, sonst False."""
    try:
        requests.get(LMS_HOST, timeout=LMS_TIMEOUT)
        return True
    except requests.exceptions.RequestException as exc:
        log.warning("LMS nicht erreichbar (%s): %s", LMS_HOST, exc)
        return False


def get_album_count() -> int:
    data = lms_post({
        "id": 1, "method": "slim.request",
        "params": ["", ["albums", 0, 0, "tags:la"]],
    })
    return int(data["result"]["count"])


def get_all_albums(count: int) -> list[dict]:
    data = lms_post({
        "id": 2, "method": "slim.request",
        "params": ["", ["albums", 0, count, "tags:la"]],
    })
    return data["result"].get("albums_loop", [])


def get_favorite_count() -> int:
    data = lms_post({
        "id": 3, "method": "slim.request",
        "params": [LMS_PLAYER_ID, ["favorites", "items", 0, 0]],
    })
    return int(data["result"]["count"])


def get_favorites(count: int) -> list[dict]:
    data = lms_post({
        "id": 4, "method": "slim.request",
        "params": [LMS_PLAYER_ID, ["favorites", "items", 0, count, "want_url:1"]],
    })
    return data["result"].get("loop_loop", [])


def get_tracks_for_album(album_id: str) -> list[dict]:
    data = lms_post({
        "id": 5, "method": "slim.request",
        "params": [LMS_PLAYER_ID, ["tracks", 0, 999, f"album_id:{album_id}", "tags:u"]],
    })
    return data["result"].get("titles_loop", [])


def build_album_url_index(albums: list[dict]) -> dict[str, str]:
    """Erstellt ein Mapping favorites_url → album_id."""
    index: dict[str, str] = {}
    for album in albums:
        url = album.get("favorites_url", "")
        aid = str(album.get("id", ""))
        if url and aid:
            index[url] = aid
    return index

# ---------------------------------------------------------------------------
# Haupt-Logik
# ---------------------------------------------------------------------------

def run_sync() -> None:
    log.info("=" * 60)
    log.info("Sync-Lauf gestartet")
    log.info("=" * 60)

    # 1 — LMS-Erreichbarkeit prüfen
    if not check_lms_reachable():
        log.error("LMS nicht erreichbar – Sync wird übersprungen.")
        sys.exit(0)   # Exit 0 → Cron läuft weiter, kein Fehler-Alarm

    log.info("LMS erreichbar: %s", LMS_HOST)

    # 2 — Alle Alben laden und Index aufbauen
    album_count = get_album_count()
    log.info("Alben in LMS gesamt: %d", album_count)

    all_albums  = get_all_albums(album_count)
    url_to_id   = build_album_url_index(all_albums)
    log.info("Album-Index aufgebaut: %d Einträge", len(url_to_id))

    # 3 — Favoriten laden
    fav_count = get_favorite_count()
    log.info("LMS Favoriten gesamt: %d", fav_count)

    favorites = get_favorites(fav_count)
    log.info("Favoriten-Alben geladen: %d", len(favorites))

    # 4 — Playlist-Datei schreiben
    playlist_dir = os.path.dirname(PLAYLIST_FILE)
    if playlist_dir:
        os.makedirs(playlist_dir, exist_ok=True)

    lines: list[str] = ["+ */\n", "+ *[*10]\n"]  # Verzeichnisse durchlassen

    skipped_albums  = 0
    skipped_tracks  = 0
    track_count     = 0

    for fav in favorites:
        album_url  = fav.get("url", "")
        album_name = fav.get("name", "(unbekannt)")
        log.info("Verarbeite Album: %s", album_name)

        album_id = url_to_id.get(album_url, "")
        if not album_id:
            log.warning("  Keine album_id gefunden, überspringe: %s", album_name)
            skipped_albums += 1
            continue

        log.info("  Album ID: %s", album_id)
        tracks = get_tracks_for_album(album_id)
        log.info("  %d Tracks gefunden", len(tracks))

        for track in tracks:
            track_url = track.get("url", "")
            if not track_url.startswith("file://"):
                log.debug("  Überspringe (kein file://): %s", track_url)
                skipped_tracks += 1
                continue

            # file:///music/T/Toxikull/... → T/Toxikull/...
            rel_path = track_url.replace("file:///music/", "", 1)
            rel_path = urllib.parse.unquote(rel_path)
            lines.append(f"+ /{rel_path}\n")
            track_count += 1

    lines.append("- *\n")

    with open(PLAYLIST_FILE, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    # UTF-8-BOM entfernen (falls vorhanden)
    subprocess.run(
        ["sed", "-i", "1s/^\xef\xbb\xbf//", PLAYLIST_FILE],
        check=False,
    )

    log.info(
        "Playlist geschrieben: %s  (%d Tracks, %d Alben übersprungen, %d Tracks übersprungen)",
        PLAYLIST_FILE, track_count, skipped_albums, skipped_tracks,
    )

    # 5 — Sicherheitscheck
    if not os.path.exists(PLAYLIST_FILE):
        log.error("Fehler: Playlist-Datei konnte nicht erstellt werden: %s", PLAYLIST_FILE)
        sys.exit(1)

    with open(PLAYLIST_FILE, encoding="utf-8") as fh:
        content = fh.read()

    total_tracks = len(re.findall(r"^\+ /", content, re.MULTILINE))
    log.info("Fertig: %d Tracks in der Playlist.", total_tracks)

    # 6 — rsync ausführen
    rsync_cmd = [
        "rsync",
        "-av", "--stats",
        "--size-only",
        "--delete-excluded",
        f"--filter=. {PLAYLIST_FILE}",
        f"{MUSIC_BASE_PATH}/",
        f"{MUSIC_SYNC_PATH}/",
        "--prune-empty-dirs",
    ]
    log.info("Starte rsync …")
    result = subprocess.run(
        rsync_cmd,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        log.info("rsync stdout:\n%s", result.stdout)
    if result.stderr:
        log.warning("rsync stderr:\n%s", result.stderr)
    if result.returncode != 0:
        log.error("rsync beendet mit Exit-Code %d", result.returncode)
        sys.exit(result.returncode)

    log.info("Sync abgeschlossen.")
    log.info("=" * 60)


if __name__ == "__main__":
    run_sync()
