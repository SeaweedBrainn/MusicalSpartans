# MusicalSpartans Android App — Backend Integration Handoff

Date: 2026-11-15 (Pacific)

Audience: MusicalSpartans Android/phone-app developer

Repository: https://github.com/SeaweedBrainn/MusicalSpartans

## Goal

Connect the Android app to the deployed Rhythm Backend so the phone can scan one
session QR code, retrieve every completed attempt in that session, download both
CSV files for each attempt, and request Gemini coaching.

Production API:

```text
https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net
```

The backend is live and has been tested with the V2 per-note CSV contract.

## Current repository observations

The app currently has useful pieces that can be retained:

- `FakeRunRepository` loads demo CSVs from `app/src/main/assets/`.
- `RunImporter` already parses a summary/timeline pair into a `Run`.
- `SessionStore` persists local reports.
- `CoachViewModel` owns song/report UI state.
- The file picker in `MainActivity` supports manual CSV import.

The following parts are not the production integration:

- `backend/main.py` is an older local multipart upload server with `/runs` routes.
- The app's direct Gemini API-key configuration must not be used for production.
- Production Gemini calls must go through the Azure backend.

## Security model

Every session has two independent 32-character Base64url capabilities:

- `session_key`: phone read capability. It can list runs, download CSVs, and request coaching.
- `upload_key`: Unity write/revocation capability. It must never be sent to the phone.

The phone must:

- Keep the read key in private app storage or memory.
- Never log the key, place it in analytics, or display it in UI.
- Never send the key to any origin other than the configured production API.
- Send it only as `Authorization: Bearer <session_key>` on `/v1` requests.
- Reject redirects to another origin rather than forwarding the bearer header.

Do not put Gemini, Azure, or upload credentials in the APK.

## QR scan flow

Unity constructs this URL after the session registration acknowledgement:

```text
https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net/sessions/{session_id}/?key={session_key}
```

The phone should parse the QR locally. It does not need to open the landing page.

Validate all of the following before accepting the scan:

1. HTTPS scheme.
2. Exact production host.
3. Path exactly `/sessions/{32-lowercase-hex-id}/`.
4. Exactly one query parameter named `key`.
5. Key matches `[A-Za-z0-9_-]{32}`.
6. No fragment, user-info, extra query parameters, or unexpected path.

The same QR grants read access to all later attempts in that session. Do not scan
again for every song. A session normally expires after 24 hours.

## API sequence

### List completed attempts

```http
GET /v1/sessions/{session_id}/runs?after_sequence=0&limit=100
Authorization: Bearer <session_key>
```

Only completed attempts are returned. Use `sequence` as the ingestion cursor, not
the client finish timestamp. Continue while `has_more` is true, then poll later
with the last `next_after_sequence`.

The response contains relative file paths and metadata, including:

- `run_id`
- `sequence`
- `completed_at`
- `finished_at_utc`
- `game_id`, `song_id`, `chart_id`
- `autoplay`
- `successful_hit_count`
- `files.series`
- `files.summary`

### Download the two files

Use the read bearer on every request:

```http
GET /v1/sessions/{session_id}/runs/{run_id}/series.csv
Authorization: Bearer <session_key>
```

```http
GET /v1/sessions/{session_id}/runs/{run_id}/summary.csv
Authorization: Bearer <session_key>
```

Retain the exact response bytes. Do not normalize line endings or remove trailing
blank cells. Validate that the returned paths stay on the production API origin.

Only advance the local ingestion cursor after both files and the run metadata are
saved successfully.

### Request Gemini coaching

```http
POST /v1/sessions/{session_id}/runs/{run_id}/coach
Authorization: Bearer <session_key>
```

The request has no body. The backend reads the committed CSVs, sends validated
data to Gemini, and returns:

```json
{
  "session_id": "...",
  "run_id": "...",
  "coaching": {
    "mode": "song_debrief",
    "tier": "A",
    "coaching_focus": "timing_bias",
    "speech": "...",
    "phone_text": ["..."],
    "drill": "...",
    "next_target": "...",
    "focus_section": {
      "start_s": 4,
      "end_s": 5,
      "reason": "..."
    },
    "data_notes": [],
    "confidence": "high",
    "evidence_basis": "game_heuristic"
  }
}
```

Display `coaching.speech` as the main paragraph, `phone_text` as short UI lines,
and optionally speak `speech` with the existing `Speaker`. The response is not
persisted by the backend; the app should save it if coaching history is desired.

### Request a session debrief

After several runs are available, request a cross-song report:

```http
POST /v1/sessions/{session_id}/coach
Authorization: Bearer <session_key>
```

