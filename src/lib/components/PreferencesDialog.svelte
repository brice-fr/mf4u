<script lang="ts">
  import type { AppPrefs, SplitMode } from "$lib/prefs";
  import { savePrefs } from "$lib/prefs";

  let {
    prefs,
    onchange,
    onclose,
    /** ISO string of the open file's first sample — used to bound the first-split picker. */
    fileStartTime = null as string | null,
    /** ISO string of the open file's last sample — used to bound the first-split picker. */
    fileEndTime   = null as string | null,
  }: {
    prefs:          AppPrefs;
    onchange:       (p: AppPrefs) => void;
    onclose:        () => void;
    fileStartTime?: string | null;
    fileEndTime?:   string | null;
  } = $props();

  // ── Period: HH MM SS derived fields ──────────────────────────────────────── //
  const ph = $derived(Math.floor(prefs.splitPeriodS / 3600));
  const pm = $derived(Math.floor((prefs.splitPeriodS % 3600) / 60));
  const ps = $derived(Math.floor(prefs.splitPeriodS % 60));

  // ── First-split: date + H/M/S derived fields ──────────────────────────────── //
  /** Shared zero-pad helper. */
  const pad2 = (n: number) => String(n).padStart(2, "0");

  /** ISO → "YYYY-MM-DD" in local time (for the date input's value/min/max). */
  function toDateStr(iso: string | null | undefined): string {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  // Date bounds for the date picker
  const dtMinDate = $derived(toDateStr(fileStartTime));
  const dtMaxDate = $derived(toDateStr(fileEndTime));

  // Current first-split value broken into parts
  const sfDate = $derived(toDateStr(prefs.splitFirstTime));
  const sfH    = $derived(prefs.splitFirstTime ? new Date(prefs.splitFirstTime).getHours()   : 0);
  const sfM    = $derived(prefs.splitFirstTime ? new Date(prefs.splitFirstTime).getMinutes() : 0);
  const sfS    = $derived(prefs.splitFirstTime ? new Date(prefs.splitFirstTime).getSeconds() : 0);

  // ── Update helpers ────────────────────────────────────────────────────────── //
  function toggle(key: keyof AppPrefs) {
    const updated = { ...prefs, [key]: !prefs[key] };
    savePrefs(updated);
    onchange(updated);
  }

  function setSplitMode(mode: SplitMode) {
    const updated = { ...prefs, splitMode: mode };
    savePrefs(updated);
    onchange(updated);
  }

  /** Commit a first-split time from its component parts. */
  function commitFirstSplit(datePart: string, h: number, m: number, s: number) {
    if (!datePart) { clearSplitFirstTime(); return; }
    // Build a local-time string → Date → ISO so the stored value is always UTC.
    const iso = new Date(`${datePart}T${pad2(h)}:${pad2(m)}:${pad2(s)}`).toISOString();
    const updated = { ...prefs, splitFirstTime: iso };
    savePrefs(updated);
    onchange(updated);
  }

  function setFirstSplitDate(dateStr: string) {
    commitFirstSplit(dateStr, sfH, sfM, sfS);
  }

  function setFirstSplitTimeField(field: "h" | "m" | "s", raw: string) {
    if (!sfDate) return;
    const v = Math.max(0, parseInt(raw, 10) || 0);
    commitFirstSplit(
      sfDate,
      field === "h" ? Math.min(23, v) : sfH,
      field === "m" ? Math.min(59, v) : sfM,
      field === "s" ? Math.min(59, v) : sfS,
    );
  }

  /** Update the split period from three numeric H/M/S inputs. */
  function setPeriod(h: number, m: number, s: number) {
    const total = Math.max(1, (h | 0) * 3600 + (m | 0) * 60 + (s | 0));
    const updated = { ...prefs, splitPeriodS: total };
    savePrefs(updated);
    onchange(updated);
  }

  /** Update one H, M, or S period field while keeping the others constant. */
  function setPeriodField(field: "h" | "m" | "s", raw: string) {
    const v = Math.max(0, parseInt(raw, 10) || 0);
    setPeriod(
      field === "h" ? v : ph,
      field === "m" ? v : pm,
      field === "s" ? v : ps,
    );
  }

  function setNum(key: "splitSizeMB", raw: string) {
    const v = parseFloat(raw);
    if (!isFinite(v) || v <= 0) return;
    const updated = { ...prefs, [key]: v };
    savePrefs(updated);
    onchange(updated);
  }

  /** Format an ISO timestamp as a 24-hour local datetime for the bounds hint. */
  function fmtDt(iso: string | null | undefined): string {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString(undefined, {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false,
      });
    } catch { return iso ?? ""; }
  }

  function clearSplitFirstTime() {
    const updated = { ...prefs, splitFirstTime: "" };
    savePrefs(updated);
    onchange(updated);
  }
