/**
 * App-wide preferences — persisted in localStorage.
 *
 * Extend AppPrefs with new keys as features require them; PREF_DEFAULTS
 * ensures existing stored data is merged safely with any new defaults.
 */

const STORAGE_KEY = "mf4u_prefs";

export interface AppPrefs {
  /** When true, MAT export suffixes each channel name with its time-vector
   *  label (e.g. EngineSpeed_t1) so the channel→time association is
   *  explicit when the file is opened in MATLAB. */
  matLinkGroups: boolean;
}

export const PREF_DEFAULTS: AppPrefs = {
  matLinkGroups: false,
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
