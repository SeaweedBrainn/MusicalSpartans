import { registerMiniapp } from "@mentra/miniapp/background";
import type { AppState, Channels, ExtractionResult, HistoryState, SongSummary, SessionReport, CoachingReply } from "../shared/channels";
import "../shared/channels";

// Can also be changed inside the miniapp's Settings panel.
const DEFAULT_SERVER = "http://172.16.22.56:8000";

function errorText(error: unknown): string {
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    const e = error as { code?: unknown; message?: unknown };
    if (typeof e.message === "string") return [e.code, e.message].filter(Boolean).join(": ");
    try { return JSON.stringify(error) || "Unknown error"; } catch { /* fallback */ }
  }
  return String(error);
}

function savedVolume(): number {
  const raw = localStorage.getItem("rhythm_volume");
  const value = raw === null ? 1 : Number(raw);
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 1;
}

registerMiniapp<Channels>((session) => {
  async function readHistory(): Promise<HistoryState> {
    const native = await session.storage.get("rhythm_history_v1");
    const legacy = native === null ? localStorage.getItem("rhythm_history_v1") : null;
    if (native !== null || legacy !== null) {
      const saved = JSON.parse(native || legacy || "null") as HistoryState | null;
      if (!saved || !Array.isArray(saved.currentSession) || !Array.isArray(saved.reports)) throw new Error("Saved history has an unsupported format");
      if (native === null && legacy !== null) {
        await session.storage.set("rhythm_history_v1", legacy);
        localStorage.removeItem("rhythm_history_v1");
      }
      return saved;
    }
    return { currentSession: [], reports: [] };
  }
  const state: AppState = {
    message: "Loading saved session and reports...", busy: true,
    jobId: localStorage.getItem("rhythm_job") || "", revision: 0, result: null,
    server: localStorage.getItem("rhythm_server") || DEFAULT_SERVER,
    captureSize: localStorage.getItem("rhythm_size") === "high" ? "high" : "medium",
    transferMethod: localStorage.getItem("rhythm_transfer") === "ble" ? "ble" : "auto",
    history: { currentSession: [], reports: [] }, historyReady: false, chat: [], lastCoaching: null, volume: savedVolume(), messageKind: "info",
  };

  function publish(message?: string, kind: "info" | "error" = "info") {
    if (message !== undefined) { state.message = message; state.messageKind = kind; }
    session.ui.send("status", { ...state });
    console.log(state.message);
  }
  // Keep utterances in order: simultaneous speak calls can interrupt playback.
  let speechQueue: Promise<void> = Promise.resolve();
  let speechEpoch=0;
  let automaticSpeechStopped=false;
  function speak(text: string, manual=false): Promise<void> {
    if (manual) automaticSpeechStopped=false;
    if (automaticSpeechStopped && !manual) return Promise.resolve();
    const epoch=speechEpoch;
    const clean = text.trim();
    if (!clean) {
      state.speechMessage = "No text is available to read aloud.";
      publish();
      return Promise.resolve();
    }
    speechQueue = speechQueue.then(async () => {
      if (epoch!==speechEpoch) return;
      state.speechMessage = "Preparing voice…";
      publish();
      try {
        // preferLocal allows cloud fallback when the local model is unavailable.
        // Do not set a cloud voice_id: it would prevent local synthesis.
        const result = await session.speaker.speak(clean, {
          processing: "preferLocal", volume: state.volume ?? 1, stopOtherAudio: false,
        });
        if (epoch!==speechEpoch) return;
        state.speechMessage = result?.completed === false
          ? "Speech was interrupted. Tap Read aloud to try again."
          : "Voice playback finished. If silent, check phone media volume and Bluetooth audio output.";
      } catch (e) {
        if (epoch!==speechEpoch) return;
        state.speechMessage = `Voice failed: ${errorText(e)}`;
        console.warn(state.speechMessage);
      }
      publish();
    });
    return speechQueue;
  }
  function announce(message: string, spoken = message) {
    publish(message);
    void speak(spoken);
  }
  function fail(message: string, spoken = "Something went wrong. Check the message in the app.") {
    publish(message, "error");
    void speak(spoken);
  }
  // Bounds HTTP requests INCLUDING response-body reads. Does not impose an
  // artificial timeout on takePhoto(), which is owned by the Mentra host.
  async function http<T>(path: string, options: RequestInit = {}, timeout = 15000): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(state.server + path, { ...options, signal: controller.signal });
      if (!response.ok) {
        if ((response.status === 401 || response.status === 410) && path === "/api/game-session-debrief" && state.result) {
          delete state.result.remote_session;
          state.result.session_access_revoked = true;
        }
        // Never copy arbitrary HTTP response bodies into speech or UI.
        throw new Error(`Server HTTP ${response.status}. ${response.status === 401 || response.status === 410 ? "Session access ended. Scan a fresh game QR." : "Check the extraction-service log or Settings → Debug."}`);
      }
      return await response.json() as T;
    } catch (e) {
      if (controller.signal.aborted) throw new Error(`Server request timed out. Check ${state.server} and Mac Python server.`);
      throw e;
    } finally { clearTimeout(timer); }
  }

  let lastGuidedRun = "";
  const guidedRuns = new Map<string, CoachingReply>();
  async function rememberGuide(id: string, reply: CoachingReply) {
    guidedRuns.set(id, reply);
    while (guidedRuns.size > 200) guidedRuns.delete(guidedRuns.keys().next().value!);
    await session.storage.set("rhythm_guides_v1", JSON.stringify([...guidedRuns]));
  }
  function withdrawExpiredAccess() {
    if (state.lastCoaching?.session_access_revoked && state.result) {
      delete state.result.remote_session;
      state.result.session_access_revoked = true;
    }
  }
  async function poll() {
    const jobId = state.jobId;
    for (let attempt = 0; attempt < 180; attempt++) {
      const result = await http<ExtractionResult>(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (result.status !== "processing") {
        state.result = result;
        state.revision = Date.now();
        const messages: Record<string, string> = {
          extracted: "Results extracted. Review the values and image crops on the Song page.",
          partial: "Game screen found. Readable fields and graph are shown; some text is unreadable.",
          needs_corners: "Tap Align screen and mark its four inner corners.",
          needs_better_photo: "Move closer and retake at high resolution.",
          unsupported_or_unreadable: "Check the photo, screen alignment, and supported theme.",
          qr_unreadable: (result.warnings || []).join(" "),
          qr_ambiguous: (result.warnings || []).join(" "),
          qr_found: result.csv ? "QR and CSV loaded." : "QR decoded. Open the Song page for details.",
          session_waiting: "Game session connected. Finish a song, then check for new runs.",
          session_error: (result.warnings || []).join(" ") || "Could not read game session.",
          run_analyzed: "Game CSV files loaded. Your score, sections and coaching tips are ready.",
        };
        const needsAttention = ["session_error", "qr_unreadable", "qr_ambiguous", "needs_corners", "needs_better_photo", "unsupported_or_unreadable"].includes(result.status);
        publish(messages[result.status] || (result.warnings || []).join(" ") || result.status, needsAttention ? "error" : "info");
        void speak(result.game_run ? result.game_run.run.warnings.some(w => /differs|past.*duration/i.test(w))
          ? "Game files loaded, but their data does not match. Review the files before using coaching advice."
          : "Game CSV files loaded. " + result.game_run.analysis.spoken_summary
          : result.status === "extracted" ? "Extraction complete. Open Song to review the results."
          : result.status === "partial" ? "Screen found. Some fields could not be read."
          : result.status === "needs_corners" ? "Select the screen corners in the app."
          : result.status === "qr_found" ? "QR code read."
          : result.status === "session_waiting" ? "Game session connected. Finish a song, then check for new runs in Chat."
          : "Could not read the results. Check the message in the app.");
        const cachedGuide = result.game_run ? guidedRuns.get(result.game_run.run_id) : undefined;
        if (cachedGuide) {
          state.lastCoaching = cachedGuide;
          announce("Saved guide for this attempt is ready.", "Your saved guide is in Chat.");
        }
        if (!cachedGuide && result.remote_session && result.game_run && result.game_run.run_id !== lastGuidedRun) {
          const flags = result.game_run.run.envelope;
          if (!flags?.autoplay && !flags?.summary_exceeds_format_range) {
            announce("Game CSV loaded. Generating your guide…", "Generating your guide.");
            try {
              state.lastCoaching = await http<CoachingReply>(`/api/jobs/${encodeURIComponent(jobId)}/coaching`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ review: { reviewed: false } }),
              }, 65000);
              withdrawExpiredAccess();
              if (!state.lastCoaching.session_access_revoked) {
                lastGuidedRun = result.game_run.run_id;
                await rememberGuide(result.game_run.run_id, state.lastCoaching);
              }
              publish(state.lastCoaching.provider === "rhythm_backend" ? "Your game guide is ready." : "Offline guide is ready. See Chat or Settings for the service note.");
              void speak(state.lastCoaching.coach.speech);
            } catch (e) { fail(`CSV loaded, but guide failed: ${errorText(e)}`, "Song data is ready, but the guide failed. Check the app."); }
          }
        }
        return;
      }
      await new Promise<void>((resolve) => setTimeout(resolve, 1000));
    }
    throw new Error("Processing is taking longer than expected. Tap Refresh result to check again.");
  }

  async function start(demo: boolean) {
    if (state.busy) return;
    automaticSpeechStopped=false;
    state.busy = true; state.result = null; state.lastCoaching = null; state.jobId = ""; state.revision++;
    localStorage.removeItem("rhythm_job");
    let stage = demo ? "loading sample" : "taking photo";
    try {
      let job: { job_id: string };
      if (demo) {
        publish("Loading the supplied 4K results sample...");
        job = await http("/api/demo", { method: "POST" });
      } else {
        if (!session.capabilities?.hasCamera) throw new Error("Connect camera glasses first.");
        // Voice feedback does not delay the shutter.
        announce("Taking photo. Keep your head steady.", "Taking photo. Keep steady.");
        const photo = await session.camera.takePhoto({
          size: state.captureSize, compress: "low",
          transferMethod: state.transferMethod, sound: true,
        });
        stage = "downloading photo"; publish("Downloading captured photo...");
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 30000);
        let bytes: ArrayBuffer;
        try {
          const response = await fetch(photo.photoUrl, { signal: controller.signal });
          if (!response.ok) throw new Error(`Photo HTTP ${response.status}`);
          bytes = await response.arrayBuffer();
        } finally { clearTimeout(timer); }
        stage = "uploading photo"; publish("Sending photo to the extraction server...");
        job = await http("/api/jobs?mode=auto", { method: "POST",
          headers: { "Content-Type": photo.mimeType || "image/jpeg" }, body: bytes }, 30000);
      }
      if (!job.job_id) throw new Error("Server returned no job ID.");
      state.jobId = job.job_id; localStorage.setItem("rhythm_job", job.job_id);
      stage = "extracting results"; announce("Reading the results. You can align this photo on the Song page if needed.", "Photo received. Reading the results.");
      await poll();
    } catch (e) { fail(`Failed while ${stage}: ${errorText(e)}`, "Scan failed. Check the message in the app."); }
    finally { state.busy = false; publish(); }
  }

  session.ui.on("scan", () => { void start(false); });
  session.ui.on("demo", () => { void start(true); });
  async function loadGame(payload?: string) {
    if (state.busy) return;
    state.busy = true; state.result = null; state.lastCoaching = null; state.jobId = ""; state.revision++;
    localStorage.removeItem("rhythm_job");
    publish(payload ? "Loading the game run from this backend..." : "Loading the custom-game CSV sample...");
    try {
      const job = await http<{ job_id: string }>(payload ? "/api/game-run" : "/api/game-demo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        ...(payload ? { body: JSON.stringify({ payload }) } : {}),
      }, 65000);
      if (!job.job_id) throw new Error("Server returned no job ID.");
      state.jobId = job.job_id;
      localStorage.setItem("rhythm_job", job.job_id);
      await poll();
    } catch (e) { fail(`Game run failed: ${errorText(e)}`); }
    finally { state.busy = false; publish(); }
  }
  session.ui.on("game_demo", () => { void loadGame(); });
  session.ui.on("load_game_run", ({ payload }) => {
    const text = payload.trim();
    if (text.length > 2048 || (!/^mentra-run:v1:[A-Za-z0-9_-]{1,80}$/.test(text) && !/^https?:\/\/[^\s]+\/sessions\/[a-f0-9]{32}\/\?key=[A-Za-z0-9_-]{32}$/.test(text))) {
      publish("Paste the complete game session QR link or a legacy mentra-run:v1: payload"); return;
    }
    void loadGame(text);
  });
  session.ui.on("refresh_game_session", ({ handle, runId }) => {
    void work("Checking game session for completed runs…", async () => {
      const job = await http<{ job_id: string }>("/api/game-session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ handle, run_id: runId || null }),
      }, 65000);
      state.jobId = job.job_id; state.result = null; state.lastCoaching = null;
      localStorage.setItem("rhythm_job", job.job_id);
      await poll();
    });
  });
  async function commitHistory(next: HistoryState) {
    // One write commits report creation and clearing the session atomically.
    // If phone storage is full, the old in-memory session remains available.
    if (!state.historyReady) throw new Error("Saved history is unavailable. Reopen the miniapp before editing sessions.");
    await session.storage.set("rhythm_history_v1", JSON.stringify(next));
    state.history = next;
  }
  function closeResult() {
    state.result = null; state.jobId = ""; state.lastCoaching = null; state.revision++;
    localStorage.removeItem("rhythm_job");
  }
  async function work(message: string, task: () => Promise<void>) {
    if (state.busy) return;
    state.busy = true; publish(message);
    try { await task(); }
    catch (e) { fail(errorText(e)); }
    finally { state.busy = false; publish(); }
  }
  session.ui.on("add_to_session", ({ review }) => {
    if (!state.jobId || !state.result) return;
    void work("Adding this result to the session...", async () => {
      const song = await http<SongSummary>(`/api/jobs/${encodeURIComponent(state.jobId)}/session-summary`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review }),
      });
      const previous = [...state.history.currentSession, ...state.history.reports.flatMap(r => r.songs)];
      if (previous.some(s => s.id === song.id)) throw new Error("This result is already saved in the session or a report.");
      if (state.history.currentSession.length >= 200) throw new Error("Generate a report before adding more than 200 plays.");
      await commitHistory({ ...state.history, currentSession: [...state.history.currentSession, song] });
      announce("Result added to the current session on this phone.", "Song added to your session.");
    });
  });
  session.ui.on("song_coaching", ({ review }) => {
    if (!state.jobId) return;
    void work("Generating coaching. This may take up to a minute...", async () => {
      state.lastCoaching = await http<CoachingReply>(`/api/jobs/${encodeURIComponent(state.jobId)}/coaching`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review }),
      }, 65000);
      withdrawExpiredAccess();
      if (state.result?.game_run && !state.lastCoaching.session_access_revoked) {
        await rememberGuide(state.result.game_run.run_id, state.lastCoaching);
      }
      publish(state.lastCoaching.provider === "rhythm_backend" ? "AI coaching is ready." : "Offline coaching is ready. See Chat or Settings for the connection note.");
      void speak(state.lastCoaching.coach.speech);
    });
  });
  session.ui.on("generate_report", () => {
    if (!state.history.currentSession.length) return;
    void work("Generating the session report...", async () => {
      const report = await http<SessionReport>("/api/session-report", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ songs: state.history.currentSession }),
      });
      await commitHistory({ currentSession: [], reports: [report, ...state.history.reports] });
      closeResult();
      publish("Session report saved on this phone. Open Chat, then Reports to read it.");
      void speak(report.spoken_summary);
    });
  });
  session.ui.on("discard_session", () => {
    void work("Discarding the current session...", async () => {
      await commitHistory({ ...state.history, currentSession: [] }); closeResult(); state.chat = []; announce("Current session discarded. Saved reports are retained.");
    });
  });
  session.ui.on("finish_song", () => { if (!state.busy) { closeResult(); publish("Ready for the next scan."); } });
  session.ui.on("report_coaching", ({ reportId }) => {
    const report = state.history.reports.find(r => r.id === reportId);
    if (!report) return;
    void work("Generating report coaching. This may take up to a minute...", async () => {
      state.lastCoaching = await http<CoachingReply>("/api/report-coaching", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ songs: report.songs }),
      }, 65000);
      publish("Report coaching is ready in Chat."); void speak(state.lastCoaching.coach.speech);
    });
  });
  session.ui.on("delete_reports", ({ from, to }) => {
    if (state.busy || !Number.isFinite(from) || !Number.isFinite(to) || from > to) return;
    void work("Deleting selected reports...", async () => {
      const retained = state.history.reports.filter(r => r.created_at < from || r.created_at > to);
      const deleted = state.history.reports.length-retained.length;
      await commitHistory({ ...state.history, reports: retained });
      state.chat = []; state.lastCoaching = null;
      publish(`${deleted} reports deleted. Coach conversation reset to remove stale context.`);
    });
  });
  session.ui.on("chat_send", ({ text }) => {
    const question = text.trim();
    if (state.busy || !question || question.length > 2000) return;
    if (!state.historyReady) { fail("Saved history is unavailable. Reopen the miniapp before using the coach conversation."); return; }
    const history = state.chat.slice(-20).map(m => ({ role: m.role, text: m.text.slice(0, 2000) }));
    state.chat = [...state.chat, { role: "user" as const, text: question }].slice(-100);
    void work("Coach is replying...", async () => {
      const all = [...state.history.reports.flatMap(r => r.songs), ...state.history.currentSession];
      const unique = Array.from(new Map(all.map(s => [s.id, s])).values()).sort((a,b) => a.played_at-b.played_at).slice(-20);
      const reply = await http<CoachingReply>("/api/coach-chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, songs: unique, report_notes: state.history.reports.filter(r => r.ai_debrief).slice(0,10).map(r => r.ai_debrief!.slice(0,12000)), report_count: state.history.reports.length, current_count: state.history.currentSession.length }),
      }, 65000);
      state.chat = [...state.chat, { role: "assistant" as const, text: reply.coach.speech, reply }].slice(-100);
      publish(reply.provider === "rhythm_backend" ? "AI coach replied." : "Offline coach replied.");
    });
  });
  session.ui.on("clear_chat", () => { if (!state.busy) { state.chat = []; publish("Conversation cleared."); } });
  session.ui.on("server_session_debrief", ({ handle }) => {
    void work("Preparing the server session debrief…", async () => {
      const response = await http<CoachingReply & { report?: SessionReport }>("/api/game-session-debrief", {
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({handle}),
      },65000);
      state.lastCoaching=response;
      if (response.report) {
        await commitHistory({...state.history,reports:[response.report,...state.history.reports.filter(r=>r.id!==response.report!.id)]});
      }
      publish(response.report ? "Server session debrief saved in Reports." : "Server session debrief is ready.");
      void speak(state.lastCoaching.coach.speech);
    });
  });
  session.ui.on("stop_speech", () => {
    speechEpoch++;
    automaticSpeechStopped=true;
    session.speaker.stop();
    state.speechMessage="Speech stopped.";
    publish();
  });
  session.ui.on("test_voice", () => { void speak("Voice test. Your rhythm trainer is ready.",true); });
  session.ui.on("speak_text", ({ text }) => { if (typeof text === "string") void speak(text,true); });
  session.ui.on("get_state", () => publish());
  session.ui.on("save_settings", (settings) => {
    if (state.busy) return;
    const server = settings.server.trim().replace(/\/+$/, "");
    if (!/^https?:\/\/[a-z0-9.\-]+(?::\d{1,5})?$/i.test(server)) {
      fail("Use a server origin such as http://192.168.1.42:8000 (no path)."); return;
    }
    if (server !== state.server) {
      state.jobId = ""; state.result = null; state.lastCoaching = null; state.revision++;
      localStorage.removeItem("rhythm_job");
    }
    state.server = server;
    state.captureSize = settings.captureSize === "high" ? "high" : "medium";
    state.transferMethod = settings.transferMethod === "ble" ? "ble" : "auto";
    localStorage.setItem("rhythm_server", state.server);
    localStorage.setItem("rhythm_size", state.captureSize);
    localStorage.setItem("rhythm_transfer", state.transferMethod);
    if (typeof settings.volume === "number" && Number.isFinite(settings.volume)) state.volume = Math.max(0, Math.min(1, settings.volume));
    localStorage.setItem("rhythm_volume", String(state.volume ?? 1));
    announce("Settings saved. Open Debug to test the saved server.", "Settings saved.");
  });
  session.ui.on("test_server", () => {
    if (state.busy) return;
    state.busy = true; publish("Testing server (maximum 5 seconds)...");
    void http<{ status: string; extractor_version?: string; ocr_engine?: string }>("/health", {}, 5000)
      .then((r) => publish(`Server ${r.extractor_version || "older version"} reachable. OCR: ${r.ocr_engine || "unknown"}.`))
      .catch((e) => fail(errorText(e)))
      .finally(() => { state.busy = false; publish(); });
  });
  session.ui.on("test_coach", () => {
    void work("Testing the coach service...", async () => {
      const info = await http<{ configured: boolean; reachable: boolean; gemini_configured: boolean }>("/api/coach-status", {}, 6000);
      publish(!info.configured ? "Coach service is not configured. Offline coaching is available."
        : !info.reachable ? "Cannot reach the patched RhythmBackend service. Check its terminal and RHYTHM_COACH_URL."
        : info.gemini_configured ? "RhythmBackend is reachable and its Gemini key is configured."
        : "RhythmBackend is reachable. Configure its Gemini key to enable AI replies.");
    });
  });
  session.ui.on("refresh_result", () => {
    if (state.busy || !state.jobId) return;
    state.busy = true; publish("Refreshing result...");
    void poll().catch((e) => fail(errorText(e)))
      .finally(() => { state.busy = false; publish(); });
  });
  session.ui.on("realign_auto", () => {
    if (state.busy || !state.jobId) return;
    state.busy = true; publish("Finding the game content automatically...");
    void http(`/api/jobs/${encodeURIComponent(state.jobId)}/auto-align`, { method: "POST" })
      .then(() => poll()).catch((e) => fail(errorText(e)))
      .finally(() => { state.busy = false; publish(); });
  });
  session.ui.on("correct_corners", ({ corners }) => {
    if (state.busy || !state.jobId) return;
    const valid = corners.length === 4 && corners.every((p) => p.length === 2
      && p.every((v) => Number.isFinite(v) && v >= 0 && v <= 1));
    if (!valid) { fail("Select four corners first."); return; }
    state.busy = true; publish("Straightening screen and extracting again...");
    void http(`/api/jobs/${encodeURIComponent(state.jobId)}/corners`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corners }),
    }).then(() => poll()).catch((e) => fail(errorText(e)))
      .finally(() => { state.busy = false; publish(); });
  });

  session.ui.handle("get_image", async ({ jobId, name }) => {
    if (!state.jobId || jobId !== state.jobId || !/^[a-z_]+$/.test(name)) {
      throw new Error("Image does not belong to the current scan.");
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${state.server}/api/jobs/${encodeURIComponent(jobId)}/preview/${name}`,
        { signal: controller.signal });
      if (!response.ok) throw new Error(`Image HTTP ${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      if (bytes.length > 2*1024*1024) throw new Error("Preview is too large.");
      let binary = "";
      for (let i = 0; i < bytes.length; i += 8192) {
        binary += String.fromCharCode(...bytes.subarray(i, i+8192));
      }
      const mime = name === "original" || name === "detected_content" ? "image/jpeg" : "image/png";
      return { dataUrl: `data:${mime};base64,${btoa(binary)}` };
    } finally { clearTimeout(timer); }
  });
  session.input.onButtonPress((press) => {
    if (press.pressType === "short") void start(false);
  });
  void (async () => {
    try {
      state.history = await readHistory(); state.historyReady = true;
      try {
        const saved=await session.storage.get("rhythm_guides_v1");
        const entries=saved ? JSON.parse(saved) : [];
        if (Array.isArray(entries)) for (const item of entries.slice(-200)) {
          if (Array.isArray(item) && typeof item[0] === "string" && item[1]?.coach?.speech && typeof item[1].coach.speech === "string") guidedRuns.set(item[0],item[1]);
        }
      } catch { console.warn("Saved guide cache could not be read; history remains available."); }
      publish("Ready. Turn on camera from the Glasses page.");
    } catch (e) {
      fail(`Saved history could not be loaded: ${errorText(e)}. Session editing is disabled; reopen the miniapp to retry.`);
    } finally { state.busy = false; publish(); }
  })();
});
