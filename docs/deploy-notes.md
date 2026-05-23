# Deploy Notes

## 2026-05-21 — VPS reset baseline

- Host: `138.16.224.55`
- User: `photoflow`
- OS: Ubuntu 22.04.5 LTS

### Read-only audit result

- Running legacy services found: `pure-ftpd`, `redis-server`
- Legacy data tree found: `/srv/photoflow/*`
- No active `nginx`/`apache2` systemd services
- Open ports before cleanup: `21` (FTP), `22` (SSH), `6379` (Redis localhost)

### Actions executed

- Stopped and disabled services:
  - `pure-ftpd`
  - `redis-server`
- Removed legacy data:
  - `/srv/photoflow`
  - `/home/photoflow/app`
- Purged legacy packages:
  - `pure-ftpd`
  - `redis-server`
  - `redis-tools`
- Created clean directories:
  - `/srv/yauza/incoming`
  - `/srv/yauza/originals`
  - `/srv/yauza/backup`
- Created system entities:
  - group `yauza`
  - user `upload` (`/usr/sbin/nologin`, home `/srv/yauza`)
- Applied ownership and permissions:
  - owner: `upload:yauza` for `/srv/yauza/*`
  - mode `775` for `incoming`
  - mode `750` for `originals` and `backup`

### Current state

- Open port: `22` (SSH only)
- Phase 0 complete, Phase 1 (FTP module) started

## 2026-05-21 — FTP module bootstrap (`vsftpd`)

### Actions executed

- Installed package: `vsftpd`
- Configured single FTP user model:
  - user allowlist file `/etc/vsftpd.userlist` contains only `upload`
  - `local_root=/srv/yauza/incoming`
  - `chroot_local_user=YES`
  - `allow_writeable_chroot=YES`
- Configured passive mode:
  - `pasv_min_port=40000`
  - `pasv_max_port=40050`
- Enforced upload-only behavior for FTP commands:
  - `cmds_denied=DELE,RMD,RNFR,RNTO,SITE_CHMOD`
- Fixed PAM shell restriction for service account:
  - added `/usr/sbin/nologin` to `/etc/shells`
- Restarted and enabled `vsftpd`

### Verification

- `vsftpd` is active
- Port `21` is listening
- FTP login as `upload` succeeded
- FTP upload into auto-created subfolder `autotest_cam` succeeded
- FTP delete was blocked with `550 Permission denied`

### Next manual check pending

- FileZilla/camera test: upload 2–3 JPEG to `incoming/test_cam/`

### Manual camera validation (completed)

- Camera created photographer folder automatically: `/srv/yauza/incoming/Otroshko`
- Uploaded files detected:
  - `OTP00621.JPG` (~5.23 MB)
  - `OTP00622.JPG` (~5.28 MB)
- Result: FTP workflow validated end-to-end for camera upload scenario

## 2026-05-22 — Batch watcher smoke test on VPS

### Runtime setup

- Project synced to `/opt/yauza-photofactory`
- Virtualenv created at `/opt/yauza-photofactory/.venv`
- Temporary runtime config created: `/opt/yauza-photofactory/config.yaml`

### Important compatibility note

- VPS system Python is `3.10`, while project metadata currently requires `>=3.11`.
- For smoke test, watcher was launched directly from source via:
  - `PYTHONPATH=/opt/yauza-photofactory/src python -m photofactory.watcher.cli ...`

### Permission fix applied

- First watcher attempt failed with `Permission denied` while moving files from `incoming`.
- Root cause: photographer subfolders were created without group write bit.
- Fixes:
  - `local_umask=002` in `/etc/vsftpd.conf`
  - restart `vsftpd`
  - `chmod -R g+rwX /srv/yauza/incoming`
  - setgid bit on incoming directories to preserve group

### Result

- Watcher `--run-once` finalized batch successfully:
  - `batch_id=20260522093716-d693f102`
  - photographer `Otroshko`
  - files moved: `2`
  - total size: `10514371` bytes
