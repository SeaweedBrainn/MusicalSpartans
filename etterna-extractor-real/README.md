# Mentra rhythm trainer — v16 / PhoneApp-Handoff-2

One consolidated update: the new coaching response contract, durable CSV ingestion/guide reuse, the v14 section metrics/heatmap, and the pending v15 phone layout fix. You do not need to install the intermediate updates first. This remains your React/TypeScript Mentra miniapp plus Python extraction service; the handoff's Kotlin instructions apply to the separate Android project.

## What changed

- Accepts and displays `what_went_well`, up to three structured `observations`, the new focus labels, and `measured_run_data` / `cross_run_pattern` evidence labels. Old stored guides remain readable. New contract fields are retained rather than stripped out.
- Native song coaching accepts the updated backend's 30–120-word validator range. Session speech accepts 60–180 words in two paragraphs. Focus windows must reference available CSV time intervals. Unsupported calibration, unavailable note-level claims and single-run cross-run evidence are rejected.
- Supports the actual new session response `{session_id, coaching}` with tier `mixed`. It no longer requires the earlier private `session_facts` extension. AI-only session debriefs are saved and labeled without inventing song counts or measurements. Their structured observations are retained, and Discuss report opens Coach with saved-report narrative available as context, explicitly labeled as previous AI text rather than independent measurements.
- Downloads/validates both exact CSV files for every newly listed completed attempt. Only the atomic metadata commit advances the durable cursor. Later checks start after the last committed sequence, retain old attempts, and reuse cached pairs. A server restart requires rescanning for the read key, but committed CSVs are reused. Autoplay remains visible and excluded from player coaching.
- Automatic per-run guides are saved in scoped phone storage (up to 200) and reused after reload. Manual Get coaching remains an explicit retry/update. Native transient HTTP/network retries are bounded: up to three GET attempts or two unchanged coaching POST attempts within one 50-second budget; auth, validation and rate-limit responses do not auto-retry. Temporary rate limits enforce Retry-After cooldown.
- Arbitrary HTTP response bodies are not copied into phone errors or speech. Read keys remain only in bounded extraction-server memory and go only to the exact configured API origin, as read bearer headers, with redirects rejected. Both 401 and 410 withdraw access; retained private history is not deleted by withdrawal.
- Includes the phone-width fix: starter flex/root centering reset, constrained root/cards, stacked mobile score cards and chart-only horizontal scrolling. Metrics/calculations are unchanged by this layout fix.

Authoritative inputs: supplied PhoneApp-Handoff-2, plus inspected RhythmBackend revision `c7ca134c9e9603565a6979d34a1cdf2deb8f7ffb`. Copies of the supplied handoff/schema files are in `integration/handoff-2`. SESSION-API.md retains V1 examples; PHONE-APP-HANDOFF.md explicitly specifies V2 notes. The standalone coach-response-schema.json describes coaching fields; the OpenAPI's empty coaching object placeholder does not describe the actual coaching payload.

## 1. Copy the project updates

Unzip and merge `backend`, `samples`, `integration` and `verification` into:

```text
~/Downloads/etterna-extractor-real
```

Keep `.venv-local`, runtime jobs, and the private `session-cache` directory. Do not replace your working manifest/package name.

Copy ALL four files from the download's `miniapp/src` into your existing qr-scanner project's `src`:

```text
src/background/index.ts
src/ui/App.tsx
src/shared/channels.ts
src/shared/timing.ts
```

## 2. Update the local coach adapter

QR-linked song/session coaching goes directly from Python to the game API and does not need this local adapter. Etterna AI coaching, local report AI and contextual coach chat still use it. If you use those features, stop the old C# service and use a fresh checkout so old integration patches are not stacked onto the new source:

```bash
cd ~/Downloads
git clone https://github.com/Jamallama/RhythmBackend.git RhythmBackend-v16
cd RhythmBackend-v16
git checkout c7ca134c9e9603565a6979d34a1cdf2deb8f7ffb
bash ~/Downloads/etterna-extractor-real/integration/apply-rhythmbackend.sh "$PWD"
cd RhythmBackend
ASPNETCORE_ENVIRONMENT=Development SessionApi__StorageProvider=Local dotnet run --no-launch-profile --urls http://127.0.0.1:5248
```

.NET 10 is required. The existing UserSecretsId is retained, so your local key configuration should carry over. If necessary, configure GEMINI_API_KEY in dotnet user-secrets; never put it in miniapp source or share it. GEMINI_MODEL is optional and otherwise uses the current backend default.

The replacement patch targets c7ca134. It adds the Development-only `/api/mentra` adapter, one formatting-repair attempt within the provider's existing 45-second budget, and authenticated/no-key/autoplay guards. It preserves the new upstream coaching schema and native session-route response shape. Do not apply the older v12 or speech-only patches to this checkout. Those superseded incremental patch files have been removed from this package.

Running a patched local service does not update Azure. The supplied handoff states the native API is deployed; this package does not deploy it or claim a live Gemini test. The backend owner can review the new patch if they also want the adapter/retry/guards on their source. Native schema compatibility does not require deploying our earlier custom SessionDebrief implementation.

