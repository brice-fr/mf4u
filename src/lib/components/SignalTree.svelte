<script lang="ts">
  import type { GroupInfo, ChannelStats } from "$lib/rpc";
  import { getSignalStats, formatNum } from "$lib/rpc";
  import { busColor } from "$lib/busColors";

  let {
    groups,
    sessionId,
    showEmptyGroups = true,
    expanded        = $bindable({} as Record<number, boolean>),
  }: {
    groups:           GroupInfo[];
    sessionId:        string;
    showEmptyGroups?: boolean;
    expanded?:        Record<number, boolean>;
  } = $props();

  // ── per-channel stats cache  {groupIndex:channelName → ChannelStats | "loading" | string} //
  type StatsValue = ChannelStats | "loading" | string; // string = error message
  let statsCache: Record<string, StatsValue> = $state({});

  function key(groupIndex: number, name: string) {
    return `${groupIndex}::${name}`;
  }

  function toggle(i: number) {
    expanded[i] = !expanded[i];
  }

  async function loadStats(groupIndex: number, channelName: string) {
    const k = key(groupIndex, channelName);
    if (statsCache[k]) return; // already loaded or in progress
    statsCache[k] = "loading";
    try {
      const s = await getSignalStats(sessionId, groupIndex, channelName);
      statsCache[k] = s;
    } catch (e) {
      statsCache[k] = String(e);
    }
  }

  function statsText(groupIndex: number, name: string): string {
    const v = statsCache[key(groupIndex, name)];
    if (!v) return "";
    if (v === "loading") return "…";
    if (typeof v === "string") return `⚠ ${v}`;
    const s = v as ChannelStats;
    const parts = [`n=${s.samples.toLocaleString()}`];
    if (s.min !== undefined) parts.push(`min=${formatNum(s.min)}`);
    if (s.max !== undefined) parts.push(`max=${formatNum(s.max)}`);
    if (s.mean !== undefined) parts.push(`μ=${formatNum(s.mean)}`);
    return parts.join("  ");
  }

  // ── filter ────────────────────────────────────────────────────────────── //
  let filterText: string = $state("");
  const filtered = $derived.by(() => {
    // Start from all groups, optionally hiding empty ones
    let base = showEmptyGroups ? groups : groups.filter((g) => g.channels.length > 0);
    // Apply text filter (also removes groups with no matching channels)
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      base = base
        .map((g) => ({ ...g, channels: g.channels.filter((c) => c.name.toLowerCase().includes(q)) }))
        .filter((g) => g.channels.length > 0);
    }
    return base;
  });
</script>

