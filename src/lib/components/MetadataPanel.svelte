<script lang="ts">
  import type { Metadata } from "$lib/rpc";
  import { formatBytes, formatDuration, formatDateTime } from "$lib/rpc";
  import { busColor } from "$lib/busColors";

  let {
    meta,
    physicalSignals = undefined,
  }: {
    meta: Metadata;
    physicalSignals?: number;
  } = $props();

  type Row = { label: string; value: string | number };

  function row(label: string, value: string | number | null | undefined): Row {
    return { label, value: (value ?? "—") as string | number };
  }

  const groups = $derived([
    {
      title: "File",
      rows: [
        row("File",        meta.file_name),
        row("Size",        formatBytes(meta.file_size)),
        row("MDF version", meta.version),
      ],
    },
    {
      title: "Timing",
      rows: [
        row("Start",    formatDateTime(meta.start_time)),
        row("End",      formatDateTime(meta.end_time)),
        row("Duration", meta.duration_s != null ? formatDuration(meta.duration_s) : null),
      ],
    },
    {
      title: "Structure",
      rows: [
        row("Total channel groups",  meta.num_channel_groups),
        row("Non-empty groups",      meta.num_nonempty_channel_groups),
        row("Total signals",         meta.num_channels),
        row("Physical signals",      physicalSignals),
      ],
    },
  ]);

  // Recording card — only shown when at least one HD text field is present
  const recordingRows = $derived(
    (["author", "subject", "project", "department"] as const)
      .map((k) => ({ label: k.charAt(0).toUpperCase() + k.slice(1), value: meta[k] }))
      .filter((r) => r.value),
  );

  // Ordered display list for bus frame counts — only types present in the file
  const BUS_ORDER = ["CAN", "CAN FD", "LIN", "MOST", "FlexRay", "Ethernet", "K-Line", "USB"];
  const busRows = $derived(
    BUS_ORDER
      .filter((t) => (meta.bus_frame_counts?.[t] ?? 0) > 0)
      .map((t) => ({
        type: t,
        count: meta.bus_frame_counts[t],
      })),
  );
</script>

<section class="panel">
  <!-- info cards -->
  {#each groups as grp}
    <div class="group">
      <h3>{grp.title}</h3>
      <dl>
        {#each grp.rows as { label, value }}
          <dt>{label}</dt>
          <dd>{value}</dd>
        {/each}
      </dl>
    </div>
  {/each}

  <!-- recording info — author / subject / project / department -->
  {#if recordingRows.length > 0}
    <div class="group">
      <h3>Recording</h3>
      <dl>
        {#each recordingRows as { label, value }}
          <dt>{label}</dt>
          <dd title={value}>{value}</dd>
        {/each}
      </dl>
    </div>
  {/if}

  <!-- bus frames — one row per detected type -->
  {#if busRows.length > 0}
    <div class="group">
      <h3>Bus Frames</h3>
      <dl>
        {#each busRows as { type, count }}
          <dt class="bus-type" style="color: {busColor(type).text}">{type}</dt>
          <dd>{count} group{count !== 1 ? "s" : ""}</dd>
        {/each}
      </dl>
    </div>
  {/if}

  <!-- attachments (compact inline list) -->
  {#if meta.attachments.length > 0}
    <div class="group">
      <h3>Attachments ({meta.attachments.length})</h3>
      <ul class="attach-list">
        {#each meta.attachments as name}
          <li title={name}>{name}</li>
        {/each}
      </ul>
    </div>
  {/if}

  <!-- comment — full-width, scrollable pre -->
  {#if meta.comment}
    <div class="group comment-card">
      <h3>Comment</h3>
      <pre class="comment-pre">{meta.comment}</pre>
    </div>
  {/if}
</section>

<style>
  .panel {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 0.85rem;
    padding: 0.85rem;
    align-items: start;
  }

  .group {
    background: #1e1e1e;
    border: 1px solid #2e2e2e;
    border-radius: 7px;
    padding: 0.75rem 0.9rem;
    min-width: 0;
  }

  h3 {
    margin: 0 0 0.5rem;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #666;
  }

  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    column-gap: 0.65rem;
    row-gap: 0.28rem;
    margin: 0;
  }

  dt { color: #777; font-size: 0.8rem; white-space: nowrap; }
  .bus-type { font-weight: 500; /* colour injected via inline style from busColors.ts */ }
  dd { color: #ddd; font-size: 0.8rem; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .attach-list {
    margin: 0;
    padding-left: 1rem;
    font-size: 0.8rem;
    color: #bbb;
    line-height: 1.6;
  }
  .attach-list li {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ── comment: spans all columns, fixed height, both scroll axes ── */
  .comment-card {
    grid-column: 1 / -1;
  }

  .comment-pre {
    margin: 0;
    font-size: 0.78rem;
    font-family: "SF Mono", "Fira Code", monospace;
    color: #aaa;
    background: #161616;
    border: 1px solid #282828;
    border-radius: 4px;
    padding: 0.55rem 0.7rem;
    max-height: 140px;
    overflow: auto;          /* both axes */
    overflow-x: auto;
    white-space: pre;        /* keep newlines; horizontal scroll for long lines */
    line-height: 1.5;
  }
</style>
