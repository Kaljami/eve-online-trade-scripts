# Contract scanner: Docker and Unraid

## What runs

The root `docker-compose.yaml` replaces the old, incomplete multi-appraisal
example with a contract-scanner stack:

| Service | Purpose |
| --- | --- |
| `database` | MariaDB, with `eve_data` for contracts and `fuzz` for static data |
| `redis` | Persistent market-price cache |
| `setup` | Creates the schema, imports required Fuzzwork CSV tables, and generates the scanner's static files |
| `scanner` | Runs a scan immediately, then waits 600 seconds after completion before the next scan |
| `browser` | Read-only contract browser on port 5003, served by Gunicorn |

Database and Redis ports are **not published** to the host. Setup must complete
successfully before the scanner and browser start. An exited `setup` container
with exit code **0** is normal. Failures are logged and prevent dependent startup.

The image includes a scanner-specific Python dependency set, not the desktop
keyboard/UI libraries required by other scripts. Python 3.12 is inside the image;
the host only needs Docker Engine and Docker Compose v2 or newer. Outbound HTTPS
access to Docker Hub, PyPI (at build time), Fuzzwork, ESI, and optionally Discord is
required.

## Quick start (Linux)

Run these commands from the repository root:

```sh
cp scanner.env.example scanner.env
```

Edit `scanner.env` and set **both** `SCANNER_DB_PASSWORD` and
`SCANNER_DB_ROOT_PASSWORD` to different, long random passwords. These have no
insecure defaults. Single-quote passwords containing `$` or `#` in the env file.
Do not commit this file or share the output of `docker compose config`, which
contains resolved credentials.

```sh
docker compose --env-file scanner.env config --quiet
docker compose --env-file scanner.env up -d --build
docker compose --env-file scanner.env ps -a
docker compose --env-file scanner.env logs -f setup scanner
```

Open `http://YOUR_SERVER_IP:5003`. Leave time for the first image build, static
data import, market downloads, and initial scan. Large regions can take much
longer than small ones. The browser can be ready while the scanner is still
collecting its first contracts. Start with `SCANNER_REGIONS=Genesis` for a small
trial run, then change it to your desired regions.

Use the provided `scanner.env` explicitly on **every** Compose command so your
existing standalone `.env` does not supply unintended settings. Never run a
second scanner against the same database concurrently.

## Unraid installation

1. In **Settings > Docker**, enable Docker. Use an appdata share on a suitable
   SSD/cache pool if available. Allow several GB of free space for images,
   temporary downloads, databases, and growth; contract history is not pruned.
2. Install **Compose Manager** through **Apps / Community Applications** if your
   Unraid installation does not already provide Compose. In the Unraid terminal,
   confirm `docker compose version` works. This deployment is a multi-container
   Compose project, not a single Add Container template.
3. Keep the source on persistent storage, not under `/tmp` or on the USB boot
   device. From the Unraid terminal:

   ```sh
   mkdir -p /mnt/user/appdata/eve-contract-scanner
   git clone https://github.com/Kaljami/eve-online-trade-scripts.git /mnt/user/appdata/eve-contract-scanner/source
   cd /mnt/user/appdata/eve-contract-scanner/source
   cp scanner.env.example scanner.env
   ```

   If `git` is unavailable, download/extract the repository into that `source`
   directory using another machine or a file manager. Use the revision containing
   this Docker deployment.
4. Edit `scanner.env`, set both passwords, and set:

   ```dotenv
   APPDATA_PATH=/mnt/user/appdata/eve-contract-scanner/data
   WEB_PORT=5003
   WEB_BIND_IP=0.0.0.0
   SCAN_INTERVAL_SECONDS=600
   ```

   Set `WEB_BIND_IP` to the server's LAN address if you want to bind only that
   interface. Choose another unused port if 5003 is occupied. No EVE developer
   application, login session, existing MySQL instance, or existing Redis is needed.
