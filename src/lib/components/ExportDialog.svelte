<script lang="ts">
  import { save as saveDialog } from "@tauri-apps/plugin-dialog";
  import { startExport, getExportProgress, cancelExport } from "$lib/rpc";
  import type { ExportJob } from "$lib/rpc";

  let {
    sessionId,
    onclose,
  }: {
    sessionId: string;
    onclose: () => void;
  } = $props();

  type Fmt = "tdms" | "mat" | "parquet";
  let format: Fmt       = $state("tdms");
  let outputPath        = $state("");
  let jobId = $state(null as string | null);
  let job   = $state(null as ExportJob | null);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const FMT_META: Record<Fmt, { label: string; ext: string; hint?: string }> = {
    tdms:    { label: "NI TDMS (.tdms)",       ext: "tdms" },
    mat:     { label: "MATLAB (.mat)",          ext: "mat"  },
    parquet: { label: "Apache Parquet (.parquet)", ext: "parquet",
               hint: "One .parquet file per channel group when multiple groups are present." },
  };

  async function browse() {
    const { ext, label } = FMT_META[format];
    const path = await saveDialog({
      defaultPath: `export.${ext}`,
      filters: [{ name: label, extensions: [ext] }],
    });
    if (path) outputPath = path as string;
  }

  async function runExport() {
    if (!outputPath || jobId) return;
    try {
      const r = await startExport(sessionId, format, outputPath);
      jobId = r.job_id;
      job   = { status: "running", done: 0, total: 0, error: null };
      pollTimer = setInterval(poll, 400);
    } catch (e) {
      job = { status: "error", done: 0, total: 0, error: String(e) };
    }
  }

  async function poll() {
    if (!jobId) return;
    try {
      job = await getExportProgress(jobId);
      if (job.status !== "running") {
        clearInterval(pollTimer!);
        pollTimer = null;
      }
    } catch {
      // transient error — keep polling
    }
  }

  async function doCancel() {
    if (!jobId) return;
    clearInterval(pollTimer!);
    pollTimer = null;
    try {
      await cancelExport(jobId);
    } catch { /* ignore */ }
    if (job) job = { ...job, status: "cancelled" };
  }

  function close() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    onclose();
  }

  // When user switches format, clear any stale output path
  function switchFormat(f: Fmt) {
    format = f;
    outputPath = "";
    jobId = null;
    job   = null;
  }

  const pct        = $derived(job && job.total > 0 ? Math.round((job.done / job.total) * 100) : 0);
  const isRunning  = $derived(job?.status === "running");
  const isDone     = $derived(job?.status === "done");
  const isError    = $derived(job?.status === "error");
  const isCancelled = $derived(job?.status === "cancelled");
  const canExport  = $derived(!!outputPath && !jobId);
</script>

