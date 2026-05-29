<script lang="ts">
  import { save as saveDialog } from "@tauri-apps/plugin-dialog";
  import type { DbcPathMode } from "$lib/rpc";

  let {
    onconfirm,
    oncancel,
  }: {
    /** Called with the chosen save path and DBC path mode once the user
     *  selects a location.  The parent is responsible for writing the file. */
    onconfirm: (path: string, mode: DbcPathMode) => void;
    oncancel:  () => void;
  } = $props();

  let mode: DbcPathMode = $state("relative");
  let picking = $state(false);

  const OPTIONS: Array<{
    value: DbcPathMode;
    label: string;
    desc:  string;
  }> = [
    {
      value: "relative",
      label: "Relative paths",
      desc:  "Store each DBC path relative to the config file. Portable when the config and DBC files are moved together.",
    },
    {
      value: "absolute",
      label: "Absolute paths",
      desc:  "Store the full system path. The config works only on this machine with files in their current locations.",
    },
    {
      value: "copy",
      label: "Copy DBC files alongside config",
      desc:  "Copy each DBC file into the same folder as the config and reference it by filename. The config folder becomes fully self-contained.",
    },
  ];

  async function choose() {
    picking = true;
    try {
      const path = await saveDialog({
        filters:     [{ name: "mf4u config", extensions: ["mf4u"] }],
        defaultPath: "config.mf4u",
      });
      if (path) onconfirm(path as string, mode);
    } finally {
      picking = false;
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
    role="dialog"
    aria-modal="true"
    aria-label="Save configuration"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">Save Configuration</span>
      <button class="close-x" onclick={oncancel} aria-label="Close">✕</button>
    </header>

    <!-- ── DBC path mode ── -->
    <section class="section">
      <span class="section-label">DBC / ARXML file paths</span>
      <div class="options">
        {#each OPTIONS as opt (opt.value)}
          <label class="option" class:selected={mode === opt.value}>
            <input
              type="radio"
              class="sr-only"
              name="dbc-path-mode"
              value={opt.value}
              checked={mode === opt.value}
              onchange={() => { mode = opt.value; }}
            />
            <span class="radio-dot" aria-hidden="true">
              {#if mode === opt.value}<span class="dot-inner"></span>{/if}
            </span>
            <span class="opt-body">
              <span class="opt-label">{opt.label}</span>
              <span class="opt-desc">{opt.desc}</span>
            </span>
          </label>
        {/each}
      </div>
    </section>

    <!-- ── actions ── -->
    <div class="actions">
      <button class="btn-secondary" onclick={oncancel} disabled={picking}>Cancel</button>
      <button class="btn-primary"   onclick={choose}   disabled={picking}>
        {picking ? "Opening…" : "Choose location…"}
      </button>
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
  .close-x:hover { color: #ccc; }

  /* ── section ── */
  .section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .section-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #555;
  }

  /* ── option cards ── */
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
    padding: 0.55rem 0.7rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    background: #181818;
    transition: border-color 0.12s, background 0.12s;
  }
  .option:hover          { border-color: #3a3a3a; background: #1e1e1e; }
  .option.selected       { border-color: #6c9ef8; background: rgba(108, 158, 248, 0.06); }

  /* ── radio dot ── */
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

  /* ── option text ── */
  .opt-body {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
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

  /* ── actions ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.1rem;
  }

  /* hidden input */
  .sr-only {
    position: absolute;
    width: 1px; height: 1px;
    padding: 0; margin: -1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
    border: 0;
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
  .btn-primary:hover:not(:disabled) { background: #81aaff; border-color: #81aaff; }
  .btn-primary:disabled { opacity: 0.5; cursor: default; }

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
  .btn-secondary:hover:not(:disabled) { border-color: #555; color: #ddd; }
  .btn-secondary:disabled { opacity: 0.5; cursor: default; }
</style>