- Files now located at:
  - originals: `/srv/yauza/originals/default/unnamed/Otroshko/20260522093716-d693f102/`
  - backup: `/srv/yauza/backup/Otroshko/20260522093716-d693f102/`
- `incoming/Otroshko` is clean after finalization.

## 2026-05-22 — Python 3.11 + systemd watcher

### Python runtime upgrade

- Installed Python `3.11.15` on VPS from `ppa:deadsnakes/ppa`
- Packages installed: `python3.11`, `python3.11-venv`, `python3.11-dev`
- Recreated project virtualenv with Python 3.11:
  - `/opt/yauza-photofactory/.venv`

### Service setup

- Created systemd unit: `/etc/systemd/system/yauza-watcher.service`
- Service command:
  - `/opt/yauza-photofactory/.venv/bin/photofactory-watcher --config /opt/yauza-photofactory/config.yaml --log-level INFO`
- Enabled and started service:
  - `systemctl enable --now yauza-watcher`
- Status: `active (running)`

### Auto-processing smoke test (service mode)

- Created test file `SMOKE001.JPG` in `/srv/yauza/incoming/WatcherSmoke/`
- Watcher logs confirmed automatic finalize:
  - `Batch finalized: photographer=WatcherSmoke ... files=1`
- File moved to:
  - originals: `/srv/yauza/originals/default/unnamed/WatcherSmoke/20260522094131-d5665550/SMOKE001.JPG`
  - backup: `/srv/yauza/backup/WatcherSmoke/20260522094131-d5665550/SMOKE001.JPG`

## 2026-05-22 — PostgreSQL + Alembic + watcher persistence

### PostgreSQL setup

- Installed packages: `postgresql`, `postgresql-contrib`
- Created role/database:
  - role: `photofactory`
  - database: `photofactory`
- Granted DB privileges to `photofactory`

### Runtime config hardening

- Runtime config moved from `/opt/yauza-photofactory/config.yaml` to `/etc/yauza/config.yaml`
- DB password stored at `/etc/yauza/.db-password`
- `yauza-watcher.service` updated to use:
  - `--config /etc/yauza/config.yaml`

### Migration

- Added dependency `psycopg2-binary` for SQLAlchemy sync engine
- Alembic applied successfully:
  - revision: `20260522_0001`
- Tables present:
  - `photographers`
  - `batches`
  - `photos`
  - `alembic_version`

### Service verification with DB write

- Created smoke input: `/srv/yauza/incoming/DbSmoke/DBSMOKE001.JPG`
- Watcher finalized batch and wrote records to DB:
  - batch key: `20260522095450-125bdcdb`
  - photographer: `DbSmoke`
  - photo: `DBSMOKE001.JPG`

## 2026-05-22 — FastAPI service bootstrap

### API deployment

- Deployed API code to `/opt/yauza-photofactory`
- Installed dependencies into project venv (`photofactory-api` entrypoint)
- Created and enabled systemd service:
  - unit: `/etc/systemd/system/yauza-api.service`
  - command: `photofactory-api --config /etc/yauza/config.yaml`
  - bind: `127.0.0.1:8000`

### Endpoint verification

- `GET /health` returns `{"status":"ok"}`
- `GET /api/batches` returns rows from PostgreSQL
- `GET /api/batches/{batch_id}` returns batch detail with photo list
- `GET /api/batches/{batch_id}/download?cleanup_incoming=true`:
  - returns ZIP (`HTTP 200`)
  - removes residual matching file from `incoming/<photographer>/`

## 2026-05-22 — API authentication (JWT)

### Config and runtime

- Added auth settings in `/etc/yauza/config.yaml`:
  - `auth.username`
  - `auth.password`
  - `auth.jwt_secret`
  - `auth.token_ttl_minutes`
- Stored current API password in `/etc/yauza/.api-auth-password` (root-owned, group `yauza`, mode `640`)
- Restarted `yauza-api` service with updated config