## 3. Restart Python

Stop the old Python process with Ctrl+C:

```bash
cd ~/Downloads/etterna-extractor-real/backend
source .venv-local/bin/activate
python3 -m pip install -r requirements.txt
RHYTHM_COACH_URL=http://127.0.0.1:5248 OCR_ENGINE=rapidocr python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

If that virtual environment does not exist, create it once with `python3 -m venv .venv-local`, then activate/install. Use python3 explicitly.

`RHYTHM_COACH_URL` configures the optional local facts/chat adapter. The game API remains:

```text
https://rhythm-backend-emmanuel-hvfkdjhxfjc4d9a5.westus-01.azurewebsites.net
```

Only change RHYTHM_SESSION_ORIGINS if the team changes the actual API origin. It is an exact-origin allowlist, separate from the Mac adapter URL. Health reports extractor_version 16.0.

## 4. Rebuild and reopen the miniapp

Inside your existing qr-scanner project:

```bash
bun run build.ts
mentra-miniapp dev
```

Close/reopen the miniapp. Confirm **Combined coach v16** in Settings → Debug. Keep the phone's saved extraction-server setting pointed to your Mac's current Wi-Fi IP, for example `http://172.16.22.56:8000`, not localhost.

Scan the game's session QR once. Later attempts/replays use **Chat → Sessions → Check for new runs**. All newly completed pairs are downloaded before the selected latest attempt is displayed. You can select an older attempt without rescanning. App/server restart still requires a fresh scan to regain credentials; it does not discard cached CSVs or phone reports. There is no automatic background polling in this prototype.

## Four pages

| Page | Contents |
| --- | --- |
| Glasses | Default landing page, central Turn on camera single-photo scan, See sessions and Stop speech. QR is tried first; appropriate no-QR images go to Etterna CV. No live preview is claimed. |
| Song | CSV/OCR song statistics, reviewed OCR corrections, Add to session, coaching action, alignment tools, five-second section metrics and latency heatmap. |
| Chat | Sessions, Reports and Coach. New observations and what-went-well text are shown with the speech. AI-only server reports can be discussed without pretending they contain local song facts. |
| Settings | Volume, server/capture preferences, warnings and storage actions. Collapsed Debug contains samples, service tests and technical evidence. |

Routine progress is narrated; actionable errors remain visible. Choose the Bluetooth glasses as the phone media output and use Test voice. The app cannot verify or force a specific audio route.

## Measurement rules

V2 overall accuracy is an approximate sum of rounded accuracy_delta values under the engine developer's zero-baseline convention, separate from score. Missing deltas or invalid totals leave it unknown; gaps/partial captures are disclosed. No grade is inferred.

V2 sections show `(P + G) / captured judgments` as hit rate, P/G/M counts, successful-hit mean offset and population SD. Hit rate is not weighted game accuracy. Running accuracy changes cannot yield independent section accuracy.

The latency heatmap plots signed successful P/G offsets against scheduled song time; zero is retained, blanks excluded/countable and misses kept separate. Outer display buckets include outliers. Long songs widen the normally five-second windows to at most 80 columns. V1 heatmaps show sample means, not reconstructed note distributions. Etterna uses OCR/photo graph crops, not the CSV heatmap.

## Storage and acceptance limits

Exact CSV bytes, immutable metadata and durable ingestion state live privately on the Mac under backend/session-cache, not on the phone. Phone storage retains compact report summaries, AI-only debriefs and bounded saved guides. A successful commit requires both exact files and metadata. Failed downloads do not advance that attempt's cursor. Credentials are never written into this cache.

Local reports cover manually added phone results. New server debriefs contain AI narrative rather than per-song facts; the upstream session implementation sends summaries to Gemini, so detailed section/accuracy/density analysis must come from the downloaded CSV/local calculations. Stored AI report text is not promoted to new measured evidence in chat.

This is a trusted-LAN Mentra-plus-Mac prototype, not the handoff's completed production Android integration. Public multi-user extraction isolation, phone-private retention of every CSV pair, actual Azure/Pages CORS acceptance, physical glasses audio, and mobile rendered layout are not certified. Photos remain in extraction jobs for review/alignment. This update does not require native Android conversion.

## Verification

From backend with the environment active:

```bash
OCR_ENGINE=tesseract python3 -m unittest discover
```

Inside verification: Node 24+, `npm install`, then `npm test`.

C# from the fresh patched repository root:

```bash
dotnet build RhythmBackend/RhythmBackend.csproj
dotnet run --project RhythmBackend/tests/CoachContractChecks/CoachContractChecks.csproj
cd RhythmBackend
dotnet run --project tests/SessionContractChecks/SessionContractChecks.csproj -- "$PWD/bin/Debug/net10.0/RhythmBackend.dll"
```

`verification/smoke-session-api.py --v2 --dll /absolute/path/to/RhythmBackend.dll` runs disposable loopback registration/upload/read/auth/no-key/revocation checks without calling Gemini. See TEST_RESULTS.md for measured evidence and limits. Optional browser geometry checks are described in verification/README.md; this runner blocks Chromium launch.
