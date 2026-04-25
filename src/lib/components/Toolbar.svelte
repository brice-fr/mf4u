<script lang="ts">
  let {
    loading           = false,
    hasFile           = false,
    hasRawFrameGroups = false,
    decodingActive    = false,
    decodingDbCount   = 0,
    filterActive      = false,
    filterCount       = 0,
    flatten           = false,
    onopen            = () => {},
    onexport          = () => {},
    onframedecoding   = () => {},
    onchannelfilter   = () => {},
    onflattentoggle   = () => {},
    onpreferences     = () => {},
  }: {
    loading?:           boolean;
    hasFile?:           boolean;
    hasRawFrameGroups?: boolean;
    decodingActive?:    boolean;
    decodingDbCount?:   number;
    filterActive?:      boolean;
    filterCount?:       number;
    flatten?:           boolean;
    onopen?:            () => void;
    onexport?:          () => void;
    onframedecoding?:   () => void;
    onchannelfilter?:   () => void;
    onflattentoggle?:   () => void;
    onpreferences?:     () => void;
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

  <!-- Channel filter -->
  <div class="icon-btn-wrap">
    <button
      class="icon-btn"
      class:active={filterActive}
      onclick={onchannelfilter}
      disabled={!hasFile}
      title="Configure channel filter…"
      aria-label="Configure channel filter"
    >
      <!-- Funnel / filter icon -->
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
           fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
      </svg>
    </button>
    {#if filterActive}
      <span class="active-badge">{filterCount}</span>
    {/if}
  </div>

  <!-- Flatten toggle -->
  <button
    class="icon-btn"
    class:active={flatten}
    onclick={onflattentoggle}
    disabled={!hasFile}
    title={flatten ? "Flatten output: on — click to toggle off" : "Flatten output: off — merge all groups into one table"}
    aria-label="Toggle flatten output"
    aria-pressed={flatten}
  >
    <!-- Two rows merging into one -->
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="1.8"
         stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="18" height="5" rx="1"/>
      <rect x="3" y="10" width="18" height="5" rx="1"/>
      <line x1="12" y1="17" x2="12" y2="21"/>
      <polyline points="9 18.5 12 21 15 18.5"/>
    </svg>
  </button>

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

  <!-- Spacer pushes the gear icon to the far right -->
  <div class="spacer"></div>

  <!-- Preferences -->
  <button
    class="icon-btn"
    onclick={onpreferences}
    title="Preferences… (⌘,)"
    aria-label="Preferences"
  >
    <!-- Gear / cog icon -->
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="1.8"
         stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
               a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
               A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
               l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
               A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
               l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
               a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
               l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
               a1.65 1.65 0 0 0-1.51 1z"/>
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

  .spacer { flex: 1; }

  .spin { animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