### Verification

- `GET /api/batches` without token returns `401` (`Missing bearer token`)
- `POST /api/auth/token` with valid credentials returns Bearer JWT
- `GET /api/batches` with `Authorization: Bearer <token>` returns data successfully

## 2026-05-22 — Telegram notifier wiring

### Code deployment

- Deployed notifier module to watcher runtime:
  - `notifications/base.py` (Notifier interface)
  - `notifications/telegram.py` (Telegram adapter)
  - `notifications/factory.py` (channel selection / fallback)
- Watcher now calls notifier after batch finalization.

### Runtime status

- `yauza-watcher` restarted successfully.
- Logs confirm fallback mode:
  - `Notifications disabled in config`
- Smoke batch `NotifySmoke` finalized successfully, pipeline unaffected.

### Pending to activate real Telegram delivery

- Set real values in `/etc/yauza/config.yaml`:
  - `notifications.enabled: true`
  - `notifications.telegram.bot_token`
  - `notifications.telegram.default_chat_id`
- Restart `yauza-watcher` and verify message arrives in editor chat.

## 2026-05-22 — Telegram runtime test (blocked by network)

### What was done

- Runtime Telegram credentials applied to `/etc/yauza/config.yaml`
- `yauza-watcher` restarted, notifier initialized as enabled

### Result

- Outbound access from VPS to `api.telegram.org:443` fails:
  - `curl`: timeout / connection failure
  - watcher log: `httpx.ConnectError: [Errno 101] Network is unreachable`
- Batch finalization still completes (pipeline remains functional), but Telegram delivery fails.

### Next required infrastructure step

- Allow outbound HTTPS from VPS to `api.telegram.org` (firewall/security-group/NAT policy).
- After network fix: rerun watcher smoke test and confirm real Telegram message delivery.

## 2026-05-22 — In-App notifications + MAX adapter

### Database/API changes deployed

- Applied migration `20260522_0002` (table `notifications`)
- API endpoint added and verified:
  - `GET /api/notifications` (JWT required)

### Watcher behavior

- On batch finalization watcher now creates `in_app` notification row.
- Smoke test:
  - input folder: `InAppSmoke`
  - output: notification with `kind=batch_finalized`, `channel=in_app`
  - visible via API and direct SQL query.

### MAX/PWA status

- MAX notifier adapter is implemented in code (`webhook` mode), but runtime webhook is not configured yet.
- PWA is registered as optional config channel (future extension point).

## 2026-05-22 — PWA push backend scaffold

### DB + migration

- Applied Alembic migration `20260522_0003`
- New table: `push_subscriptions`

### API endpoints (JWT-protected)

- `GET /api/pwa/public-key`
- `POST /api/pwa/subscriptions`
- `DELETE /api/pwa/subscriptions`

### Smoke test result

- Subscription save/delete API works (`saved` / `deleted`)
- Current runtime VAPID public key is empty (expected, not configured yet)
- Next step: set real VAPID keys and add client-side Service Worker subscription flow.

## 2026-05-22 — PWA VAPID keys configured

### Runtime setup

- Generated VAPID keypair on VPS (project venv)
- Stored private key at:
  - `/etc/yauza/pwa_vapid_private.pem`
- Updated `/etc/yauza/config.yaml`:
  - `notifications.channels: [pwa]`
  - `notifications.pwa.enabled: true`
  - `notifications.pwa.vapid_public_key: <generated>`
  - `notifications.pwa.vapid_private_key: /etc/yauza/pwa_vapid_private.pem`

### Verification

- `yauza-api` and `yauza-watcher` restarted successfully
- `GET /api/pwa/public-key` returns non-empty key
- `POST /api/pwa/test-push` returns `sent=0` when no device subscriptions exist (expected baseline)

## 2026-05-22 — PWA phone test access

- API host switched to `0.0.0.0` in `/etc/yauza/config.yaml` for temporary phone testing.
- `ufw` rule added: allow `8000/tcp`.
- Public check succeeded:
  - `http://138.16.224.55:8000/pwa/test` -> HTTP 200

