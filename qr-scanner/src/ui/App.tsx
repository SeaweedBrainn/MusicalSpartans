import { useEffect, useState } from "react";
import type { AppState, ExtractionResult, GameRunResult, CoachingReply, SongSummary, OcrReview } from "../shared/channels";
import "../shared/channels";
import { latencyHeatmap, OFFSET_BANDS, sectionJudgments } from "../shared/timing";

const initial: AppState = {
  message: "Connecting to miniapp…", busy: false, jobId: "", revision: 0,
  result: null, server: "", captureSize: "medium", transferMethod: "auto", volume: 1,
  history: { currentSession: [], reports: [] }, historyReady: false, chat: [], lastCoaching: null,
};
const CSS = `
/* Neutralize starter-template flex centering and root min-content sizing. */
html{width:100%;min-width:0;-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{display:block;margin:0;padding:0;width:100%;min-width:0}
#root,#app{display:block;width:100%;min-width:0;max-width:none;margin:0;padding:0;text-align:left}
.rhythm{width:100%;max-width:100%;min-width:0;--bg:#0A0A0B;--panel:#121214;--ink:#EDEBE6;--muted:#8C8A85;--accent:#FF2D6F;background:var(--bg);color:var(--ink);font:16px system-ui;min-height:100vh;box-sizing:border-box;padding:calc(54px + env(safe-area-inset-top,0px)) 18px calc(104px + env(safe-area-inset-bottom,0px));overflow-wrap:anywhere}
.rhythm *{box-sizing:border-box}.rhythm main{display:block;width:100%;max-width:720px;min-width:0;margin:0 auto;text-align:left}.rhythm h1{font-size:28px;margin:4px 0 10px}.rhythm h2{font-size:18px;margin:0 0 14px}.rhythm p{line-height:1.5}.rhythm .muted{color:var(--muted);font-size:14px}.rhythm .kicker{text-transform:uppercase;color:var(--accent);letter-spacing:.13em;font-size:11px;font-weight:700}.rhythm .panel{width:100%;max-width:100%;min-width:0;background:var(--panel);padding:18px;border:1px solid #303034;border-radius:2px;margin:16px 0}.rhythm .status{border-left:3px solid var(--accent);padding:12px 15px;background:#121214;border-radius:8px;font-size:14px;line-height:1.5}.rhythm button{max-width:100%;white-space:normal;overflow-wrap:anywhere;border:1px solid #8C8A85;background:#1A1A1D;color:var(--ink);border-radius:2px;padding:12px 15px;font:600 16px system-ui;cursor:pointer;min-height:48px}.rhythm button.primary{background:var(--accent);color:#0A0A0B;border-color:var(--accent)}.rhythm button:disabled{color:#8C8A85;background:#1A1A1D;cursor:wait}.rhythm button:focus-visible,.rhythm input:focus-visible{outline:3px solid #FF2D6F;outline-offset:3px}.rhythm .debrief-text{white-space:pre-line;font-size:17px;line-height:1.55}.rhythm .actions{min-width:0;max-width:100%;display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.rhythm .metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.rhythm .metric{min-width:0;max-width:100%;background:#0A0A0B;padding:16px;border-radius:2px}.rhythm .metric strong{font-size:clamp(20px,6vw,26px);font-variant-numeric:tabular-nums;display:block;margin-top:6px}.rhythm .metric small{color:var(--muted)}.rhythm .rows{table-layout:fixed;width:100%;border-collapse:collapse;font-size:15px}.rhythm td{padding:10px 0;border-bottom:1px solid #303034}.rhythm td:last-child{text-align:right;font-variant-numeric:tabular-nums}.rhythm .song{white-space:pre-line;font-size:15px}.rhythm img{width:100%;height:auto;display:block;border-radius:9px}.rhythm .image-error{color:#ffd390}.rhythm label{display:block;font-size:14px;color:var(--muted);margin:14px 0 6px}.rhythm input,.rhythm select{width:100%;max-width:100%;min-width:0;padding:11px;border:1px solid #8C8A85;border-radius:8px;background:#0A0A0B;color:var(--ink);font:16px system-ui}.rhythm summary{cursor:pointer;font-weight:600;padding:4px 0}.rhythm pre{width:100%;max-width:100%;min-width:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#c6d4e1;max-height:420px;overflow:auto}.rhythm .corner-photo{position:relative;cursor:crosshair;touch-action:manipulation}.rhythm .corner-photo svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.rhythm .corner-dot{position:absolute;width:26px;height:26px;background:#8cf0c3;color:#0A0A0B;border:2px solid white;border-radius:50%;transform:translate(-50%,-50%);display:grid;place-items:center;font-weight:800;pointer-events:none}.rhythm .warning{font-size:13px;color:#f5d699;margin:8px 0}.rhythm .badge{color:var(--accent);font-size:12px}.rhythm .app-nav{position:fixed;bottom:0;left:0;right:0;z-index:10;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:#121214;border-top:1px solid #303034;padding:8px max(8px,env(safe-area-inset-right,0px)) calc(8px + env(safe-area-inset-bottom,0px)) max(8px,env(safe-area-inset-left,0px));gap:4px}.rhythm .app-nav button{background:transparent;border:0;color:var(--muted);padding:10px 3px;font-size:14px}.rhythm .app-nav button[aria-current="page"]{color:var(--accent);background:#FF2D6F12}.rhythm .page-heading{margin:28px 0 24px}.rhythm .camera-panel{text-align:center;padding:44px 20px;min-height:350px;display:flex;flex-direction:column;align-items:center;justify-content:center}.rhythm .camera-mark{width:96px;height:96px;border:1px solid #FF2D6F66;display:grid;place-items:center;margin:0 0 26px;color:var(--accent)}.rhythm .camera-mark svg{width:44px;height:44px}.rhythm .camera-panel .actions{justify-content:center;width:100%}.rhythm .camera-panel button.primary{width:min(100%,340px)}.rhythm .secondary-link{background:transparent;border-color:#303034}.rhythm .subnav{display:flex;gap:6px;flex-wrap:wrap;margin:20px 0}.rhythm .subnav button{flex:1}.rhythm .subnav button[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}.rhythm .notice{border-left:3px solid #f5d699;background:#211b17;padding:14px;font-size:14px;margin:16px 0}.rhythm .empty{padding:28px 4px}.rhythm .empty p{color:var(--muted)}.rhythm textarea{width:100%;padding:12px;border:1px solid #8C8A85;border-radius:2px;background:#0A0A0B;color:var(--ink);font:inherit}.rhythm textarea:focus-visible,.rhythm select:focus-visible,.rhythm summary:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.rhythm input[type="range"]{accent-color:var(--accent);padding:0;min-height:48px}.rhythm .page-heading p{color:var(--muted);margin-top:8px}.rhythm figure{margin:12px 0}.rhythm figcaption{font-size:12px;color:var(--muted);margin-top:8px}
.rhythm .heatmap-scroll{display:block;width:100%;max-width:100%;min-width:0;contain:inline-size;overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}
.rhythm .heatmap-scroll svg{display:block;max-width:none}
@media(max-width:440px){.rhythm{padding-left:14px;padding-right:14px}.rhythm .panel{padding:16px}.rhythm .metrics{grid-template-columns:minmax(0,1fr)}.rhythm .metric strong{font-size:26px}.rhythm .actions>button{flex:1 1 140px}.rhythm .app-nav button{font-size:13px}}
`;

