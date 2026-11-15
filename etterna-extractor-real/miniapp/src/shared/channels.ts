import type { MentraTyped, Rpc } from "@mentra/miniapp/ui";

export interface Field<T = number | string | { first: number; second: number }> {
  value: T | null;
  raw: string | null;
  ocr_confidence: number | null;
}
export interface ExtractionData {
  accuracy_percent: Field<number>;
  accuracy_label: Field<string>;
  grade?: Field<string>;
  wife_version?: Field<number>;
  judge_setting: Field<number>;
  playback_rate: Field<number>;
  judgments: Record<string, Field<number>>;
  timing: Record<string, Field<number>>;
  auxiliary_counts: Record<string, Field<{ first: number; second: number }>>;
  ratios_and_streaks?: Record<string, Field>;
  song_text: string;
  unlabeled_ratings_text: string[];
}
export interface ExtractionResult {
  job_id: string;
  status: string;
  layout?: string;
  alignment?: string;
  alignment_details?: { matching_mode?: string; inliers?: number; visible_game_fraction?: number } | null;
  source?: string;
  warnings?: string[];
  data?: ExtractionData;
  crops?: Record<string, string>;
  qr_payload?: string;
  qr_decoder?: string;
  session_access_revoked?: boolean;
  session_diagnostic?: { api_origin: string; session_fingerprint: string; http_status: number | null;
    backend_error_code: string | null; stage: string | null; retry_after_seconds?: number | null };
  csv?: { columns: string[]; rows: Record<string, string>[] } | null;
  game_run?: GameRunResult;
  remote_session?: { handle: string; run_count: number; selected_run_id?: string;
    runs: Array<{ run_id: string; sequence: number; song_id: number; game_id: number; autoplay: boolean }> };
}
export interface GameRunResult {
  run_id: string;
  created_at: string;
  run: {
    format_version?: number;
    nominal_bpm?: number | null;
    notes?: Array<{ note_index: number; time_ms: number; lane: number; judgement: "P" | "G" | "M";
      accuracy_delta: number | null; latency_ms: number | null; nps: number; bpm: number; combo: number; std_ms: number | null }>;
    summary: { game_id: number; song_id: number; difficulty: number; game_time_ms: number;
      bpm: number; total_notes: number; score: number; average_latency_ms: number };
    chart_id: number | null;
    envelope?: { autoplay: boolean; summary_exceeds_format_range: boolean; successful_hit_count: number };
    sample_interval_sec?: number | null;
    timeline_available: boolean;
    samples: Array<{ time_sec: number; accuracy: number | null; avg_latency_ms: number | null;
      bpm: number | null; nps: number; latency_spread_ms: number | null }>;
    warnings: string[];
  };
  analysis: {
    score: number; accuracy: number | null; grade: string | null; mean_offset_ms: number | null;
    sections: Array<{ start_ms: number; end_ms: number; accuracy: number | null;
      mean_offset_ms: number | null; spread_ms: number | null; judged_notes?: number; misses?: number; perfect?: number; good?: number; hit_rate?: number; measured_offsets?: number }>;
    tips: Array<{ time_ms: number; spans_song: boolean; text: string }>;
    spoken_summary: string;
    method: string;
    accuracy_is_approximate?: boolean;
    accuracy_coverage_uncertain?: boolean;
    accuracy_basis?: string;
    spread_ms?: number | null;
    judgments?: Record<string, number>;
  };
}
export interface AppState {
  message: string;
  messageKind?: "info" | "error";
  volume?: number;
  busy: boolean;
  jobId: string;
  revision: number;
  result: ExtractionResult | null;
  server: string;
  captureSize: "medium" | "high";
  transferMethod: "auto" | "ble";
  history: HistoryState;
  historyReady: boolean;
  speechMessage?: string;
  chat: ChatMessage[];
  lastCoaching: CoachingReply | null;
}
export interface OcrReview { reviewed: boolean; accuracy_pct?: number | null; mean_offset_ms?: number | null; native_grade?: string | null }
export interface SongSummary {
  id: string; source: "custom_game_csv" | "screen_ocr"; scoring_system: string; title: string; played_at: number;
  game_id: number | null; song_id: number | null; chart_id: number | null; difficulty: number | null;
  game_time_ms: number | null; bpm: number | null; total_notes: number | null; score: number | null; score_max: number | null;
  accuracy_is_approximate?: boolean; accuracy_coverage_uncertain?: boolean; peak_nps?: number | null;
  native_grade: string | null; accuracy_pct: number | null; mean_offset_ms: number | null; offset_spread_ms: number | null;
  weakest_section: { start_s: number; end_s: number; accuracy_pct: number } | null;
  tips: string[]; data_notes: string[]; reviewed: boolean; usable_for_coaching: boolean;
}
export interface SessionReport {
  ai_debrief?: string;
  coaching?: CoachingReply;
  scope?: "server_session";
  id: string; created_at: number; songs: SongSummary[];
  groups: Array<{ scoring_system: string; song_count: number; verified_song_count: number;
    average_accuracy_pct: number | null; average_offset_ms: number | null;
    first_to_last_change_pct: number | null; best_song: string | null }>;
  highlights: string[]; text: string; spoken_summary: string;
}
export interface HistoryState { currentSession: SongSummary[]; reports: SessionReport[] }
export interface CoachingReply {
  session_access_revoked?: boolean;
  coaching_route?: "session_api";
  provider: "rhythm_backend" | "offline"; fallback_reason: string | null;
  coach: { mode: string; tier: string | null; speech: string; phone_text: string[]; coaching_focus: string;
    what_went_well?: string | null; observations?: Array<{ label: string; value: string; interpretation: string }>;
    drill: string | null; next_target: string | null; confidence: string; evidence_basis: string;
    data_notes: string[]; focus_section: { start_s: number; end_s: number; reason: string } | null };
}
export interface ChatMessage { role: "user" | "assistant"; text: string; reply?: CoachingReply }
export interface Channels {
  server_session_debrief: { handle: string };
  stop_speech: {};
  scan: {};
  demo: {};
  game_demo: {};
  load_game_run: { payload: string };
  refresh_game_session: { handle: string; runId?: string };
  add_to_session: { review: OcrReview };
  song_coaching: { review: OcrReview };
  generate_report: {};
  discard_session: {};
  finish_song: {};
  report_coaching: { reportId: string };
  delete_reports: { from: number; to: number };
  chat_send: { text: string };
  clear_chat: {};
  speak_text: { text: string };
  test_voice: {};
  get_state: {};
  refresh_result: {};
  realign_auto: {};
  correct_corners: { corners: number[][] };
  save_settings: { server: string; captureSize: "medium" | "high"; transferMethod: "auto" | "ble"; volume?: number };
  test_server: {};
  test_coach: {};
  status: AppState;
  get_image: Rpc<{ jobId: string; name: string }, { dataUrl: string }>;
}
declare global {
  var mentra: MentraTyped<Channels>;
}
