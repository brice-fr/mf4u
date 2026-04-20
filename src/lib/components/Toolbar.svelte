<script lang="ts">
  let {
    loading           = false,
    hasFile           = false,
    hasRawFrameGroups = false,
    decodingActive    = false,
    decodingDbCount   = 0,
    onopen            = () => {},
    onexport          = () => {},
    onframedecoding   = () => {},
  }: {
    loading?:           boolean;
    hasFile?:           boolean;
    hasRawFrameGroups?: boolean;
    decodingActive?:    boolean;
    decodingDbCount?:   number;
    onopen?:            () => void;
    onexport?:          () => void;
    onframedecoding?:   () => void;
  } = $props();
</script>

<div class="toolbar">

  <!-- Open -->
  <button
    class="icon-btn"
    onclick={onopen}
    disabled={loading}
    title="Open file… (⌘O)"
    aria-label="Open file"
  >
    {#if loading}
      <!-- Spinner -->
      <svg class="spin" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
    {:else}
      <!-- Folder-open icon -->
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        <polyline points="16 13 12 9 8 13"/>
        <line x1="12" y1="9" x2="12" y2="17"/>
      </svg>
    {/if}
  </button>

  <!-- Frame decoding -->
  <div class="icon-btn-wrap">
    <button
      class="icon-btn"
      class:active={decodingActive}
      onclick={onframedecoding}
      disabled={!hasRawFrameGroups}
      title="Configure frame decoding…"
      aria-label="Configure frame decoding"
    >
      <!-- Chain-link icon -->
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
      </svg>
    </button>
    {#if decodingActive && decodingDbCount > 0}
      <span class="active-badge">{decodingDbCount} DB</span>
    {/if}
  </div>

  <!-- Export -->
  <button
    class="icon-btn"
    onclick={onexport}
    disabled={!hasFile}
    title="Export… (⌘E)"
    aria-label="Export file"
  >
    <!-- Document with downward-arrow -->
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="1.8"
         stroke-linecap="round" stroke-linejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="12" y1="12" x2="12" y2="18"/>
      <polyline points="9 15 12 18 15 15"/>
    </svg>
  </button>

</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    background: #1e1e1e;
    border-bottom: 1px solid #2a2a2a;
    height: 36px;
    flex-shrink: 0;
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    color: #aaa;
    padding: 0;
    transition: background 0.1s, color 0.1s;
  }
  .icon-btn:hover:not(:disabled) { background: #2e2e2e; color: #e8e8e8; }
  .icon-btn:active:not(:disabled) { background: #3a3a3a; }
  .icon-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .icon-btn.active { color: #6c9ef8; }
  .icon-btn.active:hover:not(:disabled) { background: #1a2030; color: #81aaff; }

  .icon-btn svg { width: 18px; height: 18px; }

  /* wrapper for button + floating badge */
  .icon-btn-wrap {
    position: relative;
    display: flex;
    align-items: center;
  }

  .active-badge {
    position: absolute;
    top: -4px;
    right: -6px;
    background: #6c9ef8;
    color: #fff;
    font-size: 0.55rem;
    font-weight: 700;
    line-height: 1;
    padding: 1px 3px;
    border-radius: 3px;
    pointer-events: none;
    white-space: nowrap;
  }

  .spin { animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
