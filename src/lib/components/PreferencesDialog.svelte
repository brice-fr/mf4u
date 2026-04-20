<script lang="ts">
  import type { AppPrefs } from "$lib/prefs";
  import { savePrefs } from "$lib/prefs";

  let {
    prefs,
    onchange,
    onclose,
  }: {
    prefs:    AppPrefs;
    onchange: (p: AppPrefs) => void;
    onclose:  () => void;
  } = $props();

  function toggle(key: keyof AppPrefs) {
    const updated = { ...prefs, [key]: !prefs[key] };
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
    width: min(400px, 94vw);
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
