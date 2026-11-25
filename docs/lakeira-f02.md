# F02: Google Drive rolling storage

The agreed design is **Google Drive (Google One account storage), MP4-only cloud
uploads, a one-hour local buffer, and thirty days of routine cloud recordings**.
The recorder, SQLite database, and website still run on the on-site computer.
Google Drive is storage for the application, not its application server.

## Implemented

- Completed catalogue MP4 variants are uploaded using the Drive API. WebM remains
  a local compatibility encoding and is not uploaded by the default worker.
- The local Drive index reserves a generated file ID before uploading. Retries
  after an uncertain response reuse that ID. App-specific metadata allows recovery
  if index entries are lost; ambiguous duplicates fail instead of picking a copy.
- Uploaded bytes are read back and SHA-256 verified before success is recorded.
- Local cleanup can remove both local encodings after one hour, only after the
  MP4 cloud copy is verified again. Failed uploads remain buffered beyond an hour.
- Routine cloud copies expire thirty days after capture end. Outage recovery never
  gives old footage a fresh thirty-day window. Active holds protect both tiers.
- Separate saved incident archives are outside routine cleanup. Local incident
  extraction takes a job hold. A manager can also save an incident from a verified
  cloud-only source; its temporary copy is removed after extraction.
- Recording lists include authorized cloud-only MP4 files. Playback passes through
  Flask, rechecks current camera assignments, verifies the downloaded bytes, and
  supports HTTP byte ranges. The frontend requests MP4 on all browsers.
- No public Drive links or sharing grants are created. The configured folder must
  be owned only by the dedicated account. The application requests `drive.file`,
  which limits it to files it creates or the user explicitly opens with it.

## 1. Create the Google API credentials

