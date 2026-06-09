/**
 * App-wide preferences — persisted in localStorage.
 *
 * Extend AppPrefs with new keys as features require them; PREF_DEFAULTS
 * ensures existing stored data is merged safely with any new defaults.
 */

const STORAGE_KEY = "mf4u_prefs";

/** How (if at all) the export output should be split into multiple files. */
export type SplitMode = "none" | "time" | "size";

export interface AppPrefs {
  /** When true, MAT export suffixes each channel name with its time-vector
   *  label (e.g. EngineSpeed_t1) so the channel→time association is
   *  explicit when the file is opened in MATLAB. */
  matLinkGroups: boolean;

  /** "none" = one file; "time" = fixed time windows; "size" = target file size. */
  splitMode: SplitMode;
  /** Target file size in MB (size mode). */
  splitSizeMB: number;
  /** Window length in seconds (time mode). */
  splitPeriodS: number;
  /**
   * Absolute date-time of the first split boundary (ISO 8601 string, time mode).
   * Empty string = no explicit first-split — splits begin at the file's first
   * sample and repeat every splitPeriodS seconds.
   * The frontend converts this to a seconds-offset relative to the file's own
   * start_time before sending it to the sidecar.
   */
  splitFirstTime: string;
}

export const PREF_DEFAULTS: AppPrefs = {
  matLinkGroups:    true,
  splitMode:        "none",
  splitSizeMB:      100,
  splitPeriodS:  60,
  splitFirstTime: "",
};

export function loadPrefs(): AppPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...PREF_DEFAULTS };
    return { ...PREF_DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return { ...PREF_DEFAULTS };
  }
}

export function savePrefs(prefs: AppPrefs): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // localStorage may be unavailable in some Tauri configurations
  }
}