## 2026-05-22 — HTTPS enabled for PWA

### TLS/Reverse proxy

- Installed: `nginx`, `certbot`, `python3-certbot-nginx`
- Configured nginx reverse proxy:
  - `work.yauzamedia.ru` -> `127.0.0.1:8000`
- Issued Let's Encrypt certificate and enabled redirect to HTTPS.
- Verified page:
  - `https://work.yauzamedia.ru/pwa/test`

### Security cleanup after setup

- API bind returned to `127.0.0.1:8000` (internal only)
- Removed `ufw` allow for `8000/tcp`
- Public access now only via ports `80/443` through nginx

## 2026-05-22 — iPhone PWA push success

### Manual test outcome

- iPhone device subscribed successfully (Apple Push endpoint stored in backend).
- Multiple test push requests returned:
  - `sent=1`
  - `failed=0`
  - `deactivated=0`
- Real notification delivery to iPhone confirmed.

### Current notification posture

- In-App notifications: fully operational.
- PWA push: operational and validated on iPhone.
- External messenger channel (Telegram/MAX): still optional, blocked/disabled per infra constraints.

## 2026-05-22 — Minimal bild dashboard page

### New routes

- `GET /bild` — minimal bild dashboard (HTML)
- `GET /bild-dashboard.js` — client logic for:
  - JWT login/logout
  - In-App notifications polling (`/api/notifications`)
  - push enable/disable
  - test push trigger

### Validation

- Verified over HTTPS:
  - `https://work.yauzamedia.ru/bild` -> HTTP 200
  - `https://work.yauzamedia.ru/bild-dashboard.js` -> HTTP 200

## 2026-05-22 — Bild dashboard UX finish

### Backend/API

- Added `POST /api/notifications/mark-read`:
  - marks all in-app notifications as `read`
- Added `POST /api/dev/smoke-batch`:
  - creates a smoke file in `incoming/<photographer>/`
  - sets mtime in the past to pass silence window quickly
  - lets watcher run real end-to-end flow (not test push)

### Frontend `/bild`

- Added unread counter in meta line (`Непрочитанных: N`)
- Added button "Пометить уведомления прочитанными"
- Added button "Проверка реальной пачкой"

### Validation (VPS)

- `POST /api/notifications/mark-read` -> `{"status":"ok","updated":1}`
- `POST /api/dev/smoke-batch` -> `{"status":"queued", ...}`
- After watcher cycle, `/api/notifications` returned new `BildSmoke` notification with `status="ready"` (real watcher path confirmed).

## 2026-05-22 — MVP bild cabinet + Yandex Disk module

### Migration and services

- Applied migration `20260522_0004`:
  - `batches.broken_files_count`
  - `app_settings` table (`yandex_disk.auto_upload_all`)
- Restarted:
  - `yauza-api`
  - `yauza-watcher`

### API/web additions

- Batch API now returns:
  - `broken_files_count`
  - `daily_sequence`
  - `archive_name`
- Added image endpoint:
  - `GET /api/photos/{photo_id}/content`
- Added Yandex endpoints:
  - `POST /api/batches/{batch_id}/upload-yandex`
  - `GET /api/yandex/auto-upload`
  - `POST /api/yandex/auto-upload`
- Updated `/bild` page:
  - batch cards with gallery
  - metadata line (photographer, captured_at, file_count, broken_files_count, daily_sequence)
  - buttons: "Скачать пакет" and "Загрузить на Я.Диск"
  - checkbox: "Загружать все входящие пакеты на Я.Диск"

### Validation (VPS)

- `POST /api/dev/smoke-batch` queued file for `MvpFinish`.
- Watcher finalized new batch and `/api/batches` returned:
  - `broken_files_count=0`
  - `daily_sequence`
  - archive name like `MvpFinish_20260522_151008_006.zip`