Use the dedicated Google account that owns the agreed storage plan. In
[Google Cloud Console](https://console.cloud.google.com/), select or create the
team's project, enable **Google Drive API**, and configure its OAuth consent
settings. Create an OAuth client with application type **Desktop app** and
download its client JSON. Follow the [official Python quickstart](https://developers.google.com/workspace/drive/api/quickstart/python)
for current Console navigation. Account creation, terms, consent, and purchases
must be completed by the account owner.

Store the JSON as `backend/data/drive-client.json` in your normal Git clone.
`data/` and `.env.cloud` are ignored by Git. Never paste the client JSON, token
JSON, or refresh token into chat or commit them. The runtime uses user OAuth;
a service-account key is not a substitute for the Google One account login.

For a prototype with the OAuth app in **Testing**, add the dedicated account as a
test user. Testing authorizations for Drive scopes expire after seven days;
resolve the app's production-readiness/consent requirements before relying on
unattended continuous operation. See [Google's app audience documentation](https://support.google.com/cloud/answer/15549945).

## 2. Authorize and create the private application folder

From your repository root on macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './backend[server,drive]'
cd backend
python -m smart_sec_cam.video.drive_auth --client-secrets data/drive-client.json
```

The helper opens Google's sign-in/consent flow on localhost. Select the dedicated
account and approve the displayed per-file Drive permissions yourself. It writes
`data/drive-token.json` with owner-only permissions and creates a new private
application folder. Copy the printed `DRIVE_FOLDER_ID` value. An arbitrary folder
created manually in Drive is not automatically available under `drive.file`.
Do not share this application folder.

The helper refuses to overwrite an existing token. If setup succeeds, reuse its
folder and token rather than creating new authorizations for every worker run.
If folder creation fails after the token is saved, keep the token safe and recover
setup explicitly rather than deleting credentials blindly.

## 3. Configure both server and worker

From the repository root:

```sh
cp .env.cloud.example .env.cloud
open -e .env.cloud
```

Set `DRIVE_FOLDER_ID` to the printed folder ID. The token and index paths in the
example are relative to `backend/`, which is also the Docker working directory.
Load the settings before starting either Flask or the worker:

```sh
set -a
source .env.cloud
set +a
cd backend
python -m smart_sec_cam.video.cloud_worker --check
python -m smart_sec_cam.video.cloud_worker --status
python -m smart_sec_cam.video.cloud_worker --once
```

`--check` uploads a small random `health-check` object, reads and hashes it, and
requests deletion, including after a lost upload response. The check needs no
camera or application database, and does not touch footage. If deletion fails,
its temporary key is logged for recovery. The worker/status modes need the shared
application database initialized by Flask; `--database` overrides its location.
The worker refuses to create an empty database when started in the wrong folder.

Run continuously with cleanup disabled initially:

```sh
python -m smart_sec_cam.video.cloud_worker
```

After the real upload/playback/outage checks succeed, explicitly enable the two
cleanup operations:

```sh
python -m smart_sec_cam.video.cloud_worker --enable-cleanup --enable-local-cleanup
```

`--enable-cleanup` permanently deletes expired routine Drive files after thirty
days; it does not move them to Trash. `--enable-local-cleanup` removes verified
local encoding pairs after one hour. Both flags are off by default. Neither flag
scans the incident archive. Inspect and recover stale job holds after a crash;
holds have no automatic timeout that might interrupt active work.

Keep `data/drive-index.db` alongside the shared database in backups. A cloud queue
is bound to its destination folder/provider so a worker cannot assume a verified
S3 object exists on Drive. An existing uploaded queue without a provider binding,
or one bound elsewhere, requires explicit migration and verification. Do not
change folder/provider and enable cleanup on an old live database.

## 4. Optional Docker deployment

Authorize on the host first. With `.env.cloud` configured and the server's shared
`data/` already initialized, from the repository root:

```sh
docker compose -f docker-compose.yml -f compose.cloud.yml build server cloud-worker
docker compose -f docker-compose.yml -f compose.cloud.yml run --rm cloud-worker --check
docker compose -f docker-compose.yml -f compose.cloud.yml up -d server cloud-worker
docker compose -f docker-compose.yml -f compose.cloud.yml run --rm cloud-worker --status
```

The optional Compose file passes the same Drive settings to Flask and the worker.
Both mount `./data` so they share the catalogue, token, and Drive index. Run only
one sync worker; do not overlap a continuous worker with one-shot sync passes.
Status-only processes are safe while syncing.

## Tests and remaining live checks

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
```

The suite exercises recorded media, catalogue/API permissions, incident creation,
retention boundaries, MP4-only uploads, duplicate-safe Drive retries, local pair
cleanup, temporary holds, cloud listing/playback/ranges, revocation, expired and
corrupt footage, and incidents saved from cloud-only sources. Drive tests use
mocked API responses, not a real Google account.

Before enabling cleanup, verify with the team's account and real cameras:

1. The connection check and upload/read-back of actual recordings succeed.
2. MP4 remains listed, playable, and available for incident saving after local
   cleanup. Revoked assignments deny subsequent playback/range requests.
3. An internet outage retains local footage and pending jobs; reconnecting uploads
   each pending MP4 to its original deadline without duplicate files.
4. Timestamp fixtures demonstrate thirty-day expiry and incident/job protection.
5. Actual four-camera bitrate, available account storage, upload bandwidth, API
   usage, and OAuth renewal meet the agreed operating needs.

The backend currently downloads and verifies a whole clip into temporary storage
before returning even a range response. This preserves integrity and authorization
without public links, but adds latency and repeated downloads during seeking.
Measure it before claiming playback/seek timing targets. Temporary files close
with responses; they are not a permanent playback cache.

The worker polls once per minute and handles at most 100 due variants per pass.
Remote operations still hold SQLite's write lock, so busy uploads may delay API
writes. Validate throughput and cleanup timing before production. Separate cloud
backup of saved incidents is not part of routine MP4 retention and remains a
separate acceptance item.

## Optional S3 compatibility

The previous S3 adapter remains available with `CLOUD_PROVIDER=s3`,
`CLOUD_ENDPOINT_URL`, `CLOUD_BUCKET`, and normal SDK credentials. Install the
`cloud` extra for it. Google Drive is the default; it does not use those S3
settings. Changing providers on a populated queue requires migration.
