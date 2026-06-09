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
  /** Tool name from the program_identification field of the IDBLOCK (bytes 16–23). */
  program_id: string;
  /** True when the on-disk file_identification bytes are "MDF     " (finalized).
   *  null for non-MDF source files (BLF, …) where the concept does not apply. */
  is_finalized: boolean | null;
  /** Raw unfinalized_standard_flags from the IDBLOCK (0 when finalized). */
  unfinalized_flags: number;
  /** True when all data groups have record_id_len == 0 (sorted/non-interleaved).
   *  null for non-MDF source files (BLF, …) where the concept does not apply. */
  is_sorted: boolean | null;
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
  cycles_nr: number;    // CG block cycle count — 0 means the group has no records on disk
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

export type ExportFormat = "tdms" | "mat" | "parquet" | "csv" | "tsv" | "xlsx" | "mf4";
export type SplitMode   = "none" | "time" | "size";

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

// ── App configuration (save / load) ───────────────────────────────────────── //

/**
 * Persisted application configuration.
 *
 * A config file captures the current export pipeline settings so that the same
 * pipeline can be applied to a different (but structurally similar) file later.
 *
 * Decoding entries use `group_name` as the primary key when re-applying to a
 * new file, falling back to `group_index` when the name is not found.
 * `channel_filter` stores bare signal names; when re-applied they are matched
 * by name across all groups in the new file.
 */
export interface AppConfig {
  /** Schema version — currently always 1. */
  version: 1;
  decoding: Array<{
    /** Channel group index in the file this config was saved from. */
    group_index: number;
    /** Acquisition name of the group — used for matching when the file changes. */
    group_name: string;
    /** Absolute path to the .dbc or .arxml database. */
    db_path: string;
  }>;
  /** Signal names to include in the export; null = no filter (export all). */
  channel_filter: string[] | null;
  flatten: boolean;
  export_format: ExportFormat;
  /** Last directory used for export; empty string = none saved. */
  output_folder: string;
  mat_link_groups: boolean;
  /** Output splitting settings (optional — omitted when mode is "none"). */
  split_mode?: SplitMode;
  split_size_mb?: number;
  split_period_s?: number;
  /** ISO 8601 datetime of the first split boundary; empty = start from file begin. */
  split_first_time?: string;
}

// ── Phase B: channel filter ────────────────────────────────────────────────── //

export type SignalSource = "physical" | "decoded";

/**
 * A channel selection entry used to persist the filter state in the UI.
 * The extra fields (acq_name, unit, source) are for display; the backend
 * only reads group_index and channel_name.
 */
export interface FilteredChannel {
  group_index: number;
  channel_name: string;
  acq_name: string;
  unit: string;
  source: SignalSource;
}

export interface ExportableChannel {
  name: string;
  unit: string;
}

export interface ExportableGroup {
  group_index: number;
  acq_name: string;
  source: SignalSource;
  channels: ExportableChannel[];
}

export interface ExportableSignals {
  groups: ExportableGroup[];
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
  format: ExportFormat,
  outputPath: string,
  dbAssignments?: DbAssignment[],
  flatten?: boolean,
  matLinkGroups?: boolean,
  signalFilter?: FilteredChannel[] | null,
  splitMode?: SplitMode,
  splitSizeMB?: number,
  splitPeriodS?: number,
  splitFirstOffsetS?: number,
): Promise<{ job_id: string }> {
  return invoke<{ job_id: string }>("start_export", {
    sessionId,
    format,
    outputPath,
    dbAssignments: dbAssignments && dbAssignments.length > 0 ? dbAssignments : null,
    flatten: flatten ?? false,
    matLinkGroups: matLinkGroups ?? false,
    // Send only the minimal (group_index, channel_name) fields; backend ignores extras
    signalFilter: signalFilter && signalFilter.length > 0 ? signalFilter : null,
    splitMode:          splitMode          ?? "none",
    splitSizeMb:        splitSizeMB        ?? 100,
    splitPeriodS:       splitPeriodS       ?? 60,
    splitFirstOffsetS:  splitFirstOffsetS  ?? 0,
  });
}

export async function getExportableSignals(
  sessionId: string,
  dbAssignments?: DbAssignment[] | null,
): Promise<ExportableSignals> {
  return invoke<ExportableSignals>("get_exportable_signals", {
    sessionId,
    dbAssignments: dbAssignments && dbAssignments.length > 0 ? dbAssignments : null,
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

/** How DBC / ARXML file paths are stored in a saved config. */
export type DbcPathMode = "absolute" | "relative" | "copy";

export async function saveConfig(
  path: string,
  config: AppConfig,
  dbcPathMode: DbcPathMode = "relative",
): Promise<void> {
  await invoke("save_config", { path, config, dbcPathMode });
}

export async function loadConfig(path: string): Promise<AppConfig> {
  const r = await invoke<{ config: AppConfig }>("load_config", { path });
  return r.config;
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
      hour12: false,
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
