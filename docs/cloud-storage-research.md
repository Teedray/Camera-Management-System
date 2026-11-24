# Cloud storage implementation handoff

## Corrected retention requirement

The user clarified the assignment: **one hour of local recordings and thirty days
in the cloud**. The earlier version of this research document had those periods
reversed. Its local-month/cloud-hour design and associated free-tier capacity
conclusions are superseded. Use this confirmed policy for Lakeira's F02 work.

Routine local variants may be removed after one hour only when their cloud copies
are verified. Outages extend the local buffer; they must not destroy the last
unverified copy. Routine cloud variants expire thirty days after capture end.
Saved incident archives and footage needed by active jobs are protected from
routine cleanup. Provider lifecycle rules must not bypass those protections.

## Capacity planning

Using the earlier planning assumption of **1 Mbps per camera**, continuous capture
produces 0.45 GB per camera-hour (decimal units), for one encoding at that rate.

| Storage tier | Retention | One camera | Four cameras |
| --- | --- | ---: | ---: |
| Routine local buffer | 1 hour | 0.45 GB | 1.8 GB |
| Routine cloud footage | 30 days | 324 GB | 1,296 GB |

These are calculated estimates, not real-camera measurements. If both WebM and
MP4 are uploaded, use their combined measured bitrate. Outage buffers and saved
incidents add storage. A small free cloud allowance must not be assumed to cover
thirty days of continuous footage. Reevaluate provider capacity and costs for
this corrected window before activating a storage plan.

## Current integration

The recorder writes a completed manifest after both encoded variants close.
`catalogue.import_completed` registers the camera-linked capture interval and
variant paths, sizes, and durations in the shared SQLite database. Unknown camera
channels remain pending until registered. The cloud worker imports manifests and
queues catalogued variants with deterministic routine object keys. Each upload
is downloaded and SHA-256 checked before it is marked successful.

Local cleanup independently rechecks the cloud checksum before removing a local
variant. The cloud deadline does not depend on a retained local copy. Database
migration repairs earlier one-hour cloud deadlines and requeues previously
expired or deleted variants for recovery where their local files remain.

Cloud MP4 playback now uses authorized backend retrieval when the local file
is absent. Deploy with local cleanup disabled until a real Drive playback test succeeds. Existing camera
assignment checks must apply to every cloud playback/range request. Saved
incident archives remain separate from routine footage.

## Confirmed provider and encoding

The team confirmed **Google Drive backed by the dedicated Google One account**,
with **MP4-only cloud uploads**. The previous Cloudflare R2 proposal is superseded.
The on-site recorder and application server still run locally. The worker now
has a Drive API adapter using per-file OAuth, a private app-created folder, and
persistent generated file IDs for duplicate-safe retries. The S3 adapter remains
an optional compatibility path, with destination checks preventing accidental
mixing of provider state.

Cloud-only playback is now implemented behind the existing camera assignments.
Flask downloads and verifies a complete MP4 before serving full or ranged bytes.
Incident saving can use the same verified cloud source. Both cleanup flags remain
disabled until the team's real account/camera tests pass.

The capacity figures above are planning estimates, not the three-clip Reolink
measurements supplied in the discussion. Do not treat either sample as a
four-camera busy-store measurement. Confirm the dedicated account's usable quota,
actual bitrate, sustained upload capacity, and OAuth production readiness.

## Acceptance work still needed

- Verify continuous camera capture and the F01 recorder/receiver integration.
- Measure per-camera bitrate for each encoding and confirm cloud capacity.
- Run real upload/read-back, a ten-minute outage, and recovery tests.
- Demonstrate one-hour local cleanup only after verified upload, thirty-day cloud
  expiry, saved-incident protection, and active-job holds using timestamp fixtures.
- Validate the implemented authorized cloud review/playback before enabling local cleanup.
- Validate separate incident backups and restoration of footage plus metadata.

See [Lakeira's setup guide](lakeira-f02.md) for worker commands, test coverage,
cleanup flags, and current limitations.
