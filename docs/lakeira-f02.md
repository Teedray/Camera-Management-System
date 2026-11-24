# F02: rolling cloud storage — first implementation

Lakeira's branch: `feature/lakeira-rolling-cloud-storage`, based on
`merge/database-rba-incident-clips` at upstream commit `14cd491`.

## Included

- An independent worker imports completed recorder manifests and discovers both
  catalogue variants, including those registered before the worker started.
- SQLite persists upload state, retry deadlines, checksum, and error class.
  Deterministic `routine/<recording-id>/clip.<format>` keys make retries idempotent.
- Uploaded bytes are downloaded and SHA-256 checked before success is recorded.
  This deliberately costs an extra read per upload; measure it in deployment.
- The cloud window ends one hour after **capture end**, even after an outage.
  Old unprotected footage is skipped instead of receiving a fresh upload window.
- Cleanup is opt-in. It deletes only tracked routine keys, preserves all local
  files, and requires the local variant to exist with the catalogue byte count.
  Archive paths and keys are never scanned or deleted.
- `CloudQueue.hold(recording_id, owner)` protects both formats for save/export
  work. Call it before using cloud footage; release only when the job is finished.
  Holds have no automatic timeout, so crashed jobs need explicit recovery.
- Existing incident records referencing an original filename also protect the
  original pair. Saved incident archive files remain separate and untouched.

## Run locally

From `backend/`, install the optional dependency:

```sh
python -m pip install '.[cloud]'
```

Configure environment variables in your terminal or secret manager:

| Variable | Value |
| --- | --- |
| `CLOUD_ENDPOINT_URL` | HTTPS S3-compatible endpoint, e.g. the team's R2 account endpoint |
| `CLOUD_BUCKET` | Existing private bucket dedicated to the prototype |
| `AWS_ACCESS_KEY_ID` | Bucket-scoped credential |
| `AWS_SECRET_ACCESS_KEY` | Secret credential; never commit it |
| `AWS_DEFAULT_REGION` | Optional; defaults to `auto` for R2 |
| `VIDEO_DIR` | Optional; defaults to `data/videos` |

Use the same working directory and shared `data/` directory as the Flask service.
The worker uses `AuthDatabase` and the existing catalogue without changing local
playback. Credentials are resolved by boto3's normal provider chain.

```sh
python -m smart_sec_cam.video.cloud_worker --once
python -m smart_sec_cam.video.cloud_worker
```

After the team agrees the cloud-hour/local-month policy, enable routine cloud
expiry explicitly:

```sh
python -m smart_sec_cam.video.cloud_worker --enable-cleanup
```

Use an **unversioned private bucket**, with public access disabled. Versioned
S3 buckets retain old versions after a normal delete, so this worker does not
meet physical cleanup targets there. Do not add a blanket provider lifecycle
rule that could bypass active holds. Keep incident backups in a separate prefix
or bucket. This worker does not create a bucket or change its permissions.

Run one worker. Each remote operation currently holds SQLite's write lock to
serialize cleanup with holds; read/connect timeouts bound individual requests,
but uploads may still delay API writes. A leased job queue is a follow-up before
scaling. Run periodically at one-minute intervals; the worker takes at most 100
rows per pass, so throughput and cleanup latency need deployment measurement.

## Validation

From the repository root:

```sh
PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_cloud_storage.py -v
```

The tests use isolated SQLite databases and an in-memory storage adapter. They
cover restart recovery, duplicate discovery, retry deadlines, checksum failure,
the exact one-hour boundary, disabled cleanup, missing local-copy protection,
holds, incident references, old pending objects after a crash, delete outages,
and queue fairness. They do not contact a real cloud provider.

## Next integration steps

1. Configure the team's bucket and run upload/read-back against real segments.
2. Connect cloud playback behind the current camera assignment checks. No public
   or presigned playback URLs are exposed by this implementation.
3. Wire holds into any future cloud-dependent save/export jobs. Current incident
   extraction reads local footage, which this worker never deletes.
4. Add authenticated operational status and alerting for failed uploads, buffer
   pressure, unresolved holds, and missing local copies. Error classes are stored
   in `cloud_uploads.last_error`; raw SDK exception details are not persisted.
5. Agree the requirements document's conflicting retention periods before enabling
   cleanup. Local 30-day cleanup and separate incident backup are not implemented.
6. Verify four-camera throughput, ten-minute outage recovery, and real cloud
   deletion timing. The recorder startup issue identified in the research handoff
   belongs to F01 and still needs end-to-end camera verification.

## Source checkout note

Terminal DNS could not reach GitHub during this session. The starting files were
downloaded from Lakeira's branch as a GitHub ZIP. The local Git baseline is a
snapshot, not upstream history: **do not push its baseline commit to GitHub**.
Transfer the changes using the accompanying patch onto a normal clone of the
existing branch when terminal connectivity is available.