function show(value: unknown, suffix = ""): string {
  return value === null || value === undefined ? "Unreadable / not shown" : `${value}${suffix}`;
}
function ImagePreview({ jobId, revision, name }: { jobId: string; revision: number; name: string }) {
  const [dataUrl, setDataUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setDataUrl(""); setError("");
    mentra.request("get_image", { jobId, name }, { timeout: 20000 })
      .then((r) => { if (alive) setDataUrl(r.dataUrl); })
      .catch((e) => { if (alive) setError(String(e?.message || e)); });
    return () => { alive = false; };
  }, [jobId, revision, name]);
  if (error) return <p className="image-error">Image unavailable: {error}</p>;
  if (!dataUrl) return <p className="muted">Loading image…</p>;
  return <img src={dataUrl} alt={name.replace(/_/g, " ")} />;
}

function CornerEditor({ state, onClose }: { state: AppState; onClose: () => void }) {
  const [dataUrl, setDataUrl] = useState("");
  const [error, setError] = useState("");
  const [points, setPoints] = useState<number[][]>([]);
  useEffect(() => {
    let alive = true;
    mentra.request("get_image", { jobId: state.jobId, name: "original" }, { timeout: 20000 })
      .then((r) => { if (alive) setDataUrl(r.dataUrl); })
      .catch((e) => { if (alive) setError(String(e?.message || e)); });
    return () => { alive = false; };
  }, [state.jobId]);
  return <section className="panel">
    <h2>Align screen</h2>
    <p className="muted">Optional correction: tap the four corners of the GAME IMAGE, not the laptop bezel or macOS window. Exclude the menu bar, Preview toolbar and Dock. Order: top-left, top-right, bottom-right, bottom-left.</p>
    {error && <p className="image-error">{error}</p>}
    {!dataUrl && !error && <p>Loading photo…</p>}
    {dataUrl && <div className="corner-photo" data-testid="corner-photo" onClick={(event) => {
      if (state.busy || points.length >= 4) return;
      const box = event.currentTarget.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const x = Math.max(0, Math.min(1, (event.clientX-box.left)/box.width));
      const y = Math.max(0, Math.min(1, (event.clientY-box.top)/box.height));
      setPoints((p) => [...p, [x, y]]);
    }}>
      <img src={dataUrl} alt="Captured monitor. Tap its four screen corners." />
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <polyline points={points.map((p) => `${p[0]*100},${p[1]*100}`).join(" ")
          + (points.length === 4 ? ` ${points[0][0]*100},${points[0][1]*100}` : "")}
          fill="none" stroke="#8cf0c3" strokeWidth="0.5" />
      </svg>
      {points.map((p, i) => <span key={i} className="corner-dot" style={{ left: `${p[0]*100}%`, top: `${p[1]*100}%` }}>{i+1}</span>)}
    </div>}
    <p className="muted">{points.length} / 4 corners selected</p>
    <div className="actions">
      <button disabled={state.busy} onClick={() => setPoints([])}>Reset corners</button>
      <button className="primary" disabled={state.busy || points.length !== 4} onClick={() => {
        mentra.send("correct_corners", { corners: points }); onClose();
      }}>Straighten and extract</button>
      <button onClick={onClose}>Close</button>
    </div>
  </section>;
}

