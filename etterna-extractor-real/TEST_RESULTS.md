# v16 / PhoneApp-Handoff-2 validation

Current backend source inspected: c7ca134c9e9603565a6979d34a1cdf2deb8f7ffb. The supplied handoff and standalone coaching schema are retained under integration/handoff-2. The patch targets that revision, preserves its native session response and coaching fields, and clean-applies to a fresh checkout. Older v12 custom-session/incremental speech patches are superseded.

## Completed checks

- Python discovery: 83 cases, 79 passed and four unavailable external Etterna camera fixtures skipped. The actual supplied QR image was included and decoded. Final 20-case targeted checks passed after bounding saved report context; no raw credentials were printed.
- New handoff tests verify structured observations/new focus and evidence labels, tier-mixed two-paragraph session replies without session_facts, saved narrative-only reports, bounded unchanged POST retry and no auth retry.
- Incremental ingestion tests verify all newly listed pairs download, repeated selection/refresh reuses exact cached pairs, committed sequence survives rescan/process credential reset, and failure of a second CSV leaves that attempt uncommitted so it is retried from the preceding cursor.
- Strict TypeScript plus timing/UI/background simulations pass. They cover new coaching cards, narrative-only report discussion, saved narrative chat context, guide reuse after background reload, no external navigation, and the existing sections/heatmap/OCR/session/report/speech flows.
- Current C# source builds with zero warnings/errors. All 28 coaching/contract/retry/facts checks and 199 local session/CSV/storage/HTTP checks pass. The final facts-only guard additionally prevents personal performance claims from unusable data. The old custom SessionDebrief extension is not added on top of the upstream route.
- Disposable local V2 integration against the updated patched service passed: registration/empty session, upload, read-bearer CSV retrieval, grounded local facts, native per-run/session auth/scope/no-key gates, autoplay exclusion and revocation. No real Gemini call was made; the smoke deliberately removes its key.

## Remaining acceptance

No live Gemini, Azure deployment/Pages CORS acceptance or physical glasses/phone output is claimed. Native API/CSV integration above is local or simulated. The handoff says its deployment is live; that statement was not independently exercised with player credentials.

The pending v15 phone-width fix remains included. Chromium startup is blocked in this runner, so rendered iOS acceptance is still required. The optional real-browser geometry test remains available. File bytes and durable cursor are retained privately on the Mac, not every CSV in phone-private storage. No automatic session polling or native Android conversion was added. Access withdrawal does not delete already-held private history. Captured photos remain available for review/alignment.

Earlier version evidence follows as history; where old schema/patch/caching statements differ, this v16 section and the current README supersede them.

# v15 mobile Song-page layout fix

- Inspected both supplied phone screenshots: content clips at the left and right while the fixed bottom navigation remains viewport-sized. The layout fix constrains the application root/main/card sizing, resets the centered-flex starter-template root and isolates the intrinsic-width SVG in its own scrolling container.
- Score/accuracy metrics stack on phone widths up to 440 CSS pixels. Long labels, controls, tables and raw JSON are constrained. A missing viewport meta gets a device-width default without disabling zoom or overwriting an existing viewport.
- Strict TypeScript, pure timing tests and UI/background interaction checks pass. New checks cover viewport fallback/preservation and the keyboard-focusable chart scroll region. CSV analytics and Python/C# source remain unchanged from v14.
- The included optional real-browser regression checks 320/393/430/768px page widths against a deliberately centered Vite-style flex root, stacked metrics, chart-only scrolling and browser errors. Its bundle built, but this runner blocked Chromium startup (socket creation denied). Rendered-browser screenshots and physical iOS acceptance were not completed; do not interpret the interaction checks as proof of rendered layout.

# v14 section metrics and latency heatmap validation

- Python regression: 78 tests discovered, 74 passed, four unavailable external Etterna camera-fixture cases skipped. The supplied QR camera image was included and decoded successfully.
- The V2 section test verifies P/G/M counts, hit rate, measured-offset count, unchanged successful-hit mean/population SD, and a null weighted section accuracy. Overall approximate accuracy retains its existing semantics.
- Strict TypeScript checks and all miniapp UI/background simulations pass. New pure timing checks cover section-vs-overall metric separation, true zero, blank offsets, miss-offset exclusion, positive/negative/tail buckets, sparse windows, exact final boundaries, bounded long-song columns and V1 sample-average labeling.
- UI checks cover the new section hit-rate display, absence of the old V2 accuracy placeholder, SVG heatmap labeling, keyboard-accessible time-window inspection and signed mean values. Existing four-page navigation, OCR review, sessions/reports/chat, saved volume and speech cancellation remain covered.
- No new C# changes or model/API deployment are required for this feature. Prior backend patch validation remains recorded below. No new physical-phone/glasses or rendered-browser visual acceptance is claimed; this runner previously blocked Chromium startup.
- The CSV heatmap uses existing raw rows. It does not reconstruct per-note offsets from V1 sample averages or digitize Etterna image graphs. Captured gaps and missing latencies still limit the data.

