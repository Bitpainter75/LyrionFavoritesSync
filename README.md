# 🎵 lyrion-sync

> Automatically syncs favorite albums from **Lyrion Music Server** to a local directory — packaged as a Docker container with a configurable cron schedule.

![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How It Works

```
Lyrion Music Server (LMS)
        │
        │  JSON-RPC API
        ▼
  ┌─────────────┐
  │   sync.py   │  1. Load all albums & build index
  │             │  2. Fetch favorite albums for player
  │             │  3. Resolve track URLs per album
  │             │  4. Write rsync filter playlist
  └──────┬──────┘
         │
         │  rsync --filter
         ▼
  Music source directory  ──►  Sync target directory
```

The container runs continuously and executes `sync.py` on the configured cron schedule. If the LMS is unreachable at the time of execution, the run is silently skipped — the next cron trigger will try again automatically.

---

## Requirements

- Docker & Docker Compose
- Lyrion Music Server (LMS) reachable on the network

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Bitpainter75/lyrion-sync.git
cd lyrion-sync

# 2. Edit docker-compose.yml  →  set LMS IP, paths, cron schedule
nano docker-compose.yml

# 3. Build and start the container
docker compose up -d --build

# 4. Follow live logs
docker compose logs -f
```

On first start — if `SYNC_ON_START=true` (default) — a sync runs immediately. After that, the cron schedule takes over.

---

## Repository Structure

```
lyrion-sync/
├── sync.py            # Main script: LMS query → playlist → rsync
├── entrypoint.sh      # Container entry point: cron setup + optional immediate run
├── Dockerfile         # Python 3.12 Slim + rsync + cron
├── docker-compose.yml # All parameters configured as environment variables
├── requirements.txt   # Python dependencies (only: requests)
└── README.md
```

---

## Configuration

All parameters are set as **environment variables** in `docker-compose.yml` — no rebuild required after changes.

### Lyrion Music Server

| Variable        | Default                 | Description                          |
|-----------------|-------------------------|--------------------------------------|
| `LMS_HOST`      | `http://10.3.3.3:9002` | LMS URL including port               |
| `LMS_PLAYER_ID` | `30:30:30:30:30:30`     | MAC address / player ID of the client |
| `LMS_TIMEOUT`   | `10`                    | HTTP timeout in seconds              |

### Scheduling

| Variable        | Default       | Description                             |
|-----------------|---------------|-----------------------------------------|
| `CRON_SCHEDULE` | `0 3 * * *`   | Cron expression (default: daily 03:00)  |
| `SYNC_ON_START` | `true`        | Run a sync immediately on container start |

#### Cron Examples

| Expression       | Meaning                     |
|------------------|-----------------------------|
| `0 3 * * *`      | Every day at 03:00          |
| `*/30 * * * *`   | Every 30 minutes            |
| `0 */6 * * *`    | Every 6 hours               |
| `0 2 * * 0`      | Every Sunday at 02:00       |

> **Tip:** Generate cron expressions interactively at [crontab.guru](https://crontab.guru)

---

## Volumes

Host paths are mapped to container paths in `docker-compose.yml`:

```yaml
volumes:
  - /host/path/music:/music:ro    # Music source (read-only recommended)
  - /host/path/sync:/sync         # rsync target
  - /host/path/data:/data         # Playlist output + log files
```

> The music source directory is mounted `:ro` (read-only) — the container does not need write access there.

The `/data` directory also contains the log files, one per sync run:

| File                                          | Description                          |
|-----------------------------------------------|--------------------------------------|
| `2026-05-26_14-30-00_lyrion-sync.log` | Example log file for a single run    |

Log files older than 5 days are deleted automatically at the start of each run.

---

## Behavior When LMS Is Unreachable

```
Cron trigger
     │
     ▼
LMS reachable?
  No  ──► exit 0  (silent skip, no error alert)
            │
            └── Cron keeps running, retries on next trigger
  Yes ──► Sync proceeds normally
```

---

## LMS Also Running in Docker?

**Option A – Host network (simplest):**

```yaml
services:
  lyrion-sync:
    network_mode: host
```

**Option B – Shared Docker network:**

```yaml
networks:
  lyrion-sync:
    external: true          # must already exist

services:
  lyrion-sync:
    networks:
      - lms-net
```

Then set `LMS_HOST` to the LMS container name, e.g. `http://lms:9002`.

---

## Useful Commands

```bash
# Check container status
docker compose ps

# Follow live logs
docker compose logs -f

# Trigger a sync immediately (without waiting for cron)
docker compose exec lyrion-sync python /app/sync.py

# Restart after configuration changes
docker compose up -d

# Stop the container
docker compose down
```

---

## Sync Process in Detail

1. **Reachability check** — HTTP GET to `LMS_HOST`. On failure: exit 0, skip run.
2. **Album index** — All albums in LMS are loaded via JSON-RPC and indexed as `favorites_url → album_id`.
3. **Favorites** — The favorites list of the configured player is fetched (`want_url:1`).
4. **Track URLs** — For each favorite album, track URLs are resolved (`tags:u`).
5. **Write playlist** — An rsync filter file is generated:
   ```
   + */
   + *[*10]
   + /Artist/Album/track.flac
   ...
   - *
   ```
6. **UTF-8 BOM** is stripped via `sed` for rsync compatibility.
7. **rsync** — Syncs `MUSIC_BASE_PATH` → `MUSIC_SYNC_PATH` using the playlist (`--delete-excluded`, `--prune-empty-dirs`).

---

## License

MIT — see [LICENSE](LICENSE)
