import type { GameRunResult } from "./channels";

export function sectionJudgments(game: GameRunResult, start: number, end: number) {
  const notes = (game.run.notes || []).filter(n => n.time_ms >= start && n.time_ms < end);
  const perfect = notes.filter(n => n.judgement === "P").length;
  const good = notes.filter(n => n.judgement === "G").length;
  const misses = notes.filter(n => n.judgement === "M").length;
  return { judged: notes.length, perfect, good, misses, hitRate: notes.length ? (perfect + good) / notes.length : null };
}

// Display buckets, not the game's judgement windows. Include both tails.
export const OFFSET_BANDS = [
  { label: "≥ +150", min: 150, max: Infinity },
  { label: "+100 to +150", min: 100, max: 150 },
  { label: "+60 to +100", min: 60, max: 100 },
  { label: "+30 to +60", min: 30, max: 60 },
  { label: "+10 to +30", min: 10, max: 30 },
  { label: "−10 to +10", min: -10, max: 10 },
  { label: "−30 to −10", min: -30, max: -10 },
  { label: "−60 to −30", min: -60, max: -30 },
  { label: "−100 to −60", min: -100, max: -60 },
  { label: "−150 to −100", min: -150, max: -100 },
  { label: "< −150", min: -Infinity, max: -150 },
];
export interface LatencyColumn {
  startMs: number; endMs: number; counts: number[]; misses: number;
  measured: number; meanMs: number | null;
}
export function latencyHeatmap(game: GameRunResult) {
  const noteLevel = game.run.format_version === 2;
  const rows = noteLevel ? (game.run.notes || []).map(n => ({
    time: n.time_ms, offset: n.latency_ms, miss: n.judgement === "M", active: true,
  })) : game.run.samples.map(s => ({ time: s.time_sec * 1000, offset: s.avg_latency_ms, miss: false, active: s.nps > 0 }));
  const captured = rows.filter(r => r.active && Number.isFinite(r.time) && r.time >= 0);
  const points = captured.filter(r => !r.miss && typeof r.offset === "number" && Number.isFinite(r.offset));
  const missing = captured.filter(r => !r.miss && (r.offset === null || !Number.isFinite(r.offset))).length;
  const duration = Math.max(1, game.run.summary.game_time_ms, ...captured.map(r => r.time));
  // At most 80 columns; long songs use wider, whole-five-second windows.
  const windowMs = Math.max(5000, Math.ceil(duration / (80 * 5000)) * 5000);
  const columns: LatencyColumn[] = Array.from({ length: Math.ceil(duration / windowMs) }, (_, i) => ({
    startMs: i * windowMs, endMs: Math.min((i + 1) * windowMs, duration),
    counts: OFFSET_BANDS.map(() => 0), misses: 0, measured: 0, meanMs: null,
  }));
  for (const row of captured) {
    // The final window includes an event exactly on the duration boundary.
    const c = columns[Math.min(columns.length - 1, Math.floor(row.time / windowMs))];
    if (row.miss) c.misses++;
    else if (typeof row.offset === "number" && Number.isFinite(row.offset)) {
      const band = OFFSET_BANDS.findIndex(b => row.offset! >= b.min && row.offset! < b.max);
      if (band >= 0) c.counts[band]++;
      c.measured++;
      c.meanMs = (c.meanMs ?? 0) + (row.offset - (c.meanMs ?? 0)) / c.measured;
    }
  }
  return { noteLevel, columns, windowMs, measured: points.length, missing,
    misses: captured.filter(r => r.miss).length, maxCount: Math.max(1, ...columns.flatMap(c => c.counts)) };
}
