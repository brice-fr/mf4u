<script lang="ts">
  import { getExportableSignals } from "$lib/rpc";
  import type { GroupInfo, DbAssignment, FilteredChannel, SignalSource } from "$lib/rpc";

  let {
    groups,
    sessionId,
    dbAssignments = [],
    selectedSignals = null,
    onchange,
    onclose,
  }: {
    groups:          GroupInfo[];
    sessionId:       string;
    dbAssignments?:  DbAssignment[];
    selectedSignals: FilteredChannel[] | null;
    onchange:        (filter: FilteredChannel[] | null) => void;
    onclose:         () => void;
  } = $props();

  // ── types ─────────────────────────────────────────────────────────────── //

  interface DisplayChannel {
    key:          string;   // "${group_index}::${channel_name}"
    group_index:  number;
    acq_name:     string;
    channel_name: string;
    unit:         string;
    source:       SignalSource;
  }

  interface AvailGroup {
    id:          string;   // "${source}::${group_index}"
    group_index: number;
    acq_name:    string;
    source:      SignalSource;
    channels:    DisplayChannel[];
  }

  function chKey(group_index: number, channel_name: string): string {
    return `${group_index}::${channel_name}`;
  }

  // ── initialise available / toExport from props ────────────────────────── //

  // Build the complete set of known physical channels from the groups prop.
  const allPhysical: DisplayChannel[] = $derived(
    groups
      .filter(g => !g.is_bus_raw)
      .flatMap(g =>
        g.channels
          .filter(ch => ch.name)
          .map(ch => ({
            key:          chKey(g.index, ch.name),
            group_index:  g.index,
            acq_name:     g.acq_name,
            channel_name: ch.name,
            unit:         ch.unit,
            source:       "physical" as SignalSource,
          }))
      )
  );

  function initPanels(): { avail: DisplayChannel[]; exp: DisplayChannel[] } {
    if (selectedSignals === null) {
      // Default: all physical channels go to export
      return { avail: [], exp: [...allPhysical] };
    }

    const selectedKeys   = new Set(selectedSignals.map(s => chKey(s.group_index, s.channel_name)));
    const physicalKeySet = new Set(allPhysical.map(c => c.key));

    const inExport   = allPhysical.filter(c => selectedKeys.has(c.key));
    const notExport  = allPhysical.filter(c => !selectedKeys.has(c.key));

    // Restore decoded channels that were stored in selectedSignals
    const decodedInFilter: DisplayChannel[] = selectedSignals
      .filter(s => !physicalKeySet.has(chKey(s.group_index, s.channel_name)))
      .map(s => ({
        key:          chKey(s.group_index, s.channel_name),
        group_index:  s.group_index,
        acq_name:     s.acq_name,
        channel_name: s.channel_name,
        unit:         s.unit,
        source:       s.source,
      }));

    return { avail: notExport, exp: [...inExport, ...decodedInFilter] };
  }

  const { avail: initAvail, exp: initExp } = initPanels();

  let available = $state(initAvail);
  let toExport  = $state(initExp);

  // ── UI state ──────────────────────────────────────────────────────────── //

  let selectedAvail  = $state(new Set<string>());
  let selectedExport = $state(new Set<string>());
  let search         = $state("");
  let previewLoading = $state(false);
  let previewFetched = $state(false);
  let previewError   = $state<string | null>(null);
  let collapsedGroups = $state(new Set<string>());   // group IDs that are collapsed

  // ── derived ───────────────────────────────────────────────────────────── //

  const filteredAvail: DisplayChannel[] = $derived.by(() => {
    const q = search.toLowerCase().trim();
    if (!q) return available;
    return available.filter(c =>
      c.channel_name.toLowerCase().includes(q) ||
      c.acq_name.toLowerCase().includes(q) ||
      c.unit.toLowerCase().includes(q)
    );
  });

  const availGroups: AvailGroup[] = $derived.by(() => {
    const map = new Map<string, AvailGroup>();
    for (const ch of filteredAvail) {
      const id = `${ch.source}::${ch.group_index}`;
      if (!map.has(id)) {
        map.set(id, { id, group_index: ch.group_index, acq_name: ch.acq_name,
                      source: ch.source, channels: [] });
      }
      map.get(id)!.channels.push(ch);
    }
    return [...map.values()];
  });

  // Total across both panels (grows when decoded channels are previewed)
  const totalChannels = $derived(available.length + toExport.length);

  const hasSelection = $derived(dbAssignments.length > 0);

  // ── shuttle operations ────────────────────────────────────────────────── //

  function addSelected() {
    if (selectedAvail.size === 0) return;
    const keys = selectedAvail;
    toExport  = [...toExport, ...available.filter(c => keys.has(c.key))];
    available = available.filter(c => !keys.has(c.key));
    selectedAvail = new Set();
  }

  function addAll() {
    if (filteredAvail.length === 0) return;
    const keys = new Set(filteredAvail.map(c => c.key));
    toExport  = [...toExport, ...filteredAvail];
    available = available.filter(c => !keys.has(c.key));
    selectedAvail = new Set();
  }

  function removeAll() {
    available = [...available, ...toExport];
    toExport  = [];
    selectedExport = new Set();
  }

  function removeSelected() {
    if (selectedExport.size === 0) return;
    const keys = selectedExport;
    available = [...available, ...toExport.filter(c => keys.has(c.key))];
    toExport  = toExport.filter(c => !keys.has(c.key));
    selectedExport = new Set();
  }

  function toggleAvail(key: string) {
    const next = new Set(selectedAvail);
    if (next.has(key)) next.delete(key); else next.add(key);
    selectedAvail = next;
  }

  function toggleExport(key: string) {
    const next = new Set(selectedExport);
    if (next.has(key)) next.delete(key); else next.add(key);
    selectedExport = next;
  }

  function toggleGroup(id: string) {
    const next = new Set(collapsedGroups);
    if (next.has(id)) next.delete(id); else next.add(id);
    collapsedGroups = next;
  }

  // ── preview decoded channels ──────────────────────────────────────────── //

  async function loadDecodedPreview() {
    if (previewLoading || dbAssignments.length === 0) return;
    previewLoading = true;
    previewError   = null;
    try {
      const result = await getExportableSignals(sessionId, dbAssignments);
      const existingKeys = new Set([...available.map(c => c.key), ...toExport.map(c => c.key)]);
      const newDecoded: DisplayChannel[] = [];
      for (const grp of result.groups) {
        if (grp.source !== "decoded") continue;
        for (const ch of grp.channels) {
          const key = chKey(grp.group_index, ch.name);
          if (!existingKeys.has(key)) {
            newDecoded.push({
              key,
              group_index:  grp.group_index,
              acq_name:     grp.acq_name,
              channel_name: ch.name,
              unit:         ch.unit,
              source:       "decoded",
            });
          }
        }
      }
      available = [...available, ...newDecoded];
      previewFetched = true;
    } catch (e) {
      previewError = String(e);
    } finally {
      previewLoading = false;
    }
  }

  // ── close / apply ─────────────────────────────────────────────────────── //

  function applyAndClose() {
    if (toExport.length === 0 || toExport.length === totalChannels) {
      // Empty selection or all channels → no filter
      onchange(null);
    } else {
      onchange(toExport.map(c => ({
        group_index:  c.group_index,
        channel_name: c.channel_name,
        acq_name:     c.acq_name,
        unit:         c.unit,
        source:       c.source,
      })));
    }
    onclose();
  }