</script>

<!-- backdrop -->
<div
  class="overlay"
  onclick={onclose}
  onkeydown={(e) => e.key === "Escape" && onclose()}
  role="presentation"
  tabindex="-1"
>
  <!-- dialog -->
  <div
    class="dialog"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
    role="dialog"
    aria-modal="true"
    aria-label="Preferences"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">Preferences</span>
      <button class="close-x" onclick={onclose} aria-label="Close">✕</button>
    </header>

    <!-- ── MATLAB Export ── -->
    <section class="pref-section">
      <span class="section-label">MATLAB Export</span>

      <label class="check-row" for="pref-mat-link-groups">
        <input
          id="pref-mat-link-groups"
          type="checkbox"
          class="sr-only"
          checked={prefs.matLinkGroups}
          onchange={() => toggle("matLinkGroups")}
        />
        <span class="check-box" class:checked={prefs.matLinkGroups} aria-hidden="true">
          {#if prefs.matLinkGroups}✓{/if}
        </span>
        <span class="check-body">
          <span class="check-title">Link channels to their time vectors</span>
          <span class="check-desc">
            Timestamps are exported as <code>t1</code>, <code>t2</code>, … (one per
            channel group). When this option is on, each data vector is also suffixed
            with the matching label — e.g. <code>EngineSpeed_t1</code> — making it
            immediately clear which time axis to use in MATLAB.
          </span>
        </span>
      </label>
    </section>

    <!-- ── Output Splitting ── -->
    <section class="pref-section">
      <span class="section-label">Output Splitting</span>

      {#snippet splitOption(value: SplitMode, label: string, desc: string)}
        <label class="split-card" class:selected={prefs.splitMode === value}>
          <input
            type="radio"
            class="sr-only"
            name="split-mode"
            {value}
            checked={prefs.splitMode === value}
            onchange={() => setSplitMode(value)}
          />
          <span class="radio-dot" aria-hidden="true">
            {#if prefs.splitMode === value}<span class="dot-inner"></span>{/if}
          </span>
          <span class="split-body">
            <span class="split-label">{label}</span>
            <span class="split-desc">{desc}</span>

            {#if prefs.splitMode === value && value === "time"}
              <span class="split-inputs">

                <!-- Period as H / M / S -->
                <span class="num-field">
                  <span class="num-label">Period</span>
                  <span class="hms-row">
                    <input
                      class="num-input hms"
                      type="number" min="0" step="1"
                      value={ph}
                      oninput={(e) => setPeriodField("h", (e.target as HTMLInputElement).value)}
                      aria-label="Hours"
                    />
                    <span class="num-unit">h</span>
                    <input
                      class="num-input hms"
                      type="number" min="0" max="59" step="1"
                      value={pm}
                      oninput={(e) => setPeriodField("m", (e.target as HTMLInputElement).value)}
                      aria-label="Minutes"
                    />
                    <span class="num-unit">m</span>
                    <input
                      class="num-input hms"
                      type="number" min="0" max="59" step="1"
                      value={ps}
                      oninput={(e) => setPeriodField("s", (e.target as HTMLInputElement).value)}
                      aria-label="Seconds"
                    />
                    <span class="num-unit">s</span>
                  </span>
                </span>

                <!-- First split at — date picker + 24 h time fields -->
                <span class="num-field dt-field">
                  <span class="num-label">
                    First split at
                    {#if !fileStartTime}
                      <span class="dt-hint">(open a file to validate bounds)</span>
                    {:else}
                      <span class="dt-hint">
                        {fmtDt(fileStartTime)} – {fmtDt(fileEndTime)}
                      </span>
                    {/if}
                  </span>
                  <span class="dt-row">
                    <!-- Date part -->
                    <input
                      class="dt-date-input"
                      type="date"
                      value={sfDate}
                      min={dtMinDate}
                      max={dtMaxDate}
                      oninput={(e) => setFirstSplitDate((e.target as HTMLInputElement).value)}
                    />
                    <!-- Time part: HH : MM : SS (always 24 h) -->
                    <span class="hms-row">
                      <input
                        class="num-input hms"
                        type="number" min="0" max="23" step="1"
                        value={sfH}
                        disabled={!sfDate}
                        oninput={(e) => setFirstSplitTimeField("h", (e.target as HTMLInputElement).value)}
                        aria-label="Hour"
                      />
                      <span class="num-unit colon">:</span>
                      <input
                        class="num-input hms"
                        type="number" min="0" max="59" step="1"
                        value={sfM}
                        disabled={!sfDate}
                        oninput={(e) => setFirstSplitTimeField("m", (e.target as HTMLInputElement).value)}
                        aria-label="Minute"
                      />
                      <span class="num-unit colon">:</span>
                      <input
                        class="num-input hms"
                        type="number" min="0" max="59" step="1"
                        value={sfS}
                        disabled={!sfDate}
                        oninput={(e) => setFirstSplitTimeField("s", (e.target as HTMLInputElement).value)}
                        aria-label="Second"
                      />
                    </span>
                    {#if prefs.splitFirstTime}
                      <button class="dt-clear" onclick={clearSplitFirstTime} title="Clear — split from file start">✕</button>
                    {/if}
                  </span>
                  {#if !prefs.splitFirstTime}
                    <span class="dt-empty-hint">Not set — splits start at the file's first sample.</span>
                  {/if}
                </span>

              </span>
            {/if}

            {#if prefs.splitMode === value && value === "size"}
              <span class="split-inputs">
                <label class="num-field">
                  <span class="num-label">Max file size</span>
                  <span class="num-row">
                    <input
                      class="num-input"
                      type="number"
                      min="1"
                      step="1"
                      value={prefs.splitSizeMB}
                      oninput={(e) => setNum("splitSizeMB", (e.target as HTMLInputElement).value)}
                    />
                    <span class="num-unit">MB</span>
                  </span>
                </label>
              </span>
            {/if}
          </span>
        </label>
      {/snippet}

      <div class="split-options">
        {@render splitOption("none", "No splitting", "Export each file as a single output file.")}
        {@render splitOption("time", "By time", "Split at fixed time intervals. Each chunk is named with its absolute start time (e.g. recording_240315_102445.mat).")}
        {@render splitOption("size", "By size", "Target a maximum file size. The period is estimated from the source file density. Chunks are named with their absolute start time.")}
      </div>
    </section>

    <!-- ── actions ── -->
    <div class="actions">
      <button class="btn-primary" onclick={onclose}>Close</button>
    </div>
  </div>
</div>

<style>
  /* ── overlay ── */
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  /* ── dialog box ── */
  .dialog {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 10px;
    width: min(460px, 94vw);
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1.1rem 1.2rem 1rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  /* ── header ── */
  .dlg-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .dlg-title {
    font-size: 0.9rem;
    font-weight: 600;
    color: #e8e8e8;
  }

  .close-x {
    background: none;
    border: none;
    color: #666;
    font-size: 0.85rem;
    cursor: pointer;
    padding: 0.1em 0.3em;
    line-height: 1;
  }
  .close-x:hover { color: #ccc; }

  /* ── preference section ── */
  .pref-section {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }

  .section-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #555;
  }

  /* Screen-reader only — visually hidden but accessible */
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  /* ── checkbox row ── */
  .check-row {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    cursor: pointer;
    user-select: none;
    padding: 0.5rem 0.6rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    background: #181818;
    transition: border-color 0.12s, background 0.12s;
  }
  .check-row:hover { border-color: #3a3a3a; background: #1e1e1e; }

  .check-box {
    flex-shrink: 0;
    width: 15px;
    height: 15px;
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    background: #141414;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    color: #fff;
    margin-top: 1px;
    transition: background 0.12s, border-color 0.12s;
  }
  .check-box.checked {
    background: #6c9ef8;
    border-color: #6c9ef8;
  }

  .check-body {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .check-title {
    font-size: 0.82rem;
    color: #ddd;
    line-height: 1.3;
  }

  .check-desc {
    font-size: 0.72rem;
    color: #666;
    line-height: 1.5;
  }

  .check-desc code {
    font-family: ui-monospace, monospace;
    font-size: 0.68rem;
    color: #888;
    background: #252525;
    padding: 0.05em 0.3em;
    border-radius: 3px;
  }

  /* ── split option cards ── */
  .split-options {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .split-card {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    cursor: pointer;
    user-select: none;
    padding: 0.55rem 0.7rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    background: #181818;
    transition: border-color 0.12s, background 0.12s;
  }
  .split-card:hover          { border-color: #3a3a3a; background: #1e1e1e; }
  .split-card.selected       { border-color: #6c9ef8; background: rgba(108,158,248,0.06); }

  .radio-dot {
    flex-shrink: 0;
    width: 14px;
    height: 14px;
    border: 1px solid #3a3a3a;
    border-radius: 50%;
    background: #141414;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 2px;
    transition: border-color 0.12s;
  }
  .split-card.selected .radio-dot { border-color: #6c9ef8; }

  .dot-inner {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #6c9ef8;
  }

  .split-body {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    flex: 1;
  }

  .split-label {
    font-size: 0.82rem;
    color: #ddd;
    line-height: 1.3;
  }
  .split-card.selected .split-label { color: #e8e8e8; }

  .split-desc {
    font-size: 0.71rem;
    color: #666;
    line-height: 1.5;
  }

  /* ── number inputs inside the selected card ── */
  .split-inputs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 0.5rem;
  }

  .num-field {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    cursor: default;
  }

  .num-label {
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #555;
  }

  .num-row, .hms-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .num-input {
    width: 72px;
    background: #141414;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    color: #ddd;
    font-size: 0.82rem;
    padding: 0.25em 0.5em;
    text-align: right;
    -moz-appearance: textfield;
    appearance: textfield;
  }
  .num-input.hms { width: 46px; }
  .num-input::-webkit-inner-spin-button,
  .num-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .num-input:focus {
    outline: none;
    border-color: #6c9ef8;
  }

  .num-unit {
    font-size: 0.72rem;
    color: #555;
    white-space: nowrap;
  }

  /* ── first-split date/time field ── */
  .dt-field { flex: 1 1 100%; }   /* always full width inside split-inputs */

  .dt-hint {
    font-size: 0.65rem;
    color: #444;
    letter-spacing: 0;
    text-transform: none;
    font-weight: 400;
    margin-left: 0.4em;
  }

  .dt-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .dt-date-input {
    background: #141414;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    color: #ddd;
    font-size: 0.82rem;
    padding: 0.25em 0.5em;
    font-family: inherit;
    color-scheme: dark;
  }
  .dt-date-input:focus {
    outline: none;
    border-color: #6c9ef8;
  }

  /* Colon separator between H : M : S in the time part */
  .num-unit.colon {
    padding: 0 0.05rem;
    font-weight: 600;
    color: #444;
  }

  .dt-clear {
    flex-shrink: 0;
    background: none;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    color: #666;
    font-size: 0.72rem;
    cursor: pointer;
    padding: 0.2em 0.45em;
    line-height: 1;
    transition: border-color 0.12s, color 0.12s;
  }
  .dt-clear:hover { border-color: #666; color: #ccc; }

  .dt-empty-hint {
    font-size: 0.68rem;
    color: #444;
    font-style: italic;
    margin-top: 0.2rem;
  }

  /* ── actions ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    padding-top: 0.1rem;
  }

  .btn-primary {
    padding: 0.35em 1.1em;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
    background: #6c9ef8;
    border: 1px solid #6c9ef8;
    color: #fff;
    font-weight: 500;
    transition: background 0.12s, border-color 0.12s;
  }
  .btn-primary:hover { background: #81aaff; border-color: #81aaff; }
</style>