5. In that same `source` directory, run:

   ```sh
   docker compose --env-file scanner.env up -d --build
   docker compose --env-file scanner.env ps -a
   docker compose --env-file scanner.env logs --tail=100 setup scanner
   ```

6. Open `http://UNRAID_LAN_IP:5003`. Containers also appear on Unraid's Docker
   page. Manage their configuration as a Compose stack; editing generated
   containers individually is not persistent.
7. `restart: unless-stopped` restarts the long-running containers after Docker
   restarts, provided they were not manually stopped. If you use Compose Manager
   to autostart/recreate the project, configure its working directory as the
   **repository root** and include `--env-file scanner.env`. Do not simply paste
   the YAML into a different directory: its build context and config mounts are
   relative to the repository.

   Alternatively, an Unraid **User Scripts** script scheduled for array startup
   can reconcile the stack after the array and Docker are available:

   ```sh
   #!/bin/bash
   cd /mnt/user/appdata/eve-contract-scanner/source || exit 1
   docker compose --env-file scanner.env up -d
   ```

   The initial build must already have completed. Enable only one mechanism for
   managing the same Compose project.

## Settings and behavior

Edit `scanner.env`, then apply with:

```sh
docker compose --env-file scanner.env up -d
```

- `SCANNER_REGIONS`: comma-separated, case-sensitive region names, for example
  `The Forge,Domain,Genesis`. Empty uses the script's original region list.
- `SCAN_INTERVAL_SECONDS`: positive integer; delay **after** each completed scan.
  Scans never overlap within a scanner container. Failed scans exit nonzero and
  Docker's restart policy retries them; inspect logs for persistent failures.
- `MINIMUM_PROFIT_PERCENTAGE`, `GOOD_PROFIT_PERCENTAGE`,
  `MINIMUM_PROFIT_ABSOLUTE`, `GOOD_PROFIT_ABSOLUTE`: existing Discord notification
  thresholds, now configurable without rebuilding. Percentages use whole numbers
  such as `25`; absolute amounts are ISK. They do not filter what is saved.
  Existing notification logic measures discount against Jita value; the browser
  displays ROI against purchase price. These are different percentages.
- `SCANNER_DISCORD_WEBHOOK_URL`: optional. Leave empty to collect contracts without
  notifications. Set the sender name/icon and optional role/user tag as described
  in the example env file. No Discord bot token is required.
  Docker uses `SCANNER_DISCORD_*` settings deliberately, so a standalone
  `.env` file's old `discord_*` settings are not inherited.
- Edit [ignore-list.yaml](ignore-list.yaml) to suppress matching top-item names
  in notifications. Wildcards such as `"* Blueprint"` are supported. After editing,
  run `docker compose --env-file scanner.env up -d --force-recreate scanner` to
  remount the configuration file; it is read when each scan starts. The list does
  not remove contracts from the database.
  This Docker-specific list is separate from the standalone
  `contract_ignore_list.yaml`; copy your desired patterns into it.

Public mode prices only Jita station orders plus the public PLEX market.
Private Perimeter structure pricing, character login, and automatic in-game
window opening are intentionally not part of this deployment. The web UI provides
an EVE contract-link string to copy into the in-game notepad instead.

Market prices refresh every two hours; blueprint profitability refreshes every
24 hours. Static data imports automatically on first startup and can be refreshed
manually below. Item names, blueprint groups, rig IDs, and packaged volumes are
generated from the same imported data. No local cache or SDE files are baked in.

Contracts are marked expired when their scheduled ESI expiration time passes.
Sold/deleted contracts can therefore remain marked active until their scheduled
expiry; this deployment does **not** download EVE Ref's large contract archive.
Prices and blueprint profits are estimates at discovery time. Check availability,
taxes, hauling risks, blueprint assumptions, and actual market liquidity in-game.

The browser supports region, profit, volume, blueprint, status, and discovery-date
filters; it shows 100 results per page. Expired history is available by selecting
the status and "Any time" discovery period. Contents are available by clicking a
contract ID, even if the contract is no longer available in-game.

