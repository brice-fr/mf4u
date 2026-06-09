<script lang="ts">
  import type { CopyConflict, CopyResolution } from "$lib/rpc";

  let {
    conflicts,
    onconfirm,
    oncancel,
  }: {
    /** The list of colliding DBC files, as returned by checkCopyConflicts. */
    conflicts: CopyConflict[];
    /** Called with the per-filename resolution map once the user confirms. */
    onconfirm: (resolutions: Record<string, CopyResolution>) => void;
    oncancel:  () => void;
  } = $props();

  // ── State ─────────────────────────────────────────────────────────────── //
  /** Index of the conflict currently shown. */
  let idx        = $state(0);
  /** Resolution chosen for the currently shown conflict. */
  let resolution = $state<CopyResolution>("skip");
  /** When true the current choice is applied to all remaining conflicts. */
  let applyToAll = $state(false);
  /** Resolutions accumulated for already-confirmed conflicts. */
  let confirmed  = $state<Record<string, CopyResolution>>({});

  const total     = $derived(conflicts.length);
  const current   = $derived(conflicts[idx]);
  const remaining = $derived(total - idx - 1);
  const isLast    = $derived(remaining === 0);

  // ── Actions ───────────────────────────────────────────────────────────── //
  function confirm() {
    const rec = { ...confirmed, [current.filename]: resolution };

    if (applyToAll || isLast) {
      // Apply the current choice to all remaining files and finish.
      const final = { ...rec };
      for (let i = idx + 1; i < conflicts.length; i++) {
        final[conflicts[i].filename] = resolution;
      }
      onconfirm(final);
    } else {
      // Record this file and advance to the next conflict.
      confirmed   = rec;
      idx        += 1;
      resolution  = "skip"; // sensible default for each new file
    }
  }
</script>

<!-- backdrop -->
<div
  class="overlay"
  onclick={oncancel}
  onkeydown={(e) => e.key === "Escape" && oncancel()}
  role="presentation"
  tabindex="-1"
>
  <!-- dialog -->
  <div
    class="dialog"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
    role="alertdialog"
    aria-modal="true"
    aria-label="DBC file conflict"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">DBC file already exists</span>
      {#if total > 1}
        <span class="dlg-counter">{idx + 1} / {total}</span>
      {/if}
      <button class="close-x" onclick={oncancel} aria-label="Cancel">✕</button>
    </header>

    <!-- conflict description -->
    <div class="conflict-info">
      <span class="conflict-name">{current.filename}</span>
      <span class="conflict-sub">already exists in the config folder.</span>
    </div>

    <!-- resolution options -->
    <div class="options">
      {#each ([
        { value: "overwrite", label: "Overwrite",
          desc:  "Replace the existing file with the current DBC." },
        { value: "skip",      label: "Skip",
          desc:  "Keep the existing file; the config will reference it as-is." },
      ] as const) as opt (opt.value)}
        <label class="option" class:selected={resolution === opt.value}>
          <input
            type="radio"
            class="sr-only"
            name="copy-resolution"
            value={opt.value}
            checked={resolution === opt.value}
            onchange={() => { resolution = opt.value; }}
          />
          <span class="radio-dot" aria-hidden="true">
            {#if resolution === opt.value}<span class="dot-inner"></span>{/if}
          </span>
          <span class="opt-body">
            <span class="opt-label">{opt.label}</span>
            <span class="opt-desc">{opt.desc}</span>
          </span>
        </label>
      {/each}
    </div>

    <!-- "apply to all" — only shown when more than one conflict -->
    {#if total > 1}
      <label class="apply-all-row">
        <input
          type="checkbox"
          class="sr-only"
          checked={applyToAll}
          onchange={() => { applyToAll = !applyToAll; }}
        />
        <span class="check-box" class:checked={applyToAll} aria-hidden="true">
          {#if applyToAll}✓{/if}
        </span>
        <span class="apply-all-label">
          Apply to all {remaining > 0 ? `remaining ${remaining}` : ""} file{remaining !== 1 ? "s" : ""}
        </span>
      </label>
    {/if}

    <!-- actions -->
    <div class="actions">
      <button class="btn-secondary" onclick={oncancel}>Cancel</button>
      <button class="btn-primary" onclick={confirm}>
        {isLast || applyToAll ? "Confirm" : "Next →"}
      </button>
    </div>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;   /* above SaveConfigDialog */
  }

  .dialog {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 10px;
    width: min(400px, 94vw);
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding: 1.1rem 1.2rem 1rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  /* ── header ── */
  .dlg-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .dlg-title {
    flex: 1;
    font-size: 0.9rem;
    font-weight: 600;
    color: #e8e8e8;
  }

  .dlg-counter {
    font-size: 0.75rem;
    color: #555;
    font-variant-numeric: tabular-nums;
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

  /* ── conflict info ── */
  .conflict-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    padding: 0.5rem 0.65rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    background: #161616;
  }

  .conflict-name {
    font-size: 0.85rem;
    font-weight: 600;
    color: #ddd;
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }

  .conflict-sub {
    font-size: 0.72rem;
    color: #555;
  }

  /* ── resolution option cards (same style as SaveConfigDialog) ── */
  .options {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .option {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    cursor: pointer;
    user-select: none;
    padding: 0.5rem 0.65rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    background: #181818;
    transition: border-color 0.12s, background 0.12s;
  }
  .option:hover          { border-color: #3a3a3a; background: #1e1e1e; }
  .option.selected       { border-color: #6c9ef8; background: rgba(108,158,248,0.06); }

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
  .option.selected .radio-dot { border-color: #6c9ef8; }

  .dot-inner {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #6c9ef8;
  }

  .opt-body {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }

  .opt-label {
    font-size: 0.82rem;
    color: #ddd;
    line-height: 1.3;
  }
  .option.selected .opt-label { color: #e8e8e8; }

  .opt-desc {
    font-size: 0.71rem;
    color: #666;
    line-height: 1.5;
  }

  /* ── apply-to-all row ── */
  .apply-all-row {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    cursor: pointer;
    user-select: none;
  }

  .sr-only {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
    border: 0;
  }

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
    transition: background 0.12s, border-color 0.12s;
  }
  .check-box.checked { background: #6c9ef8; border-color: #6c9ef8; }

  .apply-all-label {
    font-size: 0.8rem;
    color: #888;
  }

  /* ── action buttons ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
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

  .btn-secondary {
    padding: 0.35em 1.1em;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
    background: transparent;
    border: 1px solid #3a3a3a;
    color: #aaa;
    transition: border-color 0.12s, color 0.12s;
  }
  .btn-secondary:hover { border-color: #555; color: #ddd; }
</style>