<!-- backdrop -->
<div
  class="overlay"
  onclick={close}
  onkeydown={(e) => e.key === "Escape" && close()}
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
    aria-label="Export"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">Export</span>
      <button class="close-x" onclick={close} aria-label="Close" disabled={isRunning}>✕</button>
    </header>

    <!-- ── format selector ── -->
    <div class="field">
      <span class="field-label">Format</span>
      <div class="radio-group">
        {#each (["tdms", "mat", "parquet"] as Fmt[]) as f}
          <label class="radio" class:active={format === f}>
            <input
              type="radio"
              name="fmt"
              value={f}
              checked={format === f}
              onchange={() => switchFormat(f)}
              disabled={isRunning}
            />
            {FMT_META[f].label}
          </label>
        {/each}
      </div>
    </div>

    <!-- ── output path ── -->
    <div class="field">
      <span class="field-label">Output file</span>
      <div class="path-row">
        <input
          class="path-input"
          type="text"
          readonly
          value={outputPath}
          placeholder="Click Browse… to choose"
          disabled={isRunning}
        />
        <button class="browse-btn" onclick={browse} disabled={isRunning}>Browse…</button>
      </div>
      {#if FMT_META[format].hint}
        <p class="field-hint">{FMT_META[format].hint}</p>
      {/if}
    </div>

    <!-- ── progress area ── -->
    {#if job}
      <div class="progress-area">
        {#if isRunning}
          <div class="progress-track">
            <div class="progress-fill" style:width="{pct}%"></div>
          </div>
          <span class="progress-text">
            {job.done} / {job.total} groups&nbsp;({pct}%)
          </span>
        {:else if isDone}
          <span class="status-ok">✓ Export complete</span>
        {:else if isError}
          <span class="status-err">✗ {job.error ?? "Unknown error"}</span>
        {:else if isCancelled}
          <span class="status-warn">Export cancelled</span>
        {/if}
      </div>
    {/if}

    <!-- ── action buttons ── -->
    <div class="actions">
      {#if isRunning}
        <button class="btn-danger" onclick={doCancel}>Cancel export</button>
      {:else if isDone}
        <button class="btn-primary" onclick={close}>Close</button>
      {:else}
        <button class="btn-ghost" onclick={close}>Close</button>
        <button class="btn-primary" onclick={runExport} disabled={!canExport}>
          Export
        </button>
      {/if}
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
    width: min(420px, 94vw);
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
  .close-x:hover:not(:disabled) { color: #ccc; }
  .close-x:disabled { opacity: 0.35; cursor: default; }

  /* ── fields ── */
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .field-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #666;
  }

  /* ── format radio group ── */
  .radio-group {
    display: flex;
    gap: 0.5rem;
  }

  .radio {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.82rem;
    color: #aaa;
    cursor: pointer;
    padding: 0.3em 0.65em;
    border: 1px solid #2e2e2e;
    border-radius: 5px;
    background: #181818;
    transition: border-color 0.12s;
    user-select: none;
  }
  .radio:has(input:checked),
  .radio.active {
    border-color: #6c9ef8;
    color: #e8e8e8;
    background: #161e2e;
  }
  .radio input { accent-color: #6c9ef8; }

  /* ── path row ── */
  .path-row {
    display: flex;
    gap: 0.5rem;
  }

  .path-input {
    flex: 1;
    min-width: 0;
    background: #161616;
    border: 1px solid #2e2e2e;
    border-radius: 5px;
    color: #bbb;
    font-size: 0.8rem;
    padding: 0.3em 0.6em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: default;
  }
  .path-input:disabled { opacity: 0.5; }

  .browse-btn {
    flex-shrink: 0;
    padding: 0.3em 0.75em;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    background: #252525;
    color: #ccc;
    font-size: 0.8rem;
    cursor: pointer;
    transition: border-color 0.12s;
  }
  .browse-btn:hover:not(:disabled) { border-color: #6c9ef8; }
  .browse-btn:disabled { opacity: 0.4; cursor: default; }

  .field-hint {
    margin: 0;
    font-size: 0.72rem;
    color: #555;
    line-height: 1.4;
  }

  /* ── progress area ── */
  .progress-area {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .progress-track {
    height: 4px;
    background: #2a2a2a;
    border-radius: 2px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: #6c9ef8;
    border-radius: 2px;
    transition: width 0.3s ease-out;
  }

  .progress-text { color: #888; font-size: 0.78rem; }
  .status-ok     { color: #4ec994; font-size: 0.82rem; font-weight: 500; }
  .status-err    { color: #eb5757; font-size: 0.8rem;  word-break: break-all; }
  .status-warn   { color: #c8832a; font-size: 0.82rem; }

  /* ── action buttons ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.1rem;
  }

  .btn-primary, .btn-ghost, .btn-danger {
    padding: 0.35em 1em;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
    transition: border-color 0.12s, background 0.12s;
  }

  .btn-primary {
    background: #6c9ef8;
    border: 1px solid #6c9ef8;
    color: #fff;
    font-weight: 500;
  }
  .btn-primary:hover:not(:disabled) { background: #81aaff; border-color: #81aaff; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }

  .btn-ghost {
    background: transparent;
    border: 1px solid #3a3a3a;
    color: #aaa;
  }
  .btn-ghost:hover { border-color: #666; color: #ccc; }

  .btn-danger {
    background: transparent;
    border: 1px solid #7a2222;
    color: #eb5757;
  }
  .btn-danger:hover { border-color: #eb5757; background: #1a0d0d; }
</style>
