<script lang="ts">
  import { open as openDialog } from "@tauri-apps/plugin-dialog";
  import { previewBusDecoding } from "$lib/rpc";
  import type { GroupInfo, DbAssignment, BusDecodingPreview } from "$lib/rpc";
  import { busColor } from "$lib/busColors";

  let {
    groups,
    sessionId,
    dbAssignments,
    onchange,
    onclose,
  }: {
    groups:        GroupInfo[];
    sessionId:     string;
    dbAssignments: DbAssignment[];
    onchange:      (assignments: DbAssignment[]) => void;
    onclose:       () => void;
  } = $props();

  // ── derived data ──────────────────────────────────────────────────────────── //

  const rawGroups = $derived(groups.filter(g => g.is_bus_raw));

  /** group_index → ordered db_path[] derived from the flat dbAssignments prop. */
  const assignmentMap = $derived.by(() => {
    const map = new Map<number, string[]>();
    for (const g of rawGroups) map.set(g.index, []);
    for (const a of dbAssignments) {
      const arr = map.get(a.group_index);
      if (arr) arr.push(a.db_path);
    }
    return map;
  });

  // ── local UI state ─────────────────────────────────────────────────────────── //

  let selectedIndices  = $state(new Set<number>());
  let lastClickedIndex = $state<number | null>(null);

  const selectedList = $derived([...selectedIndices].sort((a, b) => a - b));
  const allSelected  = $derived(
    rawGroups.length > 0 && rawGroups.every(g => selectedIndices.has(g.index))
  );

  /** DB list of the first selected group — what the right panel shows. */
  const currentDbList = $derived(
    selectedList.length > 0 ? (assignmentMap.get(selectedList[0]) ?? []) : []
  );

  /** True when multiple selected groups have different DB configs. */
  const configsDiffer = $derived.by(() => {
    if (selectedList.length <= 1) return false;
    const ref = JSON.stringify(assignmentMap.get(selectedList[0]) ?? []);
    return selectedList.slice(1).some(
      idx => JSON.stringify(assignmentMap.get(idx) ?? []) !== ref
    );
  });

  const panelTitle = $derived.by((): string => {
    const n = selectedList.length;
    if (n === 0) return "";
    if (n === 1) return rawGroups.find(g => g.index === selectedList[0])?.acq_name ?? `Group ${selectedList[0]}`;
    return `${n} groups selected`;
  });

  // ── preview badges ─────────────────────────────────────────────────────────── //

  interface PreviewItem {
    status: "loading" | "ok" | "none" | "error";
    matched_messages?: number;
    signal_count?: number;
    error?: string;
  }

  let previews     = $state(new Map<string, PreviewItem>());
  // Plain let — NOT $state.  Reading $state inside $effect creates a reactive
  // dependency; writing to it from within the same effect causes an infinite
  // re-run loop.  A plain let is just a mutable slot with no reactivity.
  let previewTimer: ReturnType<typeof setTimeout> | null = null;

  function previewKey(groupIndex: number, dbPath: string) {
    return `${groupIndex}::${dbPath}`;
  }

  // Only dbAssignments is a reactive dependency here.
  // previewTimer and previews are NOT read inside this effect, so they are
  // never tracked — mutating them from runPreview() is safe.
  $effect(() => {
    const assignments = dbAssignments;           // the only reactive dep
    if (assignments.length === 0) {
      clearTimeout(previewTimer ?? undefined);
      return;
    }
    clearTimeout(previewTimer ?? undefined);
    const timer = setTimeout(() => runPreview(assignments), 400);
    previewTimer = timer;
    return () => { clearTimeout(timer); };
  });

  async function runPreview(assignments: DbAssignment[]) {
    // Mark newly-seen entries as loading (state mutation outside $effect — safe).
    const loading = new Map(previews);
    for (const a of assignments) {
      const key = previewKey(a.group_index, a.db_path);
      if (!loading.has(key)) loading.set(key, { status: "loading" });
    }
    previews = loading;

    try {
      const result = await previewBusDecoding(sessionId, assignments);
      const updated = new Map(previews);
      for (const item of result.previews) {
        const key = previewKey(item.group_index, item.db_path);
        if (item.error) {
          updated.set(key, { status: "error", error: item.error });
        } else if (item.matched_messages === 0) {
          updated.set(key, { status: "none", matched_messages: 0, signal_count: 0 });
        } else {
          updated.set(key, {
            status: "ok",
            matched_messages: item.matched_messages,
            signal_count: item.signal_count ?? 0,
          });
        }
      }
      previews = updated;
    } catch {
      // Ignore transient preview errors — badge stays at "loading" until next change.
    }
  }

  // ── mutations ──────────────────────────────────────────────────────────────── //

  /** Convert local assignmentMap edits back to the flat array and notify parent. */
  function pushMap(newMap: Map<number, string[]>) {
    const out: DbAssignment[] = [];
    for (const [groupIndex, paths] of newMap.entries()) {
      for (const db_path of paths) out.push({ group_index: groupIndex, db_path });
    }
    onchange(out);
  }

  /** Deep-clone the current assignmentMap for mutation. */
  function cloneMap(): Map<number, string[]> {
    const m = new Map<number, string[]>();
    for (const [k, v] of assignmentMap.entries()) m.set(k, [...v]);
    return m;
  }

  async function addDbFile() {
    if (selectedList.length === 0) return;
    const result = await openDialog({
      multiple: false,
      filters: [{ name: "Bus description files", extensions: ["dbc", "arxml"] }],
    });
    if (!result) return;
    const dbPath = typeof result === "string" ? result : (result as string[])[0];

    const m = cloneMap();
    for (const idx of selectedList) {
      const paths = m.get(idx) ?? [];
      if (!paths.includes(dbPath)) paths.push(dbPath);
      m.set(idx, paths);
    }
    pushMap(m);
  }

  function removeDb(dbPath: string) {
    const m = cloneMap();
    for (const idx of selectedList) m.set(idx, (m.get(idx) ?? []).filter(p => p !== dbPath));
    pushMap(m);
  }

  function moveUp(dbPath: string) {
    const m = cloneMap();
    for (const idx of selectedList) {
      const paths = m.get(idx) ?? [];
      const i = paths.indexOf(dbPath);
      if (i > 0) { [paths[i - 1], paths[i]] = [paths[i], paths[i - 1]]; }
      m.set(idx, paths);
    }
    pushMap(m);
  }

  function moveDown(dbPath: string) {
    const m = cloneMap();
    for (const idx of selectedList) {
      const paths = m.get(idx) ?? [];
      const i = paths.indexOf(dbPath);
      if (i >= 0 && i < paths.length - 1) { [paths[i], paths[i + 1]] = [paths[i + 1], paths[i]]; }
      m.set(idx, paths);
    }
    pushMap(m);
  }

  function clearAll() {
    const m = cloneMap();
    for (const idx of selectedList) m.set(idx, []);
    pushMap(m);
  }

  // ── group list selection ───────────────────────────────────────────────────── //

  function onGroupClick(groupIndex: number, event: MouseEvent) {
    const allIdxs = rawGroups.map(g => g.index);
    if (event.shiftKey && lastClickedIndex !== null) {
      const from = allIdxs.indexOf(lastClickedIndex);
      const to   = allIdxs.indexOf(groupIndex);
      const [lo, hi] = from < to ? [from, to] : [to, from];
      const next = new Set(selectedIndices);
      for (let i = lo; i <= hi; i++) next.add(allIdxs[i]);
      selectedIndices = next;
    } else if (event.metaKey || event.ctrlKey) {
      const next = new Set(selectedIndices);
      if (next.has(groupIndex)) next.delete(groupIndex); else next.add(groupIndex);
      selectedIndices = next;
    } else {
      selectedIndices = new Set([groupIndex]);
    }
    lastClickedIndex = groupIndex;
  }

  function toggleSelectAll() {
    selectedIndices = allSelected
      ? new Set()
      : new Set(rawGroups.map(g => g.index));
  }

  // ── misc helpers ──────────────────────────────────────────────────────────── //
  function basename(p: string) { return p.replace(/.*[/\\]/, ""); }
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
    aria-label="Configure frame decoding"
    tabindex="-1"
  >
    <header class="dlg-header">
      <span class="dlg-title">Configure frame decoding</span>
      <button class="close-x" onclick={onclose} aria-label="Close">✕</button>
    </header>

    <div class="two-col">

      <!-- ── left panel: group list ── -->
      <div class="group-panel">
        <div class="panel-label">Raw-frame groups</div>

        {#if rawGroups.length === 0}
          <p class="empty-hint">No raw-frame groups in this file.</p>
        {:else}
          <button class="select-all-btn" onclick={toggleSelectAll}>
            {allSelected ? "Deselect all" : "Select all"}
          </button>

          <div class="group-list" role="listbox" aria-multiselectable="true">
            {#each rawGroups as group}
              {@const dbCount = assignmentMap.get(group.index)?.length ?? 0}
              <div
                class="group-row"
                class:selected={selectedIndices.has(group.index)}
                onclick={(e) => onGroupClick(group.index, e)}
                onkeydown={(e) => e.key === "Enter" && onGroupClick(group.index, e as unknown as MouseEvent)}
                role="option"
                aria-selected={selectedIndices.has(group.index)}
                tabindex="0"
              >
                <span class="group-name" title={group.acq_name}>{group.acq_name}</span>
                {#if group.bus_type}
                  <span
                    class="bus-badge"
                    style:color={busColor(group.bus_type).text}
                    style:background={busColor(group.bus_type).bg}
                    style:border-color={busColor(group.bus_type).border}
                  >{group.bus_type}</span>
                {/if}
                {#if dbCount > 0}
                  <span class="db-count">{dbCount}</span>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- ── right panel: DB assignment ── -->
      <div class="db-panel">
        {#if selectedList.length === 0}
          <div class="panel-label">Select a group to configure</div>
          <p class="empty-hint top-space">
            Select one or more groups on the left to assign bus description files.
          </p>
        {:else}
          <div class="panel-label">{panelTitle}</div>

          {#if configsDiffer}
            <p class="configs-differ">
              ⚠ Configs differ — changes will replace all selected groups.
            </p>
          {/if}

          <div class="db-list">
            {#if currentDbList.length === 0}
              <p class="empty-hint top-space">No DB files assigned. Use "Add DB file…" below.</p>
            {:else}
              {#each currentDbList as dbPath, i}
                {@const key     = previewKey(selectedList[0], dbPath)}
                {@const preview = previews.get(key)}
                {@const isFirst = i === 0}
                {@const isLast  = i === currentDbList.length - 1}
                <div class="db-row">
                  <span class="db-index">{i + 1}.</span>
                  <span class="db-name" title={dbPath}>{basename(dbPath)}</span>
                  <span class="db-arrows">
                    {#if !isFirst}
                      <button class="arrow-btn" onclick={() => moveUp(dbPath)} title="Move up">↑</button>
                    {:else}
                      <span class="arrow-spacer"></span>
                    {/if}
                    {#if !isLast}
                      <button class="arrow-btn" onclick={() => moveDown(dbPath)} title="Move down">↓</button>
                    {:else}
                      <span class="arrow-spacer"></span>
                    {/if}
                  </span>
                  <button class="remove-btn" onclick={() => removeDb(dbPath)} title="Remove">✕</button>
                  <span class="db-preview">
                    {#if !preview || preview.status === "loading"}
                      <span class="prev-spin">⏳</span>
                    {:else if preview.status === "ok"}
                      <span class="prev-ok">✓ {preview.matched_messages} msg · {preview.signal_count} sig</span>
                    {:else if preview.status === "none"}
                      <span class="prev-none">✗ 0 messages matched</span>
                    {:else}
                      <span class="prev-err" title={preview.error ?? ""}>✗ load error</span>
                    {/if}
                  </span>
                </div>
              {/each}
            {/if}
          </div>

          <div class="db-footer">
            <button class="add-btn" onclick={addDbFile}>+ Add DB file…</button>
            {#if currentDbList.length > 0}
              <button class="clear-btn" onclick={clearAll}>Clear all</button>
            {/if}
          </div>
        {/if}
      </div>

    </div><!-- two-col -->

    <div class="actions">
      <button class="btn-ghost" onclick={onclose}>Close</button>
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
    width: min(680px, 96vw);
    max-height: 80vh;
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

  /* ── two-column layout ── */
  .two-col {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 0.8rem;
    min-height: 0;
    flex: 1;
    overflow: hidden;
  }

  /* ── shared panel styles ── */
  .group-panel,
  .db-panel {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    min-height: 0;
  }

  .panel-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #666;
    flex-shrink: 0;
  }

  .empty-hint {
    font-size: 0.78rem;
    color: #555;
    margin: 0;
    line-height: 1.4;
  }
  .empty-hint.top-space { margin-top: 1.5rem; text-align: center; }

  /* ── left: group list ── */
  .select-all-btn {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.72rem;
    color: #555;
    cursor: pointer;
    text-align: left;
    flex-shrink: 0;
  }
  .select-all-btn:hover { color: #6c9ef8; text-decoration: underline; }

  .group-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    scrollbar-color: #555 transparent;
    scrollbar-width: thin;
  }
  .group-list::-webkit-scrollbar       { width: 7px; }
  .group-list::-webkit-scrollbar-track { background: transparent; }
  .group-list::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
  .group-list::-webkit-scrollbar-thumb:hover { background: #777; }

  .group-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3em 0.45em;
    border-radius: 4px;
    cursor: pointer;
    user-select: none;
    border: 1px solid transparent;
    transition: background 0.1s;
  }
  .group-row:hover  { background: #252525; }
  .group-row.selected { background: #161e2e; border-color: #2a3a5a; }
  .group-row:focus  { outline: 1px solid #6c9ef8; outline-offset: -1px; }

  .group-name {
    font-size: 0.78rem;
    color: #ccc;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bus-badge {
    font-size: 0.62rem;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid;
    flex-shrink: 0;
  }

  .db-count {
    font-size: 0.65rem;
    color: #6c9ef8;
    font-weight: 600;
    flex-shrink: 0;
  }

  /* ── right: DB list ── */
  .configs-differ {
    font-size: 0.72rem;
    color: #c8832a;
    margin: 0;
    line-height: 1.4;
    flex-shrink: 0;
  }

  .db-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
    scrollbar-color: #555 transparent;
    scrollbar-width: thin;
    min-height: 0;
  }
  .db-list::-webkit-scrollbar       { width: 7px; }
  .db-list::-webkit-scrollbar-track { background: transparent; }
  .db-list::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
  .db-list::-webkit-scrollbar-thumb:hover { background: #777; }

  .db-row {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3em 0.25em;
    border-radius: 4px;
    background: #181818;
    border: 1px solid #262626;
  }

  .db-index {
    font-size: 0.7rem;
    color: #555;
    min-width: 1.4em;
    text-align: right;
    flex-shrink: 0;
  }

  .db-name {
    flex: 1;
    min-width: 0;
    font-size: 0.78rem;
    color: #bbb;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .db-arrows {
    display: flex;
    gap: 1px;
    flex-shrink: 0;
  }

  .arrow-btn, .remove-btn {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    font-size: 0.75rem;
    padding: 0 3px;
    line-height: 1.5;
    border-radius: 3px;
    transition: color 0.1s, background 0.1s;
  }
  .arrow-btn:hover  { color: #ccc; background: #2a2a2a; }
  .remove-btn:hover { color: #eb5757; background: #1a0d0d; }

  .arrow-spacer {
    display: inline-block;
    width: 1.3em; /* same width as an arrow button */
  }

  .db-preview {
    font-size: 0.7rem;
    white-space: nowrap;
    flex-shrink: 0;
    min-width: 8rem;
    text-align: right;
  }

  .prev-spin { color: #666; }
  .prev-ok   { color: #4ec994; }
  .prev-none { color: #eb5757; }
  .prev-err  { color: #c8832a; cursor: help; }

  /* ── footer ── */
  .db-footer {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
    padding-top: 0.2rem;
  }

  .add-btn {
    padding: 0.3em 0.8em;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    background: #252525;
    color: #ccc;
    font-size: 0.78rem;
    cursor: pointer;
    transition: border-color 0.12s;
  }
  .add-btn:hover { border-color: #6c9ef8; color: #6c9ef8; }

  .clear-btn {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.72rem;
    color: #555;
    cursor: pointer;
  }
  .clear-btn:hover { color: #eb5757; text-decoration: underline; }

  /* ── action row ── */
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.1rem;
    flex-shrink: 0;
  }

  .btn-ghost {
    padding: 0.35em 1em;
    border-radius: 5px;
    font-size: 0.82rem;
    cursor: pointer;
    background: transparent;
    border: 1px solid #3a3a3a;
    color: #aaa;
    transition: border-color 0.12s;
  }
  .btn-ghost:hover { border-color: #666; color: #ccc; }
</style>
