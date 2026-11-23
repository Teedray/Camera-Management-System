# Cloud storage research

## SRS expectations and current gaps

Source: COMP 2140 Group 2, *Software Requirements Specification for Camera Footage Management System*. References below use the page numbers printed in the document. The operating environment (section 1.4, p. 7) describes **at least 30 days locally, approximately the latest hour in private cloud storage, and separate backup copies of saved incidents**. The recorder and provider findings below describe the prototype.

**Decision needed before enabling deletion.** F02's user requirement specifies a 60-minute private cloud window, but UC02 (p. 14) and SR-02-02 / AC-02-02 (p. 20) describe removing cloud recordings older than 30 days. SAF-01 (p. 30) protects the last routine copy for at least a month. Use the local-month/cloud-hour split as the working design and have the team and pharmacy confirm where the 30-day cleanup test applies. Under that design, cloud expiry can remove a routine copy only while another retained copy satisfies the minimum. Saved incidents and footage needed by active save/export jobs require protection. Lakeira owns the sync and recent-cloud retention work.

### Capacity under the SRS assumptions

At the SRS planning rate of **1 Mbps per camera**, continuous recording produces 0.45 GB per camera-hour, using decimal units. These figures assume one retained encoding at that rate. If both prototype formats are kept, use their combined measured bitrate.

| Footage window | One camera | Four cameras |
| --- | ---: | ---: |
| 10-minute outage buffer | 75 MB | 300 MB |
| 60 minutes of recent cloud footage | 0.45 GB | 1.8 GB |
| 30 days of routine local footage | 324 GB | 1,296 GB (about 1.3 TB) |

The SRS specifies **at least 2 TB of local storage** to allow for buffering and working space. The earlier 260 GB/month discussion uses a hypothetical 1 MB per 10-second pair; the SRS estimate uses a different bitrate. Neither is a Cam1 measurement. Protected incidents accumulate beyond the rolling hour, so their volume and retention policy must be budgeted separately. If the 30-day cloud interpretation is approved, routine cloud capacity alone rises to about **1.3 TB for four cameras**.

At the required 30-second segment length, four cameras uploading one object per segment around the clock would make **345,600 uploads per 30 days**, or **691,200** with two variants. That baseline and a 1.8 GB recent window fit the R2 Standard allowances documented below. Archive growth, retries, listings and playback requests still need measurement before a zero-cost deployment can be confirmed.

### Acceptance gaps

| SRS target | Current project evidence | Evidence needed for acceptance |
| --- | --- | --- |
| Continuous capture and catalogue, F01 / PR-01 (pp. 19, 29) | The recorder buffers motion-triggered clips for about 10 seconds and writes two variants. Listing scans filenames. The earlier inspection found a restarting recorder and no real saved clips. | From each of four cameras, record three minutes continuously and verify six 30-second segments per camera, one catalogue entry per segment with location and start/end times, duplicate rejection, and a visible gap after disconnection. Measure bytes for each encoding. |
| Private, verified uploads and outage recovery, F02 / PR-04 / SQR-02 (pp. 20-21, 29, 31) | The shared local folder and writer completion point exist. Provider selection is research; upload, verification and recovery are pending. | On the reference network (at least 10 Mbps upload), show each completed segment verified and playable within 30 seconds. Disconnect for ten minutes, confirm uninterrupted local recording and local access, then reconnect and verify every pending segment arrives once. Surface failures and buffer overflow. |
| Routine retention, incident protection and recovery, F04 / SAF-01 to SAF-03 (pp. 24, 30) | Local file playback works. The research identifies no recording catalogue with expiry, incident protection, active-job holds or verified backup state. | After policy sign-off, exercise the minute-by-minute cleanup and two-minute removal target at the agreed tier. Test 28-, 29- and 31-day fixtures, a protected incident and an active export. Restore footage and its camera/time metadata from separate storage and play it. Agree backup frequency and restoration time. |
| Authorized review and security, F03 / PR-02 to PR-03 / SEC-01 to SEC-03 (pp. 22-23, 29-30) | Local playback checks the current camera assignment. Cloud privacy, encryption at rest, audit coverage, and month-scale retrieval times remain unverified. | Verify private HTTPS retrieval, encryption of primary and backup copies, audit events and denial after revocation. Search a month by camera and time during recording. F03 specifies three seconds for search and PR-02 allows five, so test to three pending clarification. Verify playback starts within five seconds, seeks within three, and pauses at most one second between available segments. |

The first acceptance milestone is a reproducible four-camera recording sample with measured bitrate and a working catalogue. That evidence can validate disk sizing and gives Lakeira completed segments for upload, outage and expiry tests.

## Recorder output