<div class="tree-root">
  <div class="tree-toolbar">
    <input
      class="filter-input"
      type="search"
      placeholder="Filter signals…"
      bind:value={filterText}
    />
    <span class="summary">
      {groups.length} group{groups.length !== 1 ? "s" : ""}
      · {groups.reduce((n, g) => n + g.channels.length, 0).toLocaleString()} signals
    </span>
  </div>

  <div class="tree-body">
    {#each filtered as group (group.index)}
      <!-- ── group row ── -->
      <button class="group-row" onclick={() => toggle(group.index)}>
        <span class="chevron">{expanded[group.index] ? "▾" : "▸"}</span>
        <span class="group-name">{group.acq_name}</span>
        {#if group.bus_type}
          {@const c = busColor(group.bus_type)}
          <span class="badge bus-label"
                style="color:{c.text}; background:{c.bg}; border-color:{c.border}">
            {group.bus_type}
          </span>
          <span class="badge frames-label">raw frames</span>
        {:else if group.has_phy}
          <span class="badge phy-badge">phy</span>
        {/if}
        {#if group.compression === "zipped" || group.compression === "transposed-zipped"}
          <span class="badge comp-badge" title={group.compression}>
            {group.compression === "transposed-zipped" ? "t-zip" : "zip"}
          </span>
        {/if}
        <span class="group-count">{group.channels.length}</span>
      </button>

      <!-- ── channel rows (visible when expanded) ── -->
      {#if expanded[group.index]}
        <div class="channel-block">
          {#each group.channels as ch (ch.name)}
            <div class="channel-row">
              <span class="ch-name" title={ch.comment || ch.name}>{ch.name}</span>
              <span class="phy-slot">
                {#if ch.is_phy}<span class="badge phy-badge">phy</span>{/if}
              </span>
              <span class="ch-unit">{ch.unit || ""}</span>
              <span class="ch-stats">{statsText(group.index, ch.name)}</span>
              {#if !statsCache[key(group.index, ch.name)]}
                <button
                  class="stats-btn"
                  onclick={() => loadStats(group.index, ch.name)}
                  title="Load statistics"
                >stats</button>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    {/each}

    {#if filtered.length === 0}
      <p class="empty">No signals match "{filterText}"</p>
    {/if}
  </div>
</div>

<style>
  .tree-root {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    font-size: 0.82rem;
  }

  /* ── toolbar ── */
  .tree-toolbar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.55rem 0.9rem;
    border-bottom: 1px solid #2a2a2a;
    flex-shrink: 0;
  }

  .filter-input {
    flex: 1;
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 4px;
    color: #e8e8e8;
    font-size: 0.8rem;
    padding: 0.25em 0.6em;
    outline: none;
  }
  .filter-input:focus { border-color: #555; }

  .summary {
    color: #555;
    font-size: 0.75rem;
    white-space: nowrap;
  }

  /* ── scrollable body ── */
  .tree-body {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
  }

  /* ── group row ── */
  .group-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.35rem 0.9rem;
    background: none;
    border: none;
    border-bottom: 1px solid #1f1f1f;
    color: #ccc;
    cursor: pointer;
    text-align: left;
    font-size: 0.82rem;
  }
  .group-row:hover { background: #1e1e1e; }

  .chevron    { color: #555; font-size: 0.7rem; width: 0.8rem; flex-shrink: 0; }
  .group-name { flex: 1; font-weight: 500; color: #ddd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* bus type badge — colours injected via inline style from busColors.ts */
  .badge.bus-label {
    font-size: 0.65rem; padding: 0.1em 0.45em; border-radius: 3px;
    border: 1px solid; /* colour set by inline style */
    white-space: nowrap; flex-shrink: 0; font-weight: 600;
  }

  /* "raw frames" badge — muted, provides context without competing */
  .badge.frames-label {
    font-size: 0.65rem; padding: 0.1em 0.45em; border-radius: 3px;
    background: #1a1a1a; color: #4a4a4a; border: 1px solid #2a2a2a;
    white-space: nowrap; flex-shrink: 0;
  }

  /* "phy" badge — red, used on both group rows and channel rows */
  .badge.phy-badge {
    font-size: 0.65rem; padding: 0.1em 0.45em; border-radius: 3px;
    background: #280d0d; color: #f07575; border: 1px solid #401515;
    white-space: nowrap; flex-shrink: 0;
  }

  /* "zip" / "t-zip" badge — blue-grey, indicates compressed DG data */
  .badge.comp-badge {
    font-size: 0.65rem; padding: 0.1em 0.45em; border-radius: 3px;
    background: #0d1f28; color: #5ab4d8; border: 1px solid #1a3a4a;
    white-space: nowrap; flex-shrink: 0;
  }

  /* 4ch = exactly 4 tabular digits; right-aligned so 1- to 4-digit counts stack cleanly */
  .group-count { color: #555; font-size: 0.75rem; flex-shrink: 0; width: 4ch; text-align: right; font-variant-numeric: tabular-nums; }

  /* ── channel block ── */
  .channel-block {
    background: #111;
    border-bottom: 1px solid #1f1f1f;
  }

  .channel-row {
    display: grid;
    grid-template-columns: 1fr 2.4rem 5rem 1fr auto;
    /* name | phy-slot | unit | stats | stats-btn */
    align-items: center;
    gap: 0.5rem;
    padding: 0.22rem 0.9rem 0.22rem 2rem;
    border-bottom: 1px solid #1a1a1a;
  }
  .channel-row:hover { background: #161616; }

  .ch-name  { color: #bbb; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .phy-slot { display: flex; align-items: center; justify-content: center; }

  .ch-unit  { color: #666; font-size: 0.75rem; text-align: right; }
  .ch-stats { color: #6c9ef8; font-size: 0.75rem; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .stats-btn {
    font-size: 0.7rem;
    padding: 0.15em 0.5em;
    border: 1px solid #333;
    border-radius: 3px;
    background: transparent;
    color: #666;
    cursor: pointer;
    white-space: nowrap;
  }
  .stats-btn:hover { border-color: #6c9ef8; color: #6c9ef8; }

  .empty {
    color: #555;
    font-size: 0.8rem;
    padding: 1.5rem;
    text-align: center;
    margin: 0;
  }
</style>