</script>

<!-- backdrop -->
<div
  class="overlay"
  onclick={applyAndClose}
  onkeydown={(e) => e.key === "Escape" && applyAndClose()}
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
    aria-label="Configure channel filter"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">Configure channel filter</span>
      <button class="close-x" onclick={applyAndClose} aria-label="Close">✕</button>
    </header>

    <div class="three-col">

      <!-- ── left: available signals ── -->
      <div class="panel avail-panel">
        <div class="panel-label">Available signals</div>

        <!-- search box -->
        <div class="search-wrap">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            class="search-input"
            type="text"
            placeholder="Search signals…"
            bind:value={search}
            aria-label="Search available signals"
          />
          {#if search}
            <button class="search-clear" onclick={() => (search = "")} aria-label="Clear search">✕</button>
          {/if}
        </div>

        <!-- grouped channel list -->
        <div class="channel-list" role="listbox" aria-multiselectable="true">
          {#if availGroups.length === 0}
            <p class="empty-hint">
              {search ? "No signals match the search." : "No signals available."}
            </p>
          {:else}
            {#each availGroups as grp (grp.id)}
              {@const expanded = !collapsedGroups.has(grp.id)}
              <!-- group header -->
              <button
                class="group-header"
                onclick={() => toggleGroup(grp.id)}
                aria-expanded={expanded}
              >
                <span class="group-chevron">{expanded ? "▾" : "▸"}</span>
                <span class="group-name">{grp.acq_name}</span>
                {#if grp.source === "decoded"}
                  <span class="decoded-badge">decoded</span>
                {/if}
                <span class="group-count">{grp.channels.length}</span>
              </button>

              {#if expanded}
                {#each grp.channels as ch (ch.key)}
                  <div
                    class="ch-row"
                    class:ch-selected={selectedAvail.has(ch.key)}
                    onclick={() => toggleAvail(ch.key)}
                    onkeydown={(e) => e.key === "Enter" && toggleAvail(ch.key)}
                    role="option"
                    aria-selected={selectedAvail.has(ch.key)}
                    tabindex="0"
                  >
                    <span class="ch-name">{ch.channel_name}</span>
                    {#if ch.unit}
                      <span class="ch-unit">[{ch.unit}]</span>
                    {/if}
                  </div>
                {/each}
              {/if}
            {/each}
          {/if}
        </div>

        <!-- preview decoded button -->
        {#if hasSelection}
          <div class="preview-row">
            <button
              class="preview-btn"
              onclick={loadDecodedPreview}
              disabled={previewLoading}
            >
              {#if previewLoading}
                <span class="btn-spinner">⏳</span> Loading…
              {:else if previewFetched}
                ↻ Reload decoded channels
              {:else}
                ⊕ Preview decoded channels
              {/if}
            </button>
            {#if previewError}
              <span class="preview-err" title={previewError}>✗ error</span>
            {/if}
          </div>
        {/if}
      </div>

      <!-- ── centre: shuttle buttons ── -->
      <div class="shuttle-col">
        <button
          class="shuttle-btn"
          onclick={addSelected}
          disabled={selectedAvail.size === 0}
          title="Add selected"
          aria-label="Add selected to export"
        >→</button>
        <button
          class="shuttle-btn"
          onclick={addAll}
          disabled={filteredAvail.length === 0}
          title="Add all (respects search)"
          aria-label="Add all to export"
        >&raquo;</button>
        <button
          class="shuttle-btn"
          onclick={removeAll}
          disabled={toExport.length === 0}
          title="Remove all"
          aria-label="Remove all from export"
        >&laquo;</button>
        <button
          class="shuttle-btn"
          onclick={removeSelected}
          disabled={selectedExport.size === 0}
          title="Remove selected"
          aria-label="Remove selected from export"
        >←</button>
      </div>

      <!-- ── right: signals to export ── -->
      <div class="panel export-panel">
        <div class="panel-label">Signals to export</div>

        <div class="channel-list export-list" role="listbox" aria-multiselectable="true">
          {#if toExport.length === 0}
            <p class="empty-hint center">
              No signals selected — exporting nothing.
            </p>
          {:else}
            {#each toExport as ch (ch.key)}
              <div
                class="ch-row ch-row-export"
                class:ch-selected={selectedExport.has(ch.key)}
                onclick={() => toggleExport(ch.key)}
                onkeydown={(e) => e.key === "Enter" && toggleExport(ch.key)}
                role="option"
                aria-selected={selectedExport.has(ch.key)}
                tabindex="0"
              >
                <span class="ch-name">{ch.channel_name}</span>
                {#if ch.unit}
                  <span class="ch-unit">[{ch.unit}]</span>
                {/if}
                {#if ch.source === "decoded"}
                  <span class="decoded-badge">dec</span>
                {/if}
                <span class="ch-group">{ch.acq_name}</span>
              </div>
            {/each}
          {/if}
        </div>

        <!-- counter -->
        <div class="export-counter">
          {#if toExport.length === totalChannels || toExport.length === 0}
            <span class="counter-all">All signals</span>
          {:else}
            <span class="counter-n">{toExport.length}</span>
            <span class="counter-sep">/</span>
            <span class="counter-m">{totalChannels} signals</span>
          {/if}
        </div>
      </div>

    </div><!-- three-col -->

    <!-- ── actions ── -->
    <div class="actions">
      <button class="btn-primary" onclick={applyAndClose}>Close</button>
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

  /* ── dialog ── */
  .dialog {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 10px;
    width: min(720px, 96vw);
    max-height: 82vh;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
    padding: 1.1rem 1.2rem 1rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  /* ── header ── */
  .dlg-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
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

  /* ── three-column layout ── */
  .three-col {
    display: grid;
    grid-template-columns: 1fr 48px 1fr;
    gap: 0.6rem;
    min-height: 0;
    flex: 1;
    overflow: hidden;
  }

  /* ── shared panel ── */
  .panel {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    min-height: 0;
    min-width: 0;
  }

  .panel-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #666;
    flex-shrink: 0;
  }

  /* ── search box ── */
  .search-wrap {
    position: relative;
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }

  .search-icon {
    position: absolute;
    left: 7px;
    width: 13px;
    height: 13px;
    color: #555;
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    background: #161616;
    border: 1px solid #2e2e2e;
    border-radius: 5px;
    color: #ccc;
    font-size: 0.78rem;
    padding: 0.3em 1.6em 0.3em 1.8em;
    outline: none;
  }
  .search-input:focus { border-color: #4a5568; }

  .search-clear {
    position: absolute;
    right: 6px;
    background: none;
    border: none;
    color: #555;
    font-size: 0.65rem;
    cursor: pointer;
    padding: 0.1em 0.2em;
    line-height: 1;
  }
  .search-clear:hover { color: #aaa; }

  /* ── channel list (shared by both panels) ── */
  .channel-list {
    flex: 1;
    overflow-x: hidden;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1px;
    scrollbar-color: #555 transparent;
    scrollbar-width: thin;
    min-height: 0;
    background: #161616;
    border: 1px solid #262626;
    border-radius: 5px;
    padding: 3px;
  }
  .channel-list::-webkit-scrollbar       { width: 7px; }
  .channel-list::-webkit-scrollbar-track { background: transparent; }
  .channel-list::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
  .channel-list::-webkit-scrollbar-thumb:hover { background: #777; }

  /* ── group header (left panel) ── */
  .group-header {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    background: none;
    border: none;
    width: 100%;
    text-align: left;
    cursor: pointer;
    padding: 0.3em 0.4em;
    border-radius: 4px;
    user-select: none;
    color: #888;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    transition: background 0.1s;
  }
  .group-header:hover { background: #1e1e1e; color: #bbb; }

  .group-chevron { font-size: 0.65rem; flex-shrink: 0; }

  .group-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .group-count {
    font-size: 0.65rem;
    color: #555;
    flex-shrink: 0;
  }

  /* ── channel row ── */
  .ch-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25em 0.4em 0.25em 1.2em;
    border-radius: 3px;
    cursor: pointer;
    user-select: none;
    border: 1px solid transparent;
    transition: background 0.08s;
  }
  .ch-row:hover    { background: #212121; }
  .ch-row:focus    { outline: 1px solid #4a5568; outline-offset: -1px; }
  .ch-row.ch-selected { background: #161e2e; border-color: #2a3a5a; }

  .ch-row-export { padding-left: 0.4em; }

  .ch-name {
    font-size: 0.78rem;
    color: #ccc;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .ch-unit {
    font-size: 0.68rem;
    color: #555;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .ch-group {
    font-size: 0.65rem;
    color: #444;
    flex-shrink: 0;
    white-space: nowrap;
    max-width: 6rem;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .decoded-badge {
    font-size: 0.58rem;
    font-weight: 600;
    color: #c8832a;
    background: #1e1208;
    border: 1px solid #3a2510;
    border-radius: 3px;
    padding: 0 4px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  /* ── shuttle column ── */
  .shuttle-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .shuttle-btn {
    width: 36px;
    height: 28px;
    background: #252525;
    border: 1px solid #333;
    border-radius: 5px;
    color: #999;
    font-size: 0.85rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color 0.1s, color 0.1s, background 0.1s;
  }
  .shuttle-btn:hover:not(:disabled) { border-color: #6c9ef8; color: #6c9ef8; background: #161e2e; }
  .shuttle-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  /* ── preview button ── */
  .preview-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .preview-btn {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.72rem;
    color: #555;
    cursor: pointer;
    text-align: left;
    transition: color 0.12s;
  }
  .preview-btn:hover:not(:disabled) { color: #6c9ef8; }
  .preview-btn:disabled { opacity: 0.5; cursor: default; }

  .btn-spinner { font-size: 0.7rem; }

  .preview-err {
    font-size: 0.68rem;
    color: #c8832a;
    cursor: help;
  }

  /* ── export counter ── */
  .export-counter {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-shrink: 0;
    font-size: 0.72rem;
    justify-content: flex-end;
    padding-right: 0.2rem;
  }

  .counter-all  { color: #555; }
  .counter-n    { color: #6c9ef8; font-weight: 600; }
  .counter-sep  { color: #444; }
  .counter-m    { color: #555; }

  /* ── empty hints ── */
  .empty-hint {
    font-size: 0.75rem;
    color: #444;
    margin: 0;
    padding: 0.5rem 0.4rem;
    line-height: 1.4;
  }
  .empty-hint.center { text-align: center; padding-top: 1.5rem; }

  /* ── actions ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    padding-top: 0.1rem;
    flex-shrink: 0;
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