- `/api/batches/{id}` returned `photos[].image_url`.
- `/api/yandex/auto-upload` returned `{"enabled":false}`.
- Manual upload endpoint correctly reports disabled integration if `yandex_disk.enabled=false` in runtime config.
- HTTPS routes still OK:
  - `https://work.yauzamedia.ru/bild` -> 200
  - `https://work.yauzamedia.ru/bild-dashboard.js` -> 200

## 2026-05-22 — Yandex Disk runtime token check (blocked)

### Runtime changes

- Updated `/etc/yauza/config.yaml`:
  - `yandex_disk.enabled: true`
  - `yandex_disk.remote_base_path: /Yauza_FTP_Mirror`
- Restarted `yauza-api` and `yauza-watcher`.

### Validation result

- API accepted config and endpoints became active.
- On manual upload (`POST /api/batches/{batch_id}/upload-yandex`) Yandex API returned:
  - `401 Unauthorized` from `https://cloud-api.yandex.net/...`
- This indicates OAuth token is invalid/expired/insufficient for Disk API.

### Safety action

- Auto-upload mode was turned back off:
  - `POST /api/yandex/auto-upload` with `{"enabled":false}`
- Current state: Yandex integration code is enabled in runtime config, but upload is blocked by token authorization.

## 2026-05-22 — Yandex Disk fully enabled and verified

### Fix applied

- Root cause for previous `409 CONFLICT` was non-recursive directory creation in Yandex uploader.
- Updated uploader logic to create remote directories as a tree (`mkdir -p` behavior).
- Deployed updated code and restarted:
  - `yauza-api`
  - `yauza-watcher`

### Runtime and checks

- New OAuth token configured in `/etc/yauza/config.yaml` (token value not logged here).
- Yandex API auth check succeeded (`GET /v1/disk` -> 200).

### End-to-end validation

- Manual upload from API:
  - `POST /api/batches/{batch_id}/upload-yandex` -> `status=ok`
  - remote path example: `/Yauza_FTP_Mirror/20260522/YdiskFix_20260522_155253_010.zip`
- Auto-upload mode enabled:
  - `POST /api/yandex/auto-upload` with `{"enabled":true}`.
- Watcher auto-upload succeeded for new incoming batch:
  - log contains `Yandex auto-upload complete: /Yauza_FTP_Mirror/20260522/YdiskFixAuto_20260522_155305_011.zip`.

## 2026-05-22 — Yandex mode switched from ZIP to file mirror

### Functional change

- Per updated product requirement, Yandex integration now copies original JPEG files, not ZIP archives.
- Remote structure is now:
  - `/Yauza_FTP_Mirror/<YYYYMMDD>/<photographer>/<batch_key>/<filename>.jpg`

### Code changes

- `POST /api/batches/{batch_id}/upload-yandex` now uploads all files from batch folder.
- Watcher auto-upload now mirrors files per batch directory.
- Yandex response now includes uploaded file count (`uploaded_files`).

### Validation (VPS)

- Manual endpoint result:
  - `status=ok`
  - `remote_path=/Yauza_FTP_Mirror/20260522/YdiskMirror/20260522160041-a54e9f8e`
  - `uploaded_files=1`
- Auto-upload result:
  - folder exists on Yandex:
    - `/Yauza_FTP_Mirror/20260522/YdiskMirrorAuto/20260522160055-17098cda`
  - contains file:
    - `MIRROR-AUTO.jpg`

## 2026-05-22 — Yandex mirror aligned with incoming layout

### Product alignment

- Updated mirror strategy to match legacy FTP workflow:
  - from dated batch folders
  - to incoming-like layout per photographer.

### New remote layout

- `incoming/<photographer>/<filename>.jpg` is mirrored as:
  - `/Yauza_FTP_Mirror/<photographer>/<filename>.jpg`

### Validation (VPS)

- Manual endpoint:
  - `POST /api/batches/{batch_id}/upload-yandex` returned:
    - `remote_path=/Yauza_FTP_Mirror/MirrorLegacy`
    - `uploaded_files=1`
