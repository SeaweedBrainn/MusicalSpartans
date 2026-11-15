# Rhythm session API v1

Implementation mapping for documents 19, 20, and 21, accepted in the project chat.
This document describes checked-in code, not a claim that it has been deployed.
The authoritative machine-readable schema is [session-api.openapi.json](session-api.openapi.json),
served at `GET /openapi.json`. Legacy `/api/results` and `/api/chat` remain separate.
There is no `/api/results/upload` multipart endpoint.

The original supplied documents are retained verbatim in `contracts/`. Their
proposal markers and assumed browser origin describe the earlier coordination
draft; this mapping and its confirmed `seaweedbrainn.github.io` origin supersede
those assumptions for this implementation.

## Client configuration

```text
ApiBaseUrl = https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net
PublicClientUrl = <ApiBaseUrl>/sessions
Production browser origin = https://seaweedbrainn.github.io
```

Use HTTPS directly. Do not forward capabilities across redirects. The native phone
client must validate the QR's exact API origin, path and single `key` parameter
locally; it does not need to open the landing page to parse the QR.

| Method/path | Credential | Success |
| --- | --- | --- |
| `POST /v1/sessions` | Both newly generated keys in JSON | 201 first registration; 200 identical retry |
| `PUT /v1/sessions/{session_id}/runs/{run_id}` | Upload bearer | 201 first commit; 200 identical retry |
| `POST /v1/sessions/{session_id}/runs/{run_id}/coach` | Read bearer | 200 structured Gemini coaching for the validated CSVs |
| `GET /v1/sessions/{session_id}/runs` | Read bearer | 200, including empty sessions |
| `GET /v1/sessions/{session_id}/runs/{run_id}/series.csv` | Read bearer | 200 exact UTF-8 CSV |
| `GET /v1/sessions/{session_id}/runs/{run_id}/summary.csv` | Read bearer | 200 exact UTF-8 CSV |
| `DELETE /v1/sessions/{session_id}` | Upload bearer | 204; subsequent requests return 410 while tombstone metadata remains |
| `GET /sessions/{session_id}/?key=...` | QR link | Minimal HTML; no files or credential echo |
| `GET /health` | None | 200 only when private storage is reachable and passes initialization checks |

The root `GET /` remains the existing basic liveness response. It does not prove
storage readiness or Gemini connectivity.

## Registration and identity

Generate `session_id` and each `run_id` as 32 lowercase hexadecimal characters.
Generate independent `session_key` and `upload_key` from 24 cryptographically random
bytes, encoded as 32 unpadded Base64url characters. Never put the upload key in a
QR, public game config, CSV, analytics, or PlayerPrefs.

```json
{
  "contract_version": 1,
  "session_id": "<32 lowercase hex>",
  "session_key": "<32 Base64url characters>",
  "upload_key": "<32 independent Base64url characters>"
}
```

An identical retry returns the original `contract_version`, `session_id`,
`created_at` and `expires_at`, without echoing credentials. Both keys must match;
otherwise registration returns `409 session_conflict`. Expiry is never extended.
Keys are hashed with SHA-256, session ID and separate read/upload scope labels,
then compared using constant-time comparison. Anonymous registration does not
establish that an authentic Unity build produced the data.

## One attempt, one immutable JSON upload

Send to `PUT /v1/sessions/{session_id}/runs/{run_id}` with
`Authorization: Bearer <upload_key>` and `Content-Type: application/json`:

```json
{
  "contract_version": 1,
  "finished_at_utc": "2026-11-15T04:03:42Z",
  "game_id": 2,
  "song_id": 103,
  "chart_id": 1,
  "sample_interval_sec": 1,
  "autoplay": false,
  "latency_basis": "successful_hits_only_v1",
  "successful_hit_count": 1,
  "summary_exceeds_format_range": false,
  "series_csv": "game_id,2\nsong_id,103\nchart_id,1\nbpm,120\nsample_interval_sec,1\ngame_time,percent_accuracy,avg_latency,bpm,nps,latency_spread\n0,,,120,0,\n1,100,-12,120,1,\n",
  "summary_csv": "02,103,3,2000,120,1,1000000,-12"
}
```

All fields are required. Unknown JSON properties are rejected rather than silently
discarded. Timestamps must be ISO-8601 UTC ending in `Z`. The response contains
`session_id`, `run_id`, strictly increasing server `sequence`, `status: completed`,
and immutable server `completed_at`.

Both CSV files are staged at a unique private object prefix. A conditional update
of the session manifest publishes the completed attempt only after both writes
succeed. The same manifest holds revocation state, so an upload cannot overwrite
a concurrent revocation. API downloads require this published manifest and
recheck session validity after file I/O.

The content digest is SHA-256 over an explicit ordered list of parsed metadata
and exact UTF-8 CSV bytes, with a byte-length prefix before each field. JSON
property order and JSON escaping do not affect identity. CSV LF versus CRLF does.
Changed retry content returns `409 run_conflict`; it never replaces files. A lost
commit acknowledgement leaves staged objects intact until the outcome is known,
so cleanup cannot delete a potentially successful commit. Losing contenders own
different staging prefixes and cannot delete the winner's files.

## Listing and phone retrieval

Send the read bearer on every listing and CSV request. The upload key is not a
read key. API requests reject a `key` query parameter.

```http
GET /v1/sessions/{session_id}/runs?after_sequence=0&limit=100
Authorization: Bearer <session_key>
```

`runs` contains only completed attempts, ordered by ascending server sequence.
Each entry includes all envelope metadata (except the CSV contents), server
completion time and relative `files.series`/`files.summary` paths. No object names,
blob credentials, public URLs or signed blob URLs are exposed.