| Item | Finding |
| --- | --- |
| Recording trigger | Motion. The recorder collects frames for about 10 seconds after a trigger, then writes the buffered clip. |
| Segment duration | 10 seconds is the configured capture window. Encoded playback duration is pending measurement on real recordings. The writer derives an integer frame rate from frame count and elapsed time, so the playback duration can differ from the capture window. |
| WebM variant | VP9, requested via OpenCV FourCC `VP90`. |
| MP4 variant | MPEG-4 Part 2, requested via OpenCV FourCC `mp4v`. |
| Resolution and audio | The writer resizes frames to 640 x 480 and writes video frames only. |
| Files per segment | One WebM and one MP4 file are written from the same frames. Both use the stem `<channel>__YYYY-MM-DD_HH:MM:SS`, with the timestamp generated when writing begins. |

An isolated OpenCV 5.1.0 probe ran the repository writer on generated frames. It produced readable 640 x 480 files in both formats. OpenCV reported codec tags `VP90` for WebM and `FMP4` for MP4. Its FFmpeg backend emitted a warning about the `VP90` tag while writing WebM, and the resulting file decoded successfully. This probe verified the writer's output formats. Real camera playback duration, clip size, and recording frequency remain pending. [Video writer](../backend/smart_sec_cam/video/writer.py#L34) and [motion capture loop](../backend/smart_sec_cam/motion/detection.py#L109).

## Storage per camera per hour