- Auto mode:
  - watcher processed `MirrorLegacyAuto/LEGACY-AUTO.jpg`
  - Yandex Disk API confirms file exists at:
    - `disk:/Yauza_FTP_Mirror/MirrorLegacyAuto/LEGACY-AUTO.jpg`

## 2026-05-22 — Safety backups before UI/UX phase

### Local machine backups

- Project snapshot archive created:
  - `/Users/sergeyotroshko/Projects/yauza-photofactory-backups/yauza-photofactory-20260522-194231.tar.gz`
- Full git-history backup created:
  - `/Users/sergeyotroshko/Projects/yauza-photofactory-backups/yauza-photofactory-20260522-194425.bundle`

### VPS backups

- Runtime backup archive created:
  - `/opt/yauza-backups/yauza-runtime-20260522-164439.tar.gz`
- Archive includes:
  - `/etc/yauza/config.yaml`
  - PostgreSQL dump of database `photofactory`

## 2026-05-22 — UI/UX pass 1 for bild dashboard

### Frontend improvements (`/bild`)

- Updated visual hierarchy:
  - cleaner card spacing and typography
  - badge-style metadata in batch cards
- Added navigation and filtering:
  - search box (photographer / batch key / archive name)
  - photographer dropdown
  - date range (`from/to`)
  - filter reset button
- Added action-state UX:
  - per-card loading state for `Скачать пакет` and `Загрузить на Я.Диск`
  - short success state after action completion
- Added top-level tab navigation:
  - `Пакеты` (default open)
  - `Уведомления`
  - `Настройки`
- Photographer filter now uses real incoming folders with files:
  - `GET /api/incoming/photographers`
- Added explicit package controls:
  - `Обновить пакеты` button
  - `Убрать старые из списка` button (`POST /api/batches/cleanup-processed`)
- Fixed photo preview loading:
  - dashboard now requests image blobs with JWT headers and renders local object URLs
  - resolves previous issue where `<img>` could not access protected endpoint directly
- Downloaded batches are now hidden from active list:
  - `GET /api/batches` excludes `status=downloaded` by default
  - `GET /api/batches/{id}/download` marks batch as `downloaded`
- Gallery preview optimization:
  - added cached thumbnail endpoint `GET /api/photos/{photo_id}/thumbnail`
  - dashboard gallery now loads thumbnail blobs (not original JPEGs)
  - image loading uses bounded concurrency to reduce UI flicker
  - polling now refreshes package list only on active tab and skips redundant re-render
- Gallery rendering and review:
  - preview cards keep original aspect ratio (no forced square crop)
  - click on preview opens original image in modal lightbox (near full-window size)
  - lightbox supports ESC/backdrop close and direct original download
  - lightbox supports previous/next navigation (buttons + keyboard arrows)
- Session resilience:
  - dashboard now handles `401` uniformly (clears stale token, stops polling, opens `Настройки`, asks to login again)
  - avoids confusing "half-authorized" state after page refresh

### Validation (VPS)

- Protected image endpoint returns 200 with JWT auth:
  - `GET /api/photos/{photo_id}/content`
- Download endpoint returns 200 and marks batch as downloaded.
- Active list excludes downloaded batches:
  - `downloaded_visible_in_active = 0` (checked via API with/without `include_downloaded=true`)
- Mobile-focused layout:
  - responsive controls and single-column action flow on narrow screens
- Added batch KPI chips:
  - total batches
  - filtered batches
  - broken files count in current filter set

## 2026-05-22 — Context checkpoint for next sessions

### Goal of checkpoint

- Consolidate global/local project state so next work sessions can resume without context loss.

### Documentation synchronized

- Expanded `docs/SESSION-HANDOFF.md`:
  - project goal and current production status;
  - completed phases and pending tasks;
  - explicit next-sequence actions;
  - critical runtime files and VPS health-check commands;
  - fixed constraints (single-module changes, config-first, no secrets in git).