# v13 four-page miniapp validation

- Strict TypeScript and UI/background simulations pass against @mentra/miniapp 3.4.0.
- UI checks verify exactly four main pages; Glasses is the landing page; camera and See sessions actions; Song-only Add to session and reviewed OCR values; coaching navigation; linked-session refresh/attempt selection; reports/chat; warnings/settings placement; samples nested under collapsed Debug; and removal of manual QR entry.
- Existing CSV/Etterna displays, approximate accuracy separate from score, image bridge, corner correction, refreshed images, report read-aloud, date-bounded deletion confirmation and no external navigation remain covered.
- Background checks verify narrated scan/result progress, actionable photo errors that survive state/voice updates, recovery, saved speech volume after reload and its use in speaker calls. Existing queued/stale speech cancellation, report persistence/deduplication, chat context and scan/button flows pass.
- Browser visual checks were attempted but this runner blocked Chromium startup. No mobile screenshot, hardware audio-route or physical glasses acceptance is claimed. Test camera capture, glasses-button scan, Bluetooth output and the four pages on your phone after installing.
- This version changes the three miniapp source files plus verification/documentation. Python and C# behavior remains the v12 implementation described below; its checks were not rerun for this UI-only update.

# v12 consolidated validation

This package includes the pending speech-format fix, approximate V2 accuracy, local and server session debriefs, and selected miniapp UI handoff changes. Backend patch baseline: 48998408dce30596e1369c09908460bc1bce7543.

## Completed checks

- Python full regression: 77 cases discovered, 73 passed, four external Etterna camera-fixture cases skipped. The supplied QR camera screenshot was included via QR_CAMERA_TEST_IMAGE and decoded successfully. A final 14-case session/proxy subset passed after improving the session-coach 503 diagnostic.
- V2 accuracy checks cover summing rounded signed deltas from the supplied zero-baseline convention, approximate labeling, real zero, blank versus unavailable, invalid sums, and partial-capture warnings. Score is kept separate; no grade is inferred. Existing tests retain note gaps, latency semantics, successful-hit timing statistics, NPS semantics, exact private CSV caching and response-envelope matching.
- Local session report checks cover ordering by server sequence, first/last accuracy, bias distance, spread, BPM, peak sampled density, best/weakest available accuracy, recurring flags, one or two actions, two speech paragraphs, missing values and separation of scoring groups/unusable attempts.
- Python server-debrief proxy checks use simulated responses: read-key transport, response/paragraph validation, explicit undeployed-route errors, safe handling of invalid capabilities, and conversion of the server snapshot into a saved report. These are not live model tests.
- Strict TypeScript checks and miniapp UI/background simulations pass. They cover approximate accuracy separate from score, report persistence/deduplication, no fabricated note-level accuracy, queued/stale speech cancellation, late automatic speech suppression, voice failure/recovery, camera/button paths, QR/session/Etterna states, chat and existing storage behavior.
- Updated C# service builds with zero warnings and zero errors. All 46 coaching contract/retry checks, 11 session-debrief fact checks and 199 local session/CSV/storage/HTTP contract checks pass.
- The full compatibility patch clean-applies to a fresh checkout of the pinned backend revision. The speech-format repair uses at most two attempts inside one shared 45-second budget; it never pads or truncates speech. Session output requires exactly two paragraphs and 80–140 words.
- Disposable loopback integration passed against the built C# service: registration, empty session, V2 upload, Python read-bearer CSV retrieval, grounded facts, per-run coach auth/scope/no-key/autoplay gates, session-coach auth/scope/no-key gates and revocation. The smoke test intentionally clears Gemini credentials and makes no model call.

## Limits and deployment status

No live Gemini generation, Azure deployment, physical glasses speech, phone interruption/audio routing, native accessibility or full-device acceptance was tested. The new POST /v1/sessions/{session_id}/coach route is supplied as source in the patch; running it locally does not deploy it to Azure. The owner must review and deploy it before the miniapp's server-debrief button can use that route. Local saved-results reports work independently.

Four missing external Etterna camera fixtures were skipped, so no new OCR accuracy claim is made for them. The existing crops/OCR flow remains available for review. No Etterna replay reconstruction or video synchronization was added.

This is still the React/TypeScript Mentra miniapp plus Python extraction service, not an Android APK or phone-only production release. Selected CSV pairs are cached privately; durable bulk incremental ingestion and durable coached-run tracking remain unimplemented. Original photos remain in extraction jobs for review/alignment. Compact reports use scoped phone storage. The selected handoff palette/hierarchy/controls were applied, not every proposed screen or production requirement.
