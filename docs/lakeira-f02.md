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

## Retention policy

The user-confirmed assignment requirement is **one hour locally and thirty days
in the cloud**, measured from capture end. Earlier versions of this document
reversed those periods; those descriptions are superseded.

| Tier | Routine retention | Safety conditions |
| --- | --- | --- |
| Local recording buffer | 1 hour | Remove a variant only after its cloud upload has succeeded and its current cloud SHA-256 matches the verified upload. Failed uploads remain buffered beyond an hour. |
| Routine cloud recordings | 30 days | Delete at the capture-based deadline, unless an incident reference or active job holds the recording. Local copies are not required at the cloud deadline. |
| Saved incidents and active jobs | Protected | Separate incident archives are untouched. Recording holds protect both formats in both tiers. |

Delayed uploads keep the original thirty-day deadline; a two-day-old recording
still has twenty-eight days remaining, rather than a new thirty-day window.
Routine recordings already thirty days old are not uploaded. Both cleanup modes
remain disabled by default. Cloud cleanup and local cleanup have separate flags.
Local corruption or an unavailable/corrupt cloud copy blocks local removal and
records an error. A missing local file does not block normal cloud expiry.

On first startup with this policy, the worker migrates previously stored one-hour
cloud deadlines to capture end plus thirty days. It requeues expired/deleted rows
so local variants can restore any prematurely removed cloud objects. This cannot
recover footage if both copies were already lost. The migration runs only once
and preserves subsequent retry schedules and verified upload checksums.

`CloudQueue.hold(recording_id, owner)` protects both formats for save/export work.
Acquire it before accessing footage, and release it after the job finishes.
Holds survive crashes and need explicit recovery. Legacy incident records that
reference original filenames also protect their recording pair. Separate saved
incident archives are never scanned by cleanup.

**Playback integration remains pending.** Current API playback reads local
files. Keep local cleanup disabled in deployment until authorized cloud playback
is connected, so footage older than one hour remains reviewable. The local
cleanup flag is provided for isolated retention tests first.

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
work, past-expiry rows, active holds, removed local variants, and verified uploads
within the thirty-day cloud window. It also states both retention periods. `overdue`
includes held copies and copies retained while cleanup is disabled; it is not a
count of policy violations. Counts refer to file variants, not logical recordings.

Enable routine **cloud** expiry after thirty days explicitly:

```sh
python -m smart_sec_cam.video.cloud_worker --enable-cleanup
```

For isolated retention tests, or after authorized cloud playback is implemented,
add local cleanup of verified variants after one hour:

```sh
python -m smart_sec_cam.video.cloud_worker --enable-cleanup --enable-local-cleanup
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
Its default command keeps both cleanup modes disabled. To run one cloud cleanup
pass at the thirty-day deadline:

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
failure, the exact one-hour local and thirty-day cloud boundaries, local copy
corruption, remote-copy verification, holds, incident references, policy migration,
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
   available until local cleanup is enabled; afterward older footage needs the
   authorized cloud retrieval path.
4. Wire holds into future cloud-dependent incident/export jobs and add an
   authenticated operational dashboard and buffer-pressure alerts.
5. Validate the confirmed one-hour local/thirty-day cloud policy against real
   footage, including the exception that failed uploads stay local. Separate
   incident backup is not implemented here.
6. Verify continuous camera capture and F01's recorder startup dependency, then
   measure four-camera throughput and real deletion timing. Automated local
   tests are preparation for these acceptance tests, not a substitute for them.