function ResultCards({ result }: { result: ExtractionResult }) {
  const d = result.data;
  if (!d) return null;
  const timingLabels: Record<string, string> = {
    mean_ms: "Mean offset", mean_absolute_ms: "Mean absolute offset",
    standard_deviation_ms: "Standard deviation", smallest_ms: "Smallest offset",
    largest_ms: "Largest offset", left_cbs: "Left CBs", right_cbs: "Right CBs",
  };
  const ratioLabels: Record<string, string> = { ra: "RA", ma: "MA", pa: "PA", longest_mfc: "Longest MFC", longest_pfc: "Longest PFC" };
  return <>
    <section className="panel">
      <h2>Current result <span className="badge">{d.grade?.value || ""}</span></h2>
      <div className="metrics">
        <div className="metric"><small>Accuracy</small><strong>{show(d.accuracy_percent.value, "%")}</strong></div>
        <div className="metric"><small>Playback rate</small><strong>{show(d.playback_rate.value, "×")}</strong></div>
      </div>
      <p className="muted">{d.accuracy_label.value || "Scoring label unreadable"}</p>
      <p className="song">{d.song_text}</p>
      {d.unlabeled_ratings_text.length > 0 && <p className="muted">Displayed ratings: {d.unlabeled_ratings_text.join(" · ")}</p>}
    </section>
    <section className="panel"><h2>Judgments</h2><table className="rows"><tbody>
      {Object.entries(d.judgments).map(([name, value]) => <tr key={name}><td style={{ textTransform: "capitalize" }}>{name}</td><td>{show(value.value)}</td></tr>)}
    </tbody></table></section>
    <section className="panel"><h2>Timing</h2><table className="rows"><tbody>
      {Object.entries(d.timing).map(([name, value]) => <tr key={name}><td>{timingLabels[name] || name}</td><td>{show(value.value, name.endsWith("_ms") ? " ms" : "")}</td></tr>)}
    </tbody></table></section>
    <details className="panel"><summary>Holds, ratios and streaks</summary><table className="rows"><tbody>
      {Object.entries(d.auxiliary_counts).map(([name, f]) => <tr key={name}><td style={{ textTransform: "capitalize" }}>{name}</td><td>{f.value ? `${f.value.first} / ${f.value.second}` : "Unreadable / not shown"}</td></tr>)}
      {Object.entries(d.ratios_and_streaks || {}).map(([name, f]) => <tr key={name}><td>{ratioLabels[name] || name}</td><td>{show(f.value)}</td></tr>)}
    </tbody></table></details>
  </>;
}

function timeLabel(ms: number): string {
  return `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2, "0")}`;
}
function timingLabel(ms: number | null): string {
  return ms === null ? "Not supplied" : `${Math.abs(ms).toFixed(2)} ms ${ms < 0 ? "early" : ms > 0 ? "late" : "on time"}`;
}
function LatencyHeatmap({ game }: { game: GameRunResult }) {
  const [selected, setSelected] = useState(0);
  const map = latencyHeatmap(game);
  const index = Math.min(selected, map.columns.length - 1);
  const column = map.columns[index];
  const unit = map.noteLevel ? "hits" : "sample means";
  const left = 106, cellWidth = 28, rowHeight = 22, top = 24;
  const width = left + map.columns.length * cellWidth + 12;
  const endLabel = (ms: number) => timeLabel(Math.ceil(ms / 1000) * 1000);
  const windowLabel = (c: typeof column) => `${timeLabel(c.startMs)}–${endLabel(c.endMs)}`;
  return <section className="panel"><h2>Latency heatmap</h2>
    <p className="muted">{map.noteLevel ? "Successful P/G note offsets over song time. Negative is early; positive is late." : "Timeline average offsets over song time. These are sample means, not individual note offsets or within-sample spread."}</p>
    {!map.measured ? <p>No measured {map.noteLevel ? "successful-hit latencies" : "timeline offsets"} are available for a heatmap.</p> : <>
      <p className="muted">Brighter cells contain more {unit}. Each column covers {map.windowMs / 1000} seconds. Scroll sideways and tap a column, or use the selector.</p>
      <div className="heatmap-scroll" role="region" aria-label="Scrollable latency heatmap" tabIndex={0}>
        <svg role="img" aria-label={`Latency heatmap: ${map.measured} ${unit}, early below zero and late above zero. Use Inspect time window for the numeric values.`}
          viewBox={`0 0 ${width} 330`} style={{ display: "block", width: Math.max(width, 280), height: 330 }}>
          <text x="0" y="13" fill="#8C8A85" fontSize="11">Offset (ms)</text>
          {OFFSET_BANDS.map((band, row) => <g key={band.label}>
            <text x={left - 8} y={top + row * rowHeight + 14} fill={row === 5 ? "#EDEBE6" : "#8C8A85"} fontSize="11" textAnchor="end">{band.label}</text>
            {map.columns.map((c, col) => <rect key={col} x={left + col * cellWidth} y={top + row * rowHeight}
              width={cellWidth - 2} height={rowHeight - 2} style={{ cursor: "pointer" }}
              fill={c.counts[row] ? `rgba(255,45,111,${0.2 + 0.8 * c.counts[row] / map.maxCount})` : "#222226"}
              onClick={() => setSelected(col)}><title>{windowLabel(c)} · {band.label} ms: {c.counts[row]} {unit}</title></rect>)}
          </g>)}
          <rect x={left + index * cellWidth - 1} y={top - 2} width={cellWidth} height={rowHeight * OFFSET_BANDS.length + 2} fill="none" stroke="#EDEBE6" strokeWidth="1" pointerEvents="none" />
          {map.columns.map((c, col) => (col % Math.max(1, Math.ceil(map.columns.length / 8)) === 0) && <text key={col} x={left + col * cellWidth} y="288" fill="#8C8A85" fontSize="11">{timeLabel(c.startMs)}</text>)}
          <text x={left} y="310" fill="#8C8A85" fontSize="11">Song time → · {map.noteLevel ? "note counts" : "sample counts"}</text>
        </svg>
      </div>
      <label htmlFor="heatmap-window">Inspect time window</label><select id="heatmap-window" value={index} onChange={e => setSelected(Number(e.target.value))}>
        {map.columns.map((c, i) => <option key={i} value={i}>{windowLabel(c)} · {c.measured} {unit}{map.noteLevel ? ` · ${c.misses} misses` : ""}</option>)}
      </select>
      <p aria-live="polite">{windowLabel(column)}: {column.measured} measured {unit}; {map.noteLevel ? "mean offset" : "mean of sample means"} {timingLabel(column.meanMs)}{map.noteLevel ? `; ${column.misses} misses` : ""}.</p>
      <details><summary>Selected window values</summary><table className="rows"><thead><tr><th style={{textAlign:"left"}}>Offset (ms)</th><th>{map.noteLevel ? "Hits" : "Samples"}</th></tr></thead><tbody>
        {OFFSET_BANDS.map((band, row) => <tr key={band.label}><td>{band.label}</td><td>{column.counts[row]}</td></tr>)}
      </tbody></table></details>
    </>}
    <p className="muted">{map.measured} measured {unit}. {map.missing} {map.noteLevel ? "hits" : "active samples"} without latency are not plotted.{map.noteLevel ? ` ${map.misses} misses are counted separately; their offsets are excluded.` : " No note-level distribution can be recovered from averages."} Zero milliseconds is a real measurement. Offset buckets are display ranges, not game judgment windows.</p>
  </section>;
}