The request has no body. The response uses `mode: "session_debrief"` and returns
two spoken paragraphs: the first describes the song-to-song trend and the second
gives one high-level practice priority and comparison for the next session. Do
not present this as a detailed replay of the latest song.

Autoplay runs may be retrieved, but must not be described as player performance.

## CSV V2 requirements

The HTTP envelope remains `contract_version: 1`. The V2 choice is inside
`series.csv`:

```csv
game_id,1
song_id,10
chart_id,1
bpm,120
format_version,2
note_index,time_ms,lane,judgement,accuracy_delta,latency_ms,nps,bpm,combo,std_ms
```

V2 is one row per judged note. Fields are:

- `note_index`: nonnegative, increasing; gaps are allowed.
- `time_ms`: scheduled note time.
- `lane`: nonnegative lane index.
- `judgement`: `P`, `G`, or `M`.
- `accuracy_delta`: signed percentage-point change in running weighted accuracy.
- `latency_ms`: signed input-minus-note offset; blank means unavailable.
- `nps`: centered one-second density; do not sum it to compute total notes.
- `bpm`: active BPM at that note.
- `combo`: P/G increments; M resets to zero.
- `std_ms`: running population standard deviation of successful-hit offsets.

Only P/G rows with nonblank latency contribute to `successful_hit_count` and
timing statistics. A Miss row may contain a signed offset if it was press-caused;
automatic misses use blank latency. Zero is a real latency value, not missing data.

The unchanged summary CSV is one headerless eight-field record:

```text
game_id,song_id,difficulty_band,game_time_ms,bpm,total_notes,score,avg_latency_ms
```

Do not treat `score` as accuracy. Summary accuracy is not supplied as a field.

The existing `RunImporter` can remain the UI-facing parser, but it must be updated
to recognize the V2 metadata/header and preserve note-level rows if detailed
replay/outlier display is required.

## Suggested Android implementation

1. Add `INTERNET` permission if it is not already present.
2. Add an HTTP client (OkHttp, Retrofit, or a carefully scoped `HttpURLConnection`).
3. Create `SessionApi` for the endpoints above.
4. Create `SessionCredentialStore` for the scanned session ID/read key.
5. Add QR scanning using the team's chosen scanner library.
6. Add `RemoteRunRepository` alongside `FakeRunRepository`.
7. Download and validate both CSVs before advancing the sequence cursor.
8. Adapt `CoachViewModel` to load remote runs and request coaching.
9. Keep `SessionStore` for local reports and optional cached coaching.
10. Remove direct Gemini production calls and APK API-key configuration.

Example request construction:

```kotlin
val request = Request.Builder()
    .url("$apiBase/v1/sessions/$sessionId/runs?after_sequence=$cursor&limit=100")
    .header("Authorization", "Bearer $sessionKey")
    .header("Accept", "application/json")
    .get()
    .build()
```

## Error handling

Handle these statuses explicitly:

| Status | Meaning | App behavior |
|---|---|---|
| 200 | Read/list/download/coaching success | Process response |
| 401 | Missing/wrong key or unknown session | Clear local session access and require a new scan |
| 403 | Correct key with wrong scope | Treat as an integration error; do not retry with another key |
| 404 | Run/file not available | Mark that run unavailable; do not bypass auth |
| 409 | Conflicting upload identity | Not normally produced by the phone |
| 410 | Session expired/revoked | Withdraw the session and require a new scan |
| 413 | File/request too large | Preserve local data; do not truncate |
| 422 | Invalid CSV or metadata | Surface a safe validation message; do not silently downgrade to V1 |
| 429 | Rate limit or session quota | Honor `Retry-After` for temporary limits |
| 5xx/network | Transient failure | Retry unchanged GET/coach request with bounded backoff |

Never display raw response bodies containing request data as UI errors.

## Acceptance test

The phone integration is ready when it can:

1. Scan one QR code.
2. List an empty session successfully.
3. Retrieve song A and both CSV files.
4. Request and display song A coaching.
5. Retrieve a replay of song A without another scan.
6. Retrieve song B using the same QR/read key.
7. Avoid duplicate coaching for the same `run_id`.
8. Preserve autoplay labeling.
9. Clear access after a 401/410 response.
10. Pass with the actual Pages origin and production Azure URL.

## Do not do

- Do not use the old Python `/runs` API for production.
- Do not call Gemini directly from the APK.
- Do not send `upload_key` to the phone.
- Do not put a bearer key in a `/v1` query string.
- Do not silently convert V2 CSVs to the old V1 window format.
- Do not sum NPS rows to calculate total notes.
- Do not treat blank latency as zero.
- Do not forward bearer credentials across redirects or origins.