- Updated `docs/modules/07-ui-ux-bild.md`:
  - recorded implemented UX features in detail;
  - recorded remaining UI tasks (bild feedback round + lightbox zoom controls).
- Updated `docs/ROADMAP.md`:
  - added explicit step `7.7` for lightbox zoom (`+/-`, wheel, fit/100%, indicator), status `in_progress`.

### Current next step (single focus)

- Finish lightbox zoom controls and then run mini-usability validation with 2-3 bilds.

## 2026-05-22 — Hotfix: bild dashboard refresh + lightbox click

### Symptoms reported

- After page refresh, dashboard could appear "empty" until re-login.
- Gallery preview click did not always open lightbox.

### Root causes

- Event delegation for gallery click depended on `event.target` and missed clicks on nested `<img>` content.
- Frontend initialization was brittle when some DOM nodes were unavailable or served from mixed cached HTML/JS revisions.
- Browser cache could keep older script URL, delaying delivery of the fixed logic.

### Fix applied

- Updated click handling to use `closest("[data-action]")` for reliable action resolution.
- Hardened initialization with safe `bindIfExists(...)` guards for UI handlers.
- Lightbox now resolves critical DOM refs at use time via helper (`getLightboxRefs`), reducing stale-reference risk.
- Added cache-busting script URL in `bild-dashboard.html`:
  - `/bild-dashboard.js?v=20260522-2236`

### Deployment and verification

- Deployed updated files to VPS:
  - `src/photofactory/api/static/bild-dashboard.js`
  - `src/photofactory/api/static/bild-dashboard.html`
- Verified served HTML contains new version marker.
- User confirmed: issue resolved ("заработало").

## 2026-05-23 — Product scenarios 1+2 rollout

### Goal

- Switch MVP into production mode for two workflows:
  - oldschool (incoming + FileZilla + PWA notifications),
  - dashboard-first (download all / selected from web cabinet).

### Code changes deployed

- Watcher logic (`src/photofactory/watcher/service.py`):
  - no longer removes files from `incoming` on batch finalization;
  - copies valid JPEGs to `originals` and writes to `backup` only when `batch.write_backup_copy=true`;
  - auto-upload to Yandex now mirrors new incoming wave files;
  - added persistent per-photographer watermark state to avoid re-finalizing old files still lying in `incoming`.
- API (`src/photofactory/api/app.py`):
  - `/api/batches` and `/api/batches/{id}` now show only active files still present in `incoming`;
  - updated `/api/batches/{id}/download` to download active files and remove them from `incoming` after success;
  - added `/api/batches/{id}/download-selected` for partial ZIP by checkbox selection;
  - selected-download archive naming now includes daily global counter (`selected_<counter>`).
- Frontend (`bild-dashboard.html/js`):
  - removed filter strip and "cleanup/reset/refresh packages" controls;
  - package card now has `Скачать все` and `Скачать выбранное`;
  - each photo now has selection checkbox;
  - cache-busting marker updated to `/bild-dashboard.js?v=20260523-1142`.
- Config:
  - added `batch.write_backup_copy` to config model/example.

### Runtime actions on VPS

- Synced code to `/opt/yauza-photofactory`.
- Updated runtime config `/etc/yauza/config.yaml`:
  - `batch.write_backup_copy: false`
- Restarted services:
  - `yauza-api` (active)
  - `yauza-watcher` (active)

### Smoke checks (VPS)

- `GET /health` returns `{"status":"ok"}`.
- `/bild` serves new script version marker (`v=20260523-1142`).
- watcher smoke:
  - incoming file remains after batch finalization (`incoming_exists=yes`);
  - batch appears in API while file exists in `incoming`.
- selected download smoke:
  - `/api/batches/{id}/download-selected` returns ZIP;
  - selected file removed from `incoming`;
  - when package becomes empty in `incoming`, it disappears from `/api/batches`.