function GameRunCards({ game }: { game: GameRunResult }) {
  const summary = game.run.summary;
  const analysis = game.analysis;
  const difficulty = ["Unknown", "Beginner", "Easy", "Medium", "Hard"][summary.difficulty] || "Unknown";
  const excluded = game.run.envelope?.autoplay || game.run.envelope?.summary_exceeds_format_range;
  const mismatch = excluded || game.run.warnings.some(w => /differs|past.*duration/i.test(w));
  return <>
    <section className="panel">
      <div className="kicker">{game.run.format_version === 2 ? "Custom game · V2 note CSV" : game.run.envelope ? "Custom game · V1 session CSV" : "Legacy demo/local CSV"}</div>
      <h2>Song {summary.song_id} <span className="badge">{analysis.grade}</span></h2>
      <p className="muted">Game {summary.game_id} · {difficulty} · Chart {game.run.chart_id ?? "not supplied"}</p>
      <div className="metrics">
        <div className="metric"><small>Game score</small><strong>{analysis.score.toLocaleString("en-US")}</strong></div>
        <div className="metric"><small>{analysis.accuracy_is_approximate ? "Approximate accuracy" : "Accuracy"}</small><strong>{analysis.accuracy === null ? "Not supplied" : `${analysis.accuracy_is_approximate ? "≈ " : ""}${(analysis.accuracy*100).toFixed(analysis.accuracy_is_approximate ? 1 : 2)}%`}</strong></div>
      </div>
      {game.run.format_version === 2 && <p className="muted">V2 note data · {game.run.notes?.length || 0} judged rows. Accuracy uses rounded deltas; score remains separate. No grade is inferred.</p>}
      {analysis.accuracy_coverage_uncertain && <p className="warning">Approximate accuracy covers captured judgements; note gaps or partial data may omit changes.</p>}
      {analysis.judgments && <p>P: {analysis.judgments.P} · G: {analysis.judgments.G} · M: {analysis.judgments.M}</p>}
      <p>Mean timing: <strong>{timingLabel(analysis.mean_offset_ms)}</strong></p>
      <p className="muted">{timeLabel(summary.game_time_ms)} · {summary.bpm} BPM · {summary.total_notes} notes</p>
    </section>
    <section className="panel"><h2>Coaching tips</h2>
      {mismatch ? <p className="warning">Review the game-file mismatch before using coaching tips.</p> : analysis.tips.length ? analysis.tips.map((tip, i) => <p key={i}>
        <strong>{tip.spans_song ? "Whole song" : timeLabel(tip.time_ms)}: </strong>{tip.text}
      </p>) : <p>No timing issue was flagged by these rules.</p>}
      <p className="muted">Rule-based analysis from the game's CSV data.</p>
    </section>
    <section className="panel"><h2>{game.run.sample_interval_sec === 2 ? "Ten-second sections" : "Five-second sections"}</h2>
      {game.run.format_version === 2 && <p className="muted">Section hit rate counts P and G as hits, divided by all captured judgments. It is not weighted game accuracy. The CSV's running accuracy deltas cannot supply an independent accuracy percentage for each section.</p>}
      {analysis.sections.length ? analysis.sections.map((section) => {
        const judgments = game.run.format_version === 2 ? sectionJudgments(game, section.start_ms, section.end_ms) : null;
        const end = summary.game_time_ms > section.start_ms ? Math.min(section.end_ms, summary.game_time_ms) : section.end_ms;
        return <div key={section.start_ms} style={{ marginBottom: 22 }}>
          <p><strong>{timeLabel(section.start_ms)}–{timeLabel(end)}</strong></p>
          {judgments ? <>
            <p>Hit rate: <strong>{judgments.hitRate === null ? "No judged notes" : `${(judgments.hitRate * 100).toFixed(1)}%`}</strong></p>
            <p className="muted">P: {judgments.perfect} · G: {judgments.good} · M: {judgments.misses} · {judgments.judged} captured judgments</p>
          </> : <>
            <p>{section.accuracy === null ? "No accuracy measurement for this interval" : `Reported accuracy: ${(section.accuracy * 100).toFixed(1)}%`}</p>
            {section.accuracy !== null && <progress aria-label={`Accuracy at ${timeLabel(section.start_ms)}`} value={section.accuracy} max={1} style={{ width: "100%", accentColor: "#FF2D6F", height: 12 }} />}
          </>}
          <p className="muted">Mean offset: {timingLabel(section.mean_offset_ms)}{section.spread_ms !== null ? ` · spread (SD) ${section.spread_ms.toFixed(2)} ms` : " · spread unavailable"}</p>
        </div>;
      }) : <p>No playable timeline samples were supplied. Section measurements are unavailable.</p>}
    </section>
    <LatencyHeatmap key={game.run_id} game={game} />
    <details className="panel"><summary>Game files & timeline</summary>
      <p className="muted">Run ID: {game.run_id}</p>
      <p>{game.run.format_version === 2 ? `${game.run.notes?.length || 0} note-level rows; NPS is density, not note count.` : `${game.run.samples.length} timeline samples.`} Empty measurements remain unknown.</p>
      <pre>{JSON.stringify(game.run.format_version === 2 ? game.run.notes : game.run.samples, null, 2)}</pre>
    </details>
  </>;
}

function CoachingCard({ reply }: { reply: CoachingReply }) {
  const coach = reply.coach;
  return <section className="panel"><h2>{coach.mode === "session_debrief" ? "Session debrief" : reply.provider === "rhythm_backend" ? "AI coaching" : "Offline coaching"}</h2>
    {reply.coaching_route === "session_api" && <p className="muted">Game guide route: session CSV API.</p>}
    {reply.session_access_revoked && <p className="warning">Session access was withdrawn. Scan a fresh game QR to reconnect.</p>}
    {reply.fallback_reason && <p className="warning">{reply.fallback_reason}</p>}
    <p className="debrief-text">{coach.speech}</p>
    {coach.phone_text.filter(line=>line.trim()!==coach.speech.trim()).map((line,i)=><p key={i}>{line}</p>)}
    {coach.focus_section && <p>Focus: {timeLabel(coach.focus_section.start_s*1000)}–{timeLabel(coach.focus_section.end_s*1000)} · {coach.focus_section.reason}</p>}
    {coach.drill && <p><strong>Drill:</strong> {coach.drill}</p>}
    {coach.next_target && <p><strong>Next target:</strong> {coach.next_target}</p>}
    <button onClick={() => mentra.send("speak_text", { text: coach.speech })}>Read coaching aloud</button>
    <details><summary>Data notes</summary>{coach.data_notes.map((note,i) => <p className="muted" key={i}>{note}</p>)}
      <p className="muted">Confidence: {coach.confidence} · Basis: {coach.evidence_basis.replace(/_/g," ")}</p></details>
  </section>;
}

function ResultActions({ state, onCoach }: { state: AppState; onCoach: () => void }) {
  const result = state.result;
  const [reviewed, setReviewed] = useState(false);
  const [accuracy, setAccuracy] = useState(String(result?.data?.accuracy_percent.value ?? ""));
  const [mean, setMean] = useState(String(result?.data?.timing.mean_ms?.value ?? ""));
  const [grade, setGrade] = useState(String(result?.data?.grade?.value ?? ""));
  if (!result || (!result.game_run && !result.data)) return null;
  const isScreen = !result.game_run;
  const id = result.game_run ? "run-"+result.game_run.run_id : "scan-"+state.jobId;
  const saved = [...state.history.currentSession, ...state.history.reports.flatMap(r => r.songs)].some(s => s.id === id);
  const valid = (accuracy === "" || (Number.isFinite(Number(accuracy)) && Number(accuracy) >= 0 && Number(accuracy) <= 100))
    && (mean === "" || Number.isFinite(Number(mean)));
  const review: OcrReview = isScreen ? { reviewed, accuracy_pct: accuracy === "" ? null : Number(accuracy),
    mean_offset_ms: mean === "" ? null : Number(mean), native_grade: grade.trim() || null } : { reviewed: false };
  return <section className="panel"><h2>Save this song</h2>
    {isScreen && <>
      <p className="muted">Check these screen values before saving or coaching. Correct them here; leave a field blank if you cannot verify it.</p>
      <label htmlFor="review-accuracy">Reviewed accuracy (%)</label><input id="review-accuracy" type="number" min="0" max="100" step="any" value={accuracy} onChange={e => setAccuracy(e.target.value)} />
      <label htmlFor="review-mean">Reviewed mean timing (ms; negative is early)</label><input id="review-mean" type="number" step="any" value={mean} onChange={e => setMean(e.target.value)} />
      <label htmlFor="review-grade">Native game grade</label><input id="review-grade" maxLength={30} value={grade} onChange={e => setGrade(e.target.value)} />
      <label><input type="checkbox" style={{ width: "auto", marginRight: 8 }} checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I checked these accuracy, timing and grade values.</label>
    </>}
    <div className="actions">
      <button disabled={state.busy || !state.historyReady || saved || !valid || (isScreen && !reviewed)} onClick={() => mentra.send("add_to_session", { review })}>{saved ? "Already saved" : "Add to session"}</button>
      <button disabled={state.busy || !valid || (isScreen && !reviewed)} onClick={() => { mentra.send("song_coaching", { review }); onCoach(); }}>Get coaching</button>
      <button disabled={state.busy} onClick={() => mentra.send("finish_song", {})}>Done with result</button>
    </div>
    <p className="muted">Sessions and reports are saved in this miniapp on your phone. Coaching uses the configured service, with an offline fallback.</p>
  </section>;
}

function SongList({ songs }: { songs: SongSummary[] }) {
  return <>{songs.map((song) => <div key={song.id} style={{ borderBottom: "1px solid #303034", padding: "10px 0" }}>
    <strong>{song.title}</strong><span className="badge"> · {song.native_grade || "grade unknown"}</span>
    <p>{song.accuracy_pct === null ? "Accuracy unknown" : `${song.accuracy_is_approximate ? "≈ " : ""}${song.accuracy_pct.toFixed(1)}%`} · {timingLabel(song.mean_offset_ms)}</p>
    <p className="muted">{song.source === "screen_ocr" ? "Reviewed screen scan" : "Game CSV"} · {new Date(song.played_at).toLocaleString()}</p>
    {song.weakest_section && <p className="muted">Recorded lowest section: {timeLabel(song.weakest_section.start_s*1000)} · {song.weakest_section.accuracy_pct.toFixed(1)}%</p>}
    {!song.usable_for_coaching && <p className="warning">Data issue: this play is excluded from coaching comparisons.</p>}
  </div>)}</>;
}

type Page = "glasses" | "song" | "chat" | "settings";
type ChatView = "sessions" | "reports" | "coach";

export function App() {
  const [state, setState] = useState<AppState>(initial);
  const [page, setPage] = useState<Page>("glasses");
  const [chatView, setChatView] = useState<ChatView>("sessions");
  const [align, setAlign] = useState(false);
  const [server, setServer] = useState("");
  const [size, setSize] = useState<"medium" | "high">("medium");
  const [transfer, setTransfer] = useState<"auto" | "ble">("auto");
  const [volume, setVolume] = useState(1);
  const [cropName, setCropName] = useState("results");
  const [question, setQuestion] = useState("");
  const [deleteFrom, setDeleteFrom] = useState("");
  const [deleteTo, setDeleteTo] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    // A missing viewport meta otherwise gives iOS a desktop-width layout.
    if (!document.querySelector('meta[name="viewport"]')) {
      const meta = document.createElement("meta");
      meta.name = "viewport";
      meta.content = "width=device-width, initial-scale=1, viewport-fit=cover";
      document.head.appendChild(meta);
    }
  }, []);
  useEffect(() => {
    const off = mentra.on("status", (s) => setState({ ...initial, ...s }));
    mentra.send("get_state", {});
    return off;
  }, []);
  useEffect(() => { setServer(state.server); setSize(state.captureSize); setTransfer(state.transferMethod); setVolume(state.volume ?? 1); },
    [state.server, state.captureSize, state.transferMethod, state.volume]);
  useEffect(() => { setAlign(false); }, [state.jobId]);
  useEffect(() => { window.scrollTo(0, 0); }, [page, chatView]);
  useEffect(() => {
    const names = Object.keys(state.result?.crops || {});
    setCropName(names.includes("results") ? "results" : names[0] || "results");
  }, [state.revision]);
  const result = state.result;
  const hasSong = !!(result?.game_run || result?.data);
  const isScreenPhoto = !!result && !result.game_run && result.source !== "game_session" && result.source !== "game_csv";
  const voiceFailed = /failed|interrupted|unavailable/i.test(state.speechMessage || "");
  const openSessions = () => { setPage("chat"); setChatView("sessions"); };
  const stopSpeech = <button className="secondary-link" onClick={() => mentra.send("stop_speech", {})}>Stop speech</button>;
  return <div className="rhythm"><style>{CSS}</style><main>
    <div className="kicker">Rhythm trainer</div>
    <header className="page-heading"><h1>{({ glasses: "Glasses", song: "Song", chat: "Chat", settings: "Settings" })[page]}</h1>
      <p>{({ glasses: "Look at the screen. Let your glasses do the reading.", song: "Your song, score and timing in one place.", chat: "Review your session. Talk through what comes next.", settings: "Audio, capture preferences and support." })[page]}</p>
    </header>
    {state.busy && page !== "glasses" && <p className="muted" role="status">Working…</p>}
    {state.messageKind === "error" && <div className="notice" role="alert"><p>{state.message}</p>
      {page !== "settings" && <button onClick={() => setPage("settings")}>Open settings</button>}</div>}
    {voiceFailed && page !== "settings" && <div className="notice" role="alert">Voice needs attention. <button onClick={() => setPage("settings")}>Check audio settings</button></div>}
    {page === "glasses" && <>
      <section className="panel camera-panel" aria-label="Camera controls">
        <div className="camera-mark" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 15h10l4-6h8l4 6h10v25H6z"/><circle cx="24" cy="27" r="8"/></svg></div>
        <h2>Scan through your glasses</h2>
        <p className="muted">Read a game QR or an Etterna results screen.</p>
        <div className="actions"><button className="primary" disabled={state.busy} onClick={() => mentra.send("scan", {})}>{state.busy ? "Working…" : "Turn on camera"}</button></div>
        <p className="muted">Takes one photo per scan. Keep your head steady.</p>
        {hasSong && <button className="secondary-link" onClick={() => setPage("song")}>View song data</button>}
      </section>
      <div className="actions"><button onClick={openSessions}>See sessions</button>{stopSpeech}</div>
    </>}

    {page === "song" && <>
      {!result && <section className="empty"><h2>No song loaded</h2><p>Use your glasses to scan a game QR or an Etterna results screen.</p><button onClick={() => setPage("glasses")}>Go to glasses</button></section>}
      {result?.session_access_revoked && <p className="notice">Session access ended. Scan a fresh game QR on the Glasses page.</p>}
      {state.jobId && <div className="actions">
        {isScreenPhoto && <><button disabled={state.busy} onClick={() => mentra.send("realign_auto", {})}>Retry auto alignment</button>
          <button disabled={state.busy} onClick={() => setAlign((s) => !s)}>Adjust alignment</button></>}
        <button disabled={state.busy} onClick={() => mentra.send("refresh_result", {})}>Refresh result</button>
      </div>}
      {align && state.jobId && <CornerEditor key={"align-"+state.jobId} state={state} onClose={() => setAlign(false)} />}
      {result?.game_run && <GameRunCards game={result.game_run} />}
      {result && <ResultCards result={result} />}
      {hasSong && <ResultActions key={"actions-"+state.jobId} state={state} onCoach={() => { setPage("chat"); setChatView("coach"); }} />}
      {result && !hasSong && <section className="panel"><h2>{result.remote_session ? "Waiting for a completed song" : "No readable song data yet"}</h2>
        <p className="muted">{result.remote_session ? "Open sessions to check for finished attempts." : "Try another scan. Photo correction and warnings are available in the app."}</p>
        <div className="actions"><button onClick={result.remote_session ? openSessions : () => setPage("glasses")}>{result.remote_session ? "See sessions" : "Go to glasses"}</button><button onClick={() => setPage("settings")}>View warnings</button></div>
      </section>}
      {result?.crops?.offset_graph && <section className="panel"><h2>Timing graph</h2><figure><ImagePreview jobId={state.jobId} revision={state.revision} name="offset_graph" /><figcaption>Image crop only. Exact note events and timestamps are not reconstructed.</figcaption></figure></section>}
      {result?.crops && Object.keys(result.crops).length > 0 && <details className="panel"><summary>Song image crops</summary>
        <label htmlFor="crop">Panel</label><select id="crop" value={cropName} onChange={(e) => setCropName(e.target.value)}>
          {Object.keys(result.crops).map((name) => <option key={name} value={name}>{name.replace(/_/g, " ")}</option>)}
          <option value="overlay">Alignment overlay</option><option value="original">Original photo</option>
        </select><figure><ImagePreview jobId={state.jobId} revision={state.revision} name={cropName} /></figure>
      </details>}
      {result?.source === "qr" && <section className="panel"><h2>QR data</h2><p>{result.qr_payload}</p>
        {result.csv && <><p>{result.csv.rows.length} CSV rows loaded.</p><pre>{JSON.stringify(result.csv.rows.slice(0, 20), null, 2)}</pre></>}
      </section>}
      {result && <p className="muted">Warnings and technical evidence are in Settings.</p>}
      {hasSong && <button onClick={() => { setPage("chat"); setChatView("coach"); }}>Open coach</button>}
    </>}

    {page === "chat" && <>
      <div className="subnav" role="group" aria-label="Chat sections">{(["sessions", "reports", "coach"] as const).map(tab => <button key={tab} aria-pressed={chatView === tab} onClick={() => setChatView(tab)}>{({sessions: "Sessions", reports: "Reports", coach: "Coach"})[tab]}</button>)}</div>
      <div className="actions">{stopSpeech}</div>
      {chatView === "sessions" && <>
        {result?.remote_session && <section className="panel"><h2>Linked game session</h2>
          <p>{result.remote_session.run_count} completed attempts.</p>
          <button disabled={state.busy} onClick={() => mentra.send("refresh_game_session", { handle: result.remote_session!.handle })}>Check for new runs</button>
          <div className="actions">{result.remote_session.runs.map(run => <button key={run.run_id} disabled={state.busy} aria-pressed={run.run_id === result.remote_session!.selected_run_id}
            onClick={() => { mentra.send("refresh_game_session", { handle: result.remote_session!.handle, runId: run.run_id }); setPage("song"); }}>Attempt {run.sequence} · Song {run.song_id}{run.autoplay ? " · Autoplay" : ""}</button>)}</div>
          <button disabled={state.busy} onClick={() => { mentra.send("server_session_debrief", { handle: result.remote_session!.handle }); setChatView("reports"); }}>Request server session debrief</button>
          <p className="muted">Requires the session-report endpoint on the linked game server.</p>
        </section>}
        <section className="panel"><h2>Current session</h2><p className="muted">Results you added on this phone. The server debrief covers the linked game session.</p>
          {state.history.currentSession.length ? <SongList songs={state.history.currentSession} /> : <p>No songs added yet. Use Add to session on the Song page.</p>}
          <div className="actions"><button disabled={state.busy || !state.historyReady || !state.history.currentSession.length} onClick={() => { mentra.send("generate_report", {}); setChatView("reports"); }}>Generate session report</button></div>
        </section>
      </>}
      {chatView === "reports" && <>
        {state.lastCoaching?.coach.mode === "session_debrief" && <CoachingCard reply={state.lastCoaching} />}
        <section className="panel"><h2>Saved reports</h2>{!state.history.reports.length && <p>Generate a report from Sessions to keep it here.</p>}
          {state.history.reports.map(report => <details className="panel" key={report.id}><summary>{new Date(report.created_at).toLocaleString()} · {report.songs.length} plays</summary>
            {report.ai_debrief && <p className="debrief-text">{report.ai_debrief}</p>}
            {report.highlights.map((line,i) => <p key={i}>{line}</p>)}<SongList songs={report.songs} />
            <div className="actions"><button onClick={() => mentra.send("speak_text", { text: report.spoken_summary })}>Read report aloud</button>
              <button disabled={state.busy} onClick={() => { mentra.send("report_coaching", { reportId: report.id }); setChatView("coach"); }}>Coach this report</button></div>
            <details><summary>Full report text</summary><pre>{report.text}</pre></details>
          </details>)}
        </section>
      </>}
      {chatView === "coach" && <>
        {state.lastCoaching && <CoachingCard reply={state.lastCoaching} />}
        <section className="panel"><h2>Coach conversation</h2>
          <p className="muted">Ask about your current session and saved reports.</p>
          {state.chat.map((message,i) => <div key={i} className="status" style={{ marginBottom: 12 }}><strong>{message.role === "user" ? "You" : message.reply?.provider === "rhythm_backend" ? "AI coach" : "Offline coach"}</strong><p className="debrief-text">{message.text}</p>
            {message.reply?.fallback_reason && <p className="warning">{message.reply.fallback_reason}</p>}
            {message.role === "assistant" && <button onClick={() => mentra.send("speak_text", { text: message.text })}>Read reply aloud</button>}
          </div>)}
          <div className="actions">{["How is my timing?", "What was my highest accuracy?", "How has my accuracy changed?"].map(text => <button key={text} disabled={state.busy || !state.historyReady} onClick={() => mentra.send("chat_send", { text })}>{text}</button>)}</div>
          <form onSubmit={e => { e.preventDefault(); if (question.trim() && !state.busy && state.historyReady) { mentra.send("chat_send", { text: question.trim() }); setQuestion(""); } }}>
            <label htmlFor="coach-message">Message the coach</label><textarea id="coach-message" maxLength={2000} rows={4} value={question} onChange={e => setQuestion(e.target.value)} />
            <div className="actions"><button type="submit" disabled={state.busy || !state.historyReady || !question.trim()}>Send message</button><button type="button" disabled={state.busy} onClick={() => mentra.send("clear_chat", {})}>Clear conversation</button></div>
          </form>
        </section>
      </>}
    </>}

    {page === "settings" && <>
      <section className="panel"><h2>Audio</h2>
        <label htmlFor="volume">Speech volume · {Math.round(volume*100)}%</label><input id="volume" type="range" min="0" max="1" step="0.05" value={volume} onChange={e => setVolume(Number(e.target.value))} />
        <p className="muted">Save to apply. Phone media volume and Bluetooth output also affect what you hear. Select your glasses as the media output.</p>
        <p className="muted" role="status">{state.speechMessage || "Routine progress and coaching are read aloud."}</p>
        <div className="actions"><button onClick={() => mentra.send("test_voice", {})}>Test voice</button>{stopSpeech}</div>
      </section>
      <section className="panel"><h2>Server & capture</h2>
        <label htmlFor="server">Mac extraction server</label><input id="server" value={server} onChange={e => setServer(e.target.value)} placeholder="http://192.168.1.42:8000" autoCapitalize="none" autoCorrect="off" />
        <label htmlFor="size">Photo resolution</label><select id="size" value={size} onChange={e => setSize(e.target.value as "medium" | "high")}><option value="medium">Medium — smaller transfer</option><option value="high">High — better for small text</option></select>
        <label htmlFor="transfer">Photo transfer</label><select id="transfer" value={transfer} onChange={e => setTransfer(e.target.value as "auto" | "ble")}><option value="auto">Automatic</option><option value="ble">Bluetooth through phone</option></select>
        <div className="actions"><button className="primary" disabled={state.busy} onClick={() => mentra.send("save_settings", { server, captureSize: size, transferMethod: transfer, volume })}>Save settings</button></div>
      </section>
      <section className="panel"><h2>Warnings</h2>
        {!state.historyReady && <p className="warning">Saved history is loading or unavailable. Session editing is disabled until it loads.</p>}
        {state.lastCoaching?.fallback_reason && <p className="warning">{state.lastCoaching.fallback_reason}</p>}
        {(result?.warnings || []).map((warning,i) => <p className="warning" key={i}>{warning}</p>)}
        {!result?.warnings?.length && !state.lastCoaching?.fallback_reason && state.historyReady && <p className="muted">No additional warnings.</p>}
      </section>
      <section className="panel"><h2>Session storage</h2><p className="muted">Saved sessions and reports stay in this miniapp on your phone.</p>
        <button disabled={state.busy || !state.historyReady || (!state.history.currentSession.length && !result)} onClick={() => setConfirmDiscard(true)}>Discard current session</button>
        {confirmDiscard && <div className="notice"><p>Discard the current session and close the open result? Saved reports are retained. The coach conversation resets.</p><button disabled={state.busy} onClick={() => { mentra.send("discard_session", {}); setConfirmDiscard(false); }}>Confirm discard</button>{" "}<button onClick={() => setConfirmDiscard(false)}>Cancel</button></div>}
        {state.history.reports.length > 0 && <><h2 style={{marginTop:24}}>Delete reports by date</h2>
          <label htmlFor="delete-from">From date</label><input id="delete-from" type="date" value={deleteFrom} onChange={e => { setDeleteFrom(e.target.value); setConfirmDelete(false); }} />
          <label htmlFor="delete-to">To date</label><input id="delete-to" type="date" value={deleteTo} onChange={e => { setDeleteTo(e.target.value); setConfirmDelete(false); }} />
          <div className="actions"><button disabled={state.busy || !state.historyReady || !deleteFrom || !deleteTo || deleteFrom > deleteTo} onClick={() => setConfirmDelete(true)}>Delete reports in range</button></div>
          {confirmDelete && <div className="notice"><p>Delete reports from {deleteFrom} through {deleteTo}? The coach conversation will also reset.</p><button disabled={state.busy} onClick={() => {
            const from = new Date(deleteFrom+"T00:00:00").getTime(); const end = new Date(deleteTo+"T00:00:00"); end.setDate(end.getDate()+1);
            mentra.send("delete_reports", { from, to: end.getTime()-1 }); setConfirmDelete(false);
          }}>Confirm report deletion</button>{" "}<button onClick={() => setConfirmDelete(false)}>Cancel</button></div>}
        </>}
      </section>
      <details className="panel"><summary>Debug</summary>
        <p className="muted">Combined coach v15</p>
        <h2 style={{marginTop:20}}>Samples</h2><p className="muted">Testing only. These load sample files from your Mac without taking a photo.</p>
        <div className="actions"><button disabled={state.busy} onClick={() => { mentra.send("demo", {}); setPage("song"); }}>Try Etterna sample</button><button disabled={state.busy} onClick={() => { mentra.send("game_demo", {}); setPage("song"); }}>Try game sample</button></div>
        <h2>Service checks</h2><div className="actions"><button disabled={state.busy} onClick={() => mentra.send("test_server", {})}>Test saved server</button><button disabled={state.busy} onClick={() => mentra.send("test_coach", {})}>Test coach service</button></div>
        <p className="muted">Save settings before testing. The coach test checks the local Etterna/report/chat adapter.</p>
        <h2>Latest status</h2><p className="status" role="status">{state.message}</p>
        {result?.session_diagnostic && <><h2>Session API diagnostic</h2><p>HTTP {result.session_diagnostic.http_status ?? "unavailable"} · {result.session_diagnostic.backend_error_code || "no error code"}</p><p className="muted">Stage: {result.session_diagnostic.stage || "unknown"}<br/>API: {result.session_diagnostic.api_origin}<br/>Session fingerprint: {result.session_diagnostic.session_fingerprint}</p></>}
        {result && <details><summary>OCR and extraction evidence</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>}
      </details>
    </>}
  </main><nav className="app-nav" aria-label="Main pages">{(["glasses", "song", "chat", "settings"] as const).map(tab => <button key={tab} aria-current={page === tab ? "page" : undefined} onClick={() => setPage(tab)}>{({glasses: "Glasses", song: "Song", chat: "Chat", settings: "Settings"})[tab]}</button>)}</nav></div>;
}