## Persistence and backup

Everything writable is under `APPDATA_PATH`:

| Directory | Contents |
| --- | --- |
| `mysql` | Both databases, contracts, saved item contents, and initialization marker |
| `redis` | Redis append-only persistence |
| `static` | Generated static-data files |
| `cache` | Redundant disk caches |
| `logs` | Scanner logs (10 MiB each, three rotated backups) |

Keep the source directory, `scanner.env`, and `ignore-list.yaml` too. Docker
console log retention follows your Docker/Unraid logging configuration. Database
history grows indefinitely; monitor appdata space and include it in your backup
plan.

For a consistent filesystem backup, stop this stack first:

```sh
docker compose --env-file scanner.env stop
# Back up APPDATA_PATH and your configuration using your normal backup tool.
docker compose --env-file scanner.env up -d
```

Alternatively use MariaDB-aware database backups. Do not copy live database files
as if they were a consistent backup. Protect backups because configuration can
contain a Discord webhook and database passwords.

`docker compose --env-file scanner.env down` removes this project's containers
and network but **keeps** bind-mounted appdata. Do not delete the appdata share.
Database passwords in `scanner.env` initialize a **new** database only; changing
them later also requires changing the matching MariaDB account passwords.

This stack initializes fresh databases. It does not automatically migrate an
arbitrary existing scanner database; back up and validate its schema before any
manual import.

## Updates and maintenance

From the repository root, after backing up:

```sh
git pull --ff-only
docker compose --env-file scanner.env build
docker compose --env-file scanner.env up -d
```

To explicitly refresh MariaDB/Redis within the configured release series:

```sh
docker compose --env-file scanner.env pull database redis
docker compose --env-file scanner.env up -d
```

To refresh static data, stop readers first so no scan sees partially imported
tables:

```sh
docker compose --env-file scanner.env stop scanner browser
docker compose --env-file scanner.env run --rm setup python containerization/contract-scanner/service.py setup --refresh-static
# Continue only if setup exited successfully.
docker compose --env-file scanner.env up -d
```

To run one scan manually without overlapping the scheduled scanner:

```sh
docker compose --env-file scanner.env stop scanner
docker compose --env-file scanner.env run --rm scanner python containerization/contract-scanner/service.py scan-once
docker compose --env-file scanner.env up -d scanner
```

## Troubleshooting and access

- Check `docker compose --env-file scanner.env ps -a`, then
  `docker compose --env-file scanner.env logs --tail=100 setup scanner browser database redis`.
- Setup failures: check outbound HTTPS/DNS, appdata permissions/free space, and
  credentials. The importer validates HTTP errors and empty tables; an incomplete
  import is retried on the next setup. Fix the cause and run `up -d` again.
- Scanner restarts: check the exception in its logs. Failed database saves are
  retried three times, then fail the scan. A region's contracts and item contents
  are committed together so a failed item insert does not hide them from retries.
- Empty UI: setup may be done before the first scan finishes, filters may exclude
  all results, or the chosen regions may have no profitable contracts. Reset the
  filters, select "Any time", and check the scanner logs.
- Health endpoint: `http://YOUR_SERVER_IP:5003/healthz` returns `{"status":"ok"}`
  only if the browser can connect to MariaDB.
- This is an **unauthenticated LAN-only browser**, not an Internet-facing service.
  Do not forward its port publicly. Use a VPN or an authenticated TLS reverse
  proxy for remote access. The containers trust their private Compose network;
  neither database service is exposed to the LAN.

## Focused regression tests

With the stack built and initialized:

```sh
docker compose --env-file scanner.env run --rm --no-deps browser python -m unittest discover -s containerization/contract-scanner -p test_runtime.py -v
```

Tests use temporary files, mocks, and SQLite; they do not scan ESI or post Discord
notifications. They cover public market selection, cache fallback, generated
static-file compatibility, failure propagation, atomic persistence, empty regions,
and browser filters/escaping/contents.