`next_after_sequence` is the last returned sequence, or the supplied cursor for an
empty page. `has_more` describes the current snapshot, not whether future runs can
arrive. Page size defaults to 100 and is bounded to 1–100. Client-reported finish
time is not the ordering cursor.

The phone should advance its ingestion cursor only after both files and metadata
are retained. Keep coached-run tracking separate. A replay is a new run ID in the
same session. One scan remains valid for later attempts. Preserve autoplay runs
for retrieval, but do not coach them as player performance.

## CSV validation and coaching boundary

Series metadata must appear in this order: `game_id`, `song_id`, `chart_id`, `bpm`,
`sample_interval_sec`. Row six is exactly
`game_time,percent_accuracy,avg_latency,bpm,nps,latency_spread`.
Window starts begin at zero and advance by the declared interval (1 or 2 seconds).
`nps` is a nonnegative integer note count per window, not a computed density. A
missing note count cannot support consistency checks and is rejected; optional
accuracy/latency/spread blanks are preserved as unavailable, never replaced by 0.

Summary is one headerless eight-field record, optionally ending in LF or CRLF:
`game_id,song_id,difficulty_band,game_time_ms,bpm,total_notes,score,avg_latency_ms`.
Padded decimal IDs are accepted. Summary has no accuracy. IDs match the envelope
and series numerically. Chart ID is not difficulty. Series BPM may be fractional;
summary BPM may differ by rounding up to half a BPM.

Validate finite values, documented ranges, note-total consistency, successful-hit
count bounds, and unavailable spread when fewer than two hits can support it.
When successful-hit count is 0, series timing must be blank and summary latency 0
is only the engine's sentinel, not a real zero-ms observation. With positive hit
count, numeric zero remains valid. Negative offsets mean early; positive mean late.
Do not reconstruct song mean latency from per-window means: hit weights are absent.

`summary_exceeds_format_range: true` permits only explained ID/note/BPM clamp
mismatches; the flag is retained in listings. Summary fields must still be within
their documented serialized ranges. Raw duration and difficulty are not in the
envelope, so their pre-clamp values cannot be reconstructed. Treat flagged summary
data as unsuitable for exact coaching claims. The backend cannot verify that
Unity excluded misses from already-aggregated latency; Unity must fix this before
asserting `successful_hits_only_v1`.

### CSV coaching

After a run has been uploaded, the phone or frontend can request coaching with
the read capability:

```http
POST /v1/sessions/{session_id}/runs/{run_id}/coach
Authorization: Bearer <session_key>
```

The backend re-authorizes the session, reads the committed CSVs, and sends the
validated CSV text to Gemini as data, never as instructions. Gemini returns the
same structured `CoachResponse` contract used by the legacy coaching routes.
The response is not persisted; clients should retain it if they need a coaching
history. Autoplay runs remain retrievable but should not be coached as player
performance. Uploading a run alone does not call Gemini.

## Errors, limits and lifecycle

Errors use `{"error":{"code":"...","message":"..."}}`, without credentials or
request bodies. Statuses: 400 malformed input/cursor/ID; 401 missing or wrong key or
unknown session; 403 wrong scope; 404 unpublished/missing file; 409 conflict; 410
expired/revoked with correct scope/key; 413 size limit; 422 CSV/metadata/version;
429 temporary rate limit or full-session quota; 503 unavailable/busy storage or
deadline. Infrastructure may produce its own response if it rejects a request
before ASP.NET Core receives it.

Limits: 256 KiB UTF-8 per CSV, 2 MiB JSON request, 200 completed attempts/session,
two-minute server operation deadline. Identical committed retries succeed even
when the attempt quota is full. Rate controls per app process: 5 registrations per
minute/IP, 100 registrations/hour globally, 240 protected operations/minute/IP,
8 concurrent registration/upload operations. Temporary limits return `Retry-After`;
full-session quota returns `session_quota_exceeded` without promising a retry time.
Use one App Service instance initially; multiple instances share safe Blob CAS but
require a distributed edge limiter for a fleet-wide registration/rate budget.

Sessions expire 24 hours after registration. Expiry/revocation denies access even
before physical cleanup. The worker runs every 15 minutes while the app runs,
removes payloads and attempt metadata, retains key-hash tombstones during the next
24 hours for authenticated 410s, then deletes that session record. A minimal,
non-reversible SHA-256 digest of the used random session ID is retained separately
to prevent session-ID reuse; it has no keys, attempts or timestamps. After full
metadata deletion, reads return 401, not 410. Abandoned staging objects older than
one hour are deleted when not referenced by a manifest.

Physical deletion requires working storage and a running cleanup schedule. Free
App Service can unload, so see [AZURE-DEPLOYMENT.md](AZURE-DEPLOYMENT.md) for the
authenticated external cleanup route, account retention settings and release checks.

## Test evidence

```powershell
dotnet build --output .\bin\SessionVerification
dotnet run --project .\tests\SessionContractChecks\SessionContractChecks.csproj -- .\bin\SessionVerification\RhythmBackend.dll
dotnet run --project .\tests\CoachContractChecks\CoachContractChecks.csproj
```

The session runner covers auth scopes, registration/run retries, concurrent
commits, second-file failures, ambiguous successful commits, revocation races,
expiry, cleanup, local persistence, pagination, CSV edge cases, CORS and app-log
credential omission. Failure injection is **simulated**, HTTP evidence is local,
and neither is evidence of Unity WebGL or glasses behavior.

For Azure SDK storage checks, start Azurite on local port 10000 with
`--skipApiVersionCheck` and append `--blob` to the session test command. This uses
a disposable private container and emulator credentials, not an Azure account.
Use `tools/Test-SessionApi.ps1` against the deployed HTTPS API for a disposable
three-attempt integration smoke test; it prints no keys or QR URLs.
