# F02: rolling cloud storage

Lakeira's branch: `feature/lakeira-rolling-cloud-storage`, based on
`merge/database-rba-incident-clips`. The initial implementation is commit `eb19d87`.

## What works

The independent worker imports completed recorder manifests and discovers both
catalogue variants, including recordings registered before startup. SQLite keeps
upload state, failed-attempt counts, retry deadlines, checksum, and error class.
Deterministic `routine/<recording-id>/clip.<format>` keys make retries idempotent.
Uploaded bytes are downloaded and SHA-256 checked before success is recorded.
This costs an extra read per upload and must be measured on the reference network.

The recent cloud window ends one hour after **capture end**, including after an
outage. Old unprotected footage is skipped rather than receiving a fresh upload
window. Upload retries never schedule the first expiry check past that deadline.
Expired cleanup failures retry within one minute, subject to worker throughput.

Cleanup remains opt-in. It deletes only tracked routine keys, preserves every
local file, and requires the retained local variant to match the catalogue byte
count. Previously verified uploads also require the local SHA-256 to match before
deletion. A missing or changed local copy blocks deletion and records
`LocalCopyUnavailable`. Archive paths and keys are never scanned or deleted.

`CloudQueue.hold(recording_id, owner)` protects both formats for save/export work.
Call it before using a cloud copy, then release it when the job is finished.
Holds survive crashes and require explicit recovery. Existing incident records
referencing an original filename also protect the original pair. Current incident
extraction uses local footage, which the cloud worker never removes.

## 1. Prepare the private R2 bucket

In the team's Cloudflare account, create or select the prototype bucket. Keep
**r2.dev public access disabled** and do not attach a public custom domain. Create
an **Object Read & Write** R2 credential scoped to that bucket. Keep the Access
Key ID and Secret Access Key locally; do not paste them into chat or commit them.
The account endpoint is typically
`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`; copy the exact endpoint from the
account, including a jurisdiction-specific endpoint if applicable.

References: [R2 S3 setup](https://developers.cloudflare.com/r2/get-started/s3/) and
[R2 API credentials](https://developers.cloudflare.com/r2/api/tokens/).

For other S3-compatible providers, use an **unversioned private bucket**.
Versioned S3 buckets retain old versions after a normal delete; this worker does
not remove them. Do not add a blanket lifecycle rule that could bypass holds.
Bucket privacy and versioning must be checked manually: `--check` tests object
operations, not account policy or public domains.

## 2. Configure and test from macOS Terminal

From the root of your normal Git clone:

```sh
cp .env.cloud.example .env.cloud
open -e .env.cloud
```

Replace the placeholders and enter the bucket-scoped keys in that local file.
`.env.cloud` is excluded from Git and Docker build contexts. Then create an
isolated environment and install only the worker dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install './backend[cloud]'
set -a
source .env.cloud
set +a
cd backend
python -m smart_sec_cam.video.cloud_worker --check
```

`--check` uploads one small random `health-check/<id>.txt` object, reads it back,
compares SHA-256, and requests deletion. It always attempts deletion even after
an uncertain upload or corrupt read. If deletion fails, its temporary key is
reported for manual removal. No routine footage or incident object is touched.
The check does not need the application database or a running camera.

Once the application has created its shared database and completed recordings:

```sh
python -m smart_sec_cam.video.cloud_worker --status
python -m smart_sec_cam.video.cloud_worker --once
python -m smart_sec_cam.video.cloud_worker
```

Run from the same `backend/` directory as Flask, or provide `--database` and
`VIDEO_DIR` explicitly. The worker refuses to create an empty database if started
from the wrong directory. `--once` exits nonzero if recorded failures remain.
`--status` reads the database without changing it and requires no credentials or
SDK. It reports pending/uploaded/expired/deleted variant counts, failed rows, due
work, past-expiry rows, active holds, and verified recent uploads. `overdue`
includes held copies and copies retained while cleanup is disabled; it is not a
count of policy violations. Counts refer to file variants, not logical recordings.

After the team agrees the cloud-hour/local-month policy, enable expiry explicitly:

```sh
python -m smart_sec_cam.video.cloud_worker --enable-cleanup
```

## 3. Optional Docker worker

A separate image avoids rebuilding the frontend just to run cloud sync. Docker
Desktop is required. From the repository root, after creating `.env.cloud`:

```sh
docker compose -f docker-compose.yml -f compose.cloud.yml build cloud-worker
docker compose -f docker-compose.yml -f compose.cloud.yml run --rm cloud-worker --check
```

Once the server has initialized the shared database:

```sh
docker compose -f docker-compose.yml -f compose.cloud.yml up -d cloud-worker
docker compose -f docker-compose.yml -f compose.cloud.yml run --rm cloud-worker --status
docker compose -f docker-compose.yml -f compose.cloud.yml logs --tail=30 cloud-worker
```

`compose.cloud.yml` is opt-in and uses the same `./data` volume as the server.
Its default command keeps cleanup disabled. To run one cleanup pass after policy
approval:

```sh
docker compose -f docker-compose.yml -f compose.cloud.yml run --rm cloud-worker --once --enable-cleanup
```

Run only one worker. Remote operations currently hold SQLite's write lock so that
cleanup and holds serialize. Connection/read timeouts bound individual network
requests; uploads can still delay API writes. The worker checks at one-minute
intervals and processes up to 100 due variants per pass. Validate throughput and
cleanup latency; a leased queue and shorter scheduling interval are follow-ups
before scaling. Do not run overlapping continuous and one-shot sync workers.
A status-only process is safe while the worker is running.

## Tests

From the repository root:

```sh
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_cloud*.py' -v
```

These tests use isolated SQLite databases, an in-memory object store, and a mocked
S3 client. They cover durable retry recovery, capture-based deadlines, checksum
failure, one-hour expiry, local copy corruption, holds, incident references,
crash-leftover cleanup, delete outages, queue fairness, configuration validation,
connection-check cleanup, stream closure, and read-only status. They do not
contact a real provider or certify bucket privacy. Docker configuration/image
validation and the rest of the application suite require their dependencies.

## Remaining acceptance work

1. Run the connection check against the team's private bucket, then upload real
   catalogue segments and verify timings on the reference network.
2. Test a ten-minute network outage, restore connectivity, and verify each pending
   recent variant once. Check status while offline and after recovery.
3. Connect cloud playback behind the existing current-camera authorization check.
   This worker exposes no public or presigned playback URLs. Local playback stays
   available independently of the one-hour cloud window.
4. Wire holds into future cloud-dependent incident/export jobs and add an
   authenticated operational dashboard and buffer-pressure alerts.
5. Agree the requirements document's conflicting retention periods. Local 30-day
   cleanup and separate incident backup are not implemented here.
6. Verify continuous camera capture and F01's recorder startup dependency, then
   measure four-camera throughput and real deletion timing. Automated local
   tests are preparation for these acceptance tests, not a substitute for them.