**Measured storage per camera-hour: pending.** The current and earlier local deployments had no saved recordings in their video directories. The current motion-detection container was restarting with an AttributeError at the call to `RedisImageReceiver.start_listener_thread()`, so it could not provide a fresh recording sample during this inspection. [Recorder entry point](../backend/smart_sec_cam/motion/main.py#L12).

To measure storage once real clips are available:

1. For one camera, collect completed recording pairs over a representative time window and record each file's size in bytes and playback duration. Group the WebM and MP4 files by their shared stem.
2. Calculate bytes per wall-clock camera-hour as total bytes written during the observation window divided by its length in hours. Report each format separately and add their byte totals if storing both. The wall-clock window includes idle periods.
3. For bytes per hour of recorded video, multiply total bytes by 3,600 and divide by the sum of clip durations in seconds. When including both formats, count a paired clip's duration once. Ten-second clips would amount to about 360 segments per hour of continuous capture. The number of motion-triggered clips per wall-clock hour is pending.

## Existing integration points

| Component | Role in a future cloud storage integration |
| --- | --- |
| Recorder and shared storage | `MotionDetector` calls `VideoWriter.write()` at the end of capture. Both video writers release their files before `write()` returns. That completion point is where a later integration could identify ready-to-sync files. Compose shares host `data/videos` at `/backend/data/videos` between the recorder and Flask server. [Writer](../backend/smart_sec_cam/video/writer.py#L34) and [Compose volumes](../docker-compose.yml#L16). |
| SQLite camera identity and access | `AuthDatabase` already stores `users`, `cameras`, and `user_cameras`. The unique `cameras.channel_name` connects the recorder's filename channel to a stable `cameras.id`. Existing `get_user_cameras()` and `can_access_camera()` enforce enabled cameras and current assignments. A future recording index could reference `cameras.id` and track filename or object key, format, timestamp, size, and duration. At the time of the research, the schema had no recording catalogue. See the recording catalogue handoff below for the subsequent integration. [Camera schema](../backend/smart_sec_cam/auth/database.py#L55) and [assignment lookup](../backend/smart_sec_cam/auth/database.py#L254). |
| Recording list | `GET /api/video/video-list` scans local files, validates names, filters by the caller's assigned channels and requested format, and sorts newest first. A future metadata lookup can plug in here while keeping the current access checks, format filtering, and response shape. [Recording list](../backend/smart_sec_cam/server/server.py#L279). |
| Recording playback | `GET /api/video/<file_name>` validates the token, filename, and current channel assignment before serving the local file. Cloud retrieval belongs behind that authorization check. Administrators still require camera assignments to view footage. [Playback route](../backend/smart_sec_cam/server/server.py#L324). |

Lakeira owns cloud syncing and one-hour retention. This document records the current behavior and integration points for that work.

## Free object storage for the COMP2140 prototype

Reviewed 23 November 2026. Choose **Cloudflare R2 Standard** for the camera demo. Repeated playback has no direct R2 bandwidth charge, the existing Flask service can keep enforcing camera assignments, and one continuously recording camera fits the free monthly upload allowance under the assumptions below. Choose **Backblaze B2** if the team needs to start without a payment card and expects limited playback. Actual Cam1 file sizes and motion frequency are still pending.

| Service | Free allowance and billing conditions | Fit for this recorder |
| --- | --- | --- |
| Cloudflare R2 Standard | 10 GB-month, 1 million Class A operations and 10 million Class B operations each month. Direct internet egress and object deletes are free. Standard overages are $0.015/GB-month, $4.50/million Class A and $0.36/million Class B, with usage rounded up to billing units. Activation requires subscription checkout. | Best for repeated playback. Count uploads and bucket listings against Class A. Budget browser range reads against Class B. Cloudflare averages each day's peak storage, so a recurring cleanup backlog can affect the bill. [R2 pricing](https://developers.cloudflare.com/r2/pricing/) and [activation](https://developers.cloudflare.com/r2/get-started/). |
| Backblaze B2 | First 10 GB free. Direct monthly downloads up to three times average monthly storage are included, then $0.01/GB. No minimum storage duration fee. A payment card is optional to start. | Good for a no-card demo or frequent writes with little playback. At 0.5 GB average stored, the direct download allowance is only 1.5 GB/month. A short retention window keeps storage low but also reduces this playback allowance. [B2 pricing](https://www.backblaze.com/cloud-storage/pricing), [no-card signup](https://www.backblaze.com/blog/roll-camera-streaming-media-from-backblaze-b2/) and [spending caps](https://www.backblaze.com/docs/en/cloud-storage-create-and-manage-caps-and-alerts). |
| Supabase Storage Free | 1 GB file storage, 5 GB uncached egress and a separate 5 GB cached egress allowance. Free projects pause after one week of inactivity. | Suitable for a small classroom demo. At an illustrative 1 MB per playback, 5,000 uncached playbacks would use 5 GB. The project already has SQLite users and assignments, so adopting the storage service would not require moving authentication. [Supabase pricing](https://supabase.com/pricing). |

### What one camera would consume

These scenarios assume 30 days, 10-second clips, two files per event, one successful single-part upload per file, and prompt deletion at one hour. The 1 MB per clip pair used below is an **illustration**, with decimal units. It is the combined size of both files. Retries, listings and other account activity would add requests.

| Recording activity | Clip pairs per hour | Uploads per 30 days | Bytes retained for one representative hour at 1 MB/pair |
| --- | ---: | ---: | ---: |
| 10% of the time, evenly distributed | 36 | 51,840 | 36 MB |
| 50% of the time, evenly distributed | 180 | 259,200 | 180 MB |
| Continuous capture | 360 | 518,400 | 360 MB |

Two continuously recording cameras would make approximately 1,036,800 uploads per month. That already crosses R2's free Class A allowance before retries or listings. At the published rounding and rates, that scenario would incur about $4.50 in Class A charges for the month, assuming the full allowance was available. A busy hour can also consume far more storage than a daily motion average suggests. Before promising a zero-cost deployment, measure the busiest observed hour of paired files, count monthly uploads across all cameras, and record actual playback requests and bytes. [R2 request billing](https://developers.cloudflare.com/r2/pricing/).

### One-hour retention and private playback

For Lakeira's integration, the important distinction is when footage becomes inaccessible versus when the provider deletes its bytes. R2 says lifecycle deletions typically occur within 24 hours of expiration. For a one-hour deadline, the application should record a capture-based expiry, exclude expired recordings from listing and playback, and explicitly delete both variants with retry tracking. A delayed upload must retain the original expiry. A lifecycle rule can clean up missed objects. [R2 lifecycle behavior](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).

Keep the bucket private and preserve the current Flask assignment check on each playback request, including new range requests. A direct presigned URL grants access to its holder until expiry, so a previously issued URL can outlive a viewer's camera assignment. Serving authorized range requests through the backend preserves revocation for subsequent requests. If the backend is later hosted by another provider, include that host's outbound bandwidth in the playback budget. Lakeira owns syncing and retention implementation. [R2 presigned URL semantics](https://developers.cloudflare.com/r2/api/s3/presigned-urls/).

## Recording catalogue handoff

The catalogue integration adds SQLite tables for logical recordings and their file variants. The recorder stamps the first buffered frame and the end of capture in UTC, before encoding. These times describe capture at the recorder. Each completed WebM and MP4 has a separate relative path, byte count and playback duration derived from the encoded frame count and frame rate.

The recorder publishes a completion manifest on the shared video volume after both files close and can be decoded. Flask imports it in one database transaction, links the channel to the registered camera ID and acknowledges the manifest after commit. An unknown channel stays pending. The API applies current camera assignments to catalogue entries. Legacy files remain accessible through their original names and permissions; their capture intervals cannot be recovered reliably from filenames alone.

**Dependency for Zidane (F01).** The motion service stops at startup because its entry point calls `RedisImageReceiver.start_listener_thread()`, which the receiver does not implement. Zidane needs to reconcile the recorder and receiver APIs and verify continuous capture from a real camera. Until then, production clip measurements and end-to-end registration from Cam1 are pending. Lakeira owns cloud sync and retention. The SRS retention conflict still needs a team decision.
