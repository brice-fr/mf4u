/**
 * Typed wrappers around Tauri commands.
 * All I/O goes through the Python sidecar via JSON-RPC over stdio.
 */
import { invoke } from "@tauri-apps/api/core";

// -------------------------------------------------------------------------- //
// Types
// -------------------------------------------------------------------------- //

export interface Metadata {
  file_name: string;
  file_size: number;
  version: string;
  start_time: string | null;
  end_time: string | null;
  duration_s: number | null;
  num_channel_groups: number;
  num_nonempty_channel_groups: number;
  num_channels: number;
  has_bus_frames: boolean;
  bus_types: string[];
  bus_frame_counts: Record<string, number>; // {type: channel-group count}
  comment: string;
  author: string;
  department: string;
  project: string;
  subject: string;
  dg_compression: string[];               // per-group: "uncompressed" | "zipped" | "transposed-zipped" | "unknown"
  attachments: string[];
}

export interface OpenFileResult {
  session_id: string;
  metadata: Metadata;
}

export interface ChannelInfo {
  name: string;
  unit: string;
  comment: string;
  is_phy: boolean;
}

export interface GroupInfo {
  index: number;
  acq_name: string;
  is_bus_raw: boolean;
  bus_type: string | null;
  has_phy: boolean;
  compression: string;  // "uncompressed" | "zipped" | "transposed-zipped" | "unknown"
  channels: ChannelInfo[];
}

export interface FileStructure {
  groups: GroupInfo[];
}

export interface ChannelStats {
  samples: number;
  min?: number;
  max?: number;
  mean?: number;
  first_t?: number;
  last_t?: number;
}

export type ExportStatus = "running" | "done" | "error" | "cancelled" | "not_found";

export interface ExportJob {
  status: ExportStatus;
  done: number;
  total: number;
  error: string | null;
}

// ── Phase A: bus frame decoding ────────────────────────────────────────────── //

/** One (group, db) assignment entry.  Order within the same group_index = priority. */
export interface DbAssignment {
  group_index: number;
  db_path: string;
}

export interface BusDecodingPreview {
  group_index: number;
  db_path: string;
  matched_messages: number;
  signal_count: number;
  error: string | null;
}

export interface PreviewBusDecodingResult {
  previews: BusDecodingPreview[];
}

// -------------------------------------------------------------------------- //
// API
// -------------------------------------------------------------------------- //

export async function openFile(path: string): Promise<OpenFileResult> {
  return invoke<OpenFileResult>("open_file", { path });
}

export async function getStructure(sessionId: string): Promise<FileStructure> {
  return invoke<FileStructure>("get_structure", { sessionId });
}

export async function getSignalStats(
  sessionId: string,
  groupIndex: number,
  channelName: string,
): Promise<ChannelStats> {
  return invoke<ChannelStats>("get_signal_stats", { sessionId, groupIndex, channelName });
}

export async function closeSession(sessionId: string): Promise<void> {
  await invoke("close_session", { sessionId });
}

export async function startExport(
  sessionId: string,
  format: "mat" | "tdms" | "parquet" | "csv" | "tsv" | "xlsx" | "mf4",
  outputPath: string,
  dbAssignments?: DbAssignment[],
  flatten?: boolean,
): Promise<{ job_id: string }> {
  return invoke<{ job_id: string }>("start_export", {
    sessionId,
    format,
    outputPath,
    dbAssignments: dbAssignments && dbAssignments.length > 0 ? dbAssignments : null,
    flatten: flatten ?? false,
  });
}

export async function previewBusDecoding(
  sessionId: string,
  dbAssignments: DbAssignment[],
): Promise<PreviewBusDecodingResult> {
  return invoke<PreviewBusDecodingResult>("preview_bus_decoding", {
    sessionId,
    dbAssignments,
  });
}

export async function getExportProgress(jobId: string): Promise<ExportJob> {
  return invoke<ExportJob>("get_export_progress", { jobId });
}

export async function cancelExport(jobId: string): Promise<void> {
  await invoke("cancel_export", { jobId });
}

// -------------------------------------------------------------------------- //
// Formatting helpers
// -------------------------------------------------------------------------- //

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const parts: string[] = [];
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  parts.push(`${s.toFixed(3)}s`);
  return parts.join(" ");
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      fractionalSecondDigits: 3,
    });
  } catch {
    return iso;
  }
}

export function formatNum(v: number | undefined, decimals = 4): string {
  if (v === undefined || v === null) return "—";
  if (!isFinite(v)) return String(v);
  // Use exponential notation for very large/small values
  if (Math.abs(v) > 1e6 || (Math.abs(v) < 1e-3 && v !== 0)) {
    return v.toExponential(3);
  }
  return v.toFixed(decimals).replace(/\.?0+$/, "");
}
