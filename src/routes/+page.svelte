<script lang="ts">
  import { open as openDialog } from "@tauri-apps/plugin-dialog";
  import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
  import { Menu, Submenu, MenuItem, PredefinedMenuItem } from "@tauri-apps/api/menu";
  import { onMount } from "svelte";
  import { openFile, getStructure, closeSession } from "$lib/rpc";
  import type { Metadata, GroupInfo } from "$lib/rpc";
  import MetadataPanel from "$lib/components/MetadataPanel.svelte";
  import SignalTree from "$lib/components/SignalTree.svelte";
  import ExportDialog from "$lib/components/ExportDialog.svelte";
  import AboutDialog from "$lib/components/AboutDialog.svelte";
  import Toolbar from "$lib/components/Toolbar.svelte";

  // ── state ─────────────────────────────────────────────────────────────── //
  type Phase = "idle" | "loading" | "loaded" | "error";
  let phase: Phase              = $state("idle");
  let errorMsg: string          = $state("");
  let metadata: Metadata | null = $state(null);
  let groups: GroupInfo[]       = $state([]);
  let sessionId: string | null  = $state(null);
  let dragging: boolean         = $state(false);
  let showExport: boolean       = $state(false);
  let showAbout: boolean        = $state(false);

  // ── signal tree controls (driven from status bar) ─────────────────────── //
  let showEmptyGroups: boolean              = $state(false);
  let treeExpanded: Record<number, boolean> = $state({});

  function expandAll()   { treeExpanded = Object.fromEntries(groups.map((g) => [g.index, true])); }
  function collapseAll() { treeExpanded = {}; }

  // counts for status bar and metadata panel
  const emptyGroupCount      = $derived(groups.filter((g) => g.channels.length === 0).length);
  const totalChannelCount    = $derived(groups.reduce((n, g) => n + g.channels.length, 0));
  const physicalSignalCount  = $derived(
    groups.filter((g) => !g.is_bus_raw).reduce((n, g) => n + g.channels.length, 0),
  );

  // Native menu items we need to update at runtime
  let exportMenuItem: Awaited<ReturnType<typeof MenuItem.new>> | null = null;

  // ── window title ──────────────────────────────────────────────────────── //
  const APP_TITLE = "mf4 utility";

  async function setWindowTitle(fileName?: string) {
    const win = getCurrentWebviewWindow();
    await win.setTitle(fileName ? `${fileName} — ${APP_TITLE}` : APP_TITLE);
  }

  // ── file open ─────────────────────────────────────────────────────────── //
  async function loadFile(path: string) {
    if (sessionId) {
      await closeSession(sessionId).catch(() => {});
      sessionId = null;
    }
    phase    = "loading";
    errorMsg = "";
    metadata = null;
    groups   = [];
    try {
      const result  = await openFile(path);
      sessionId = result.session_id;
      metadata  = result.metadata;
      const struct = await getStructure(result.session_id);
      groups = struct.groups;
      phase  = "loaded";
      await setWindowTitle(result.metadata.file_name);
      exportMenuItem?.setEnabled(true);
    } catch (e) {
      errorMsg = String(e);
      phase    = "error";
      await setWindowTitle();
      exportMenuItem?.setEnabled(false);
    }
  }

  async function pickFile() {
    const path = await openDialog({
      multiple: false,
      filters: [{ name: "MF4 / MDF", extensions: ["mf4", "mdf"] }],
    });
    if (path) await loadFile(path as string);
  }

  // ── OS menus ──────────────────────────────────────────────────────────── //
  onMount(() => {
    const win = getCurrentWebviewWindow();

    // ── drag-and-drop (async, store cleanup for later) ──
    let dndCleanup: (() => void) | null = null;
    win.onDragDropEvent((ev) => {
      const t = ev.payload.type;
      if (t === "enter" || t === "over") {
        dragging = true;
      } else if (t === "leave") {
        dragging = false;
      } else if (t === "drop") {
        dragging = false;
        const paths = (ev.payload as unknown as { paths: string[] }).paths ?? [];
        if (paths.length > 0) loadFile(paths[0]);
      }
    }).then((fn) => { dndCleanup = fn; });

    // ── build native menu bar (fire-and-forget async) ──
    (async () => {
      const aboutItem = await MenuItem.new({
        id: "about",
        text: "About mf4u",
        action: () => { showAbout = true; },
      });

      exportMenuItem = await MenuItem.new({
        id: "export",
        text: "Export…",
        accelerator: "CmdOrCtrl+E",
        enabled: false,
        action: () => { if (sessionId) showExport = true; },
      });

      const menu = await Menu.new({
        items: [
          // ① App menu — macOS system menu
          await Submenu.new({
            text: "mf4u",
            items: [
              aboutItem,
              await PredefinedMenuItem.new({ item: "Separator" }),
              await PredefinedMenuItem.new({ item: "Services" }),
              await PredefinedMenuItem.new({ item: "Separator" }),
              await PredefinedMenuItem.new({ item: "Hide" }),
              await PredefinedMenuItem.new({ item: "HideOthers" }),
              await PredefinedMenuItem.new({ item: "ShowAll" }),
              await PredefinedMenuItem.new({ item: "Separator" }),
              await PredefinedMenuItem.new({ item: "Quit" }),
            ],
          }),

          // ② File menu
          await Submenu.new({
            text: "File",
            items: [
              await MenuItem.new({
                id: "open",
                text: "Open…",
                accelerator: "CmdOrCtrl+O",
                action: pickFile,
              }),
              exportMenuItem,
              await PredefinedMenuItem.new({ item: "Separator" }),
              await PredefinedMenuItem.new({ item: "CloseWindow" }),
            ],
          }),

          // ③ Help menu — non-macOS About lives here
          await Submenu.new({
            text: "Help",
            items: [aboutItem],
          }),
        ],
      });

      await menu.setAsAppMenu();
      await setWindowTitle();
    })();

    return () => { dndCleanup?.(); };
  });
</script>

<!-- ── markup ─────────────────────────────────────────────────────────── -->
<div class="app">

  {#if showAbout}
    <AboutDialog open={showAbout} onclose={() => (showAbout = false)} />
  {/if}

  {#if showExport && sessionId}
    <ExportDialog {sessionId} fileName={metadata?.file_name ?? ""} onclose={() => (showExport = false)} />
  {/if}

  <!-- ── icon toolbar ── -->
  <Toolbar
    loading={phase === "loading"}
    hasFile={phase === "loaded" && !!sessionId}
    onopen={pickFile}
    onexport={() => { if (sessionId) showExport = true; }}
  />

  <!-- ── idle / error ── -->
  {#if phase === "idle" || phase === "error"}
    <div class="drop-zone" class:drag-over={dragging} role="button" tabindex="0"
         onclick={pickFile} onkeydown={(e) => e.key === "Enter" && pickFile()}>
      <p class="drop-hint">Drop an <code>.mf4</code> file here or press <kbd>⌘O</kbd></p>
      {#if phase === "error"}
        <p class="error-msg">{errorMsg}</p>
      {/if}
    </div>

  <!-- ── loading ── -->
  {:else if phase === "loading"}
    <div class="drop-zone inert">
      <p class="drop-hint muted">Loading…</p>
    </div>

  <!-- ── loaded ── -->
  {:else if phase === "loaded" && metadata}
    <div class="content">
      <div class="left-pane">
        <MetadataPanel meta={metadata} physicalSignals={physicalSignalCount} />
      </div>
      <div class="right-pane">
        <SignalTree {groups} sessionId={sessionId!}
          {showEmptyGroups} bind:expanded={treeExpanded} />
      </div>
    </div>
  {/if}

  <!-- ── status bar (only when loaded) ── -->
  {#if phase === "loaded"}
    <div class="status-bar">
      <span class="status-info">
        {groups.length} group{groups.length !== 1 ? "s" : ""}
        · {totalChannelCount.toLocaleString()} signal{totalChannelCount !== 1 ? "s" : ""}
        · {physicalSignalCount.toLocaleString()} physical
        {#if emptyGroupCount > 0}
          · <span class="status-dim">{emptyGroupCount} empty group{emptyGroupCount !== 1 ? "s" : ""}</span>
        {/if}
      </span>
      <span class="status-actions">
        {#if emptyGroupCount > 0}
          <button class="status-link" onclick={() => (showEmptyGroups = !showEmptyGroups)}>
            {showEmptyGroups ? "hide empty groups" : "show empty groups"}
          </button>
          <span class="status-sep">·</span>
        {/if}
        <button class="status-link" onclick={expandAll}>expand all</button>
        <span class="status-sep">·</span>
        <button class="status-link" onclick={collapseAll}>collapse all</button>
      </span>
    </div>
  {/if}

</div>

<!-- ── styles ────────────────────────────────────────────────────────── -->
<style>
  :global(:root) {
    font-family: Inter, system-ui, sans-serif;
    font-size: 14px;
    background: #141414;
    color: #e8e8e8;
  }
  :global(body) { margin: 0; }
  :global(*) { box-sizing: border-box; }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  /* ── drop zone ── */
  .drop-zone {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    border: 2px dashed transparent;
    margin: 1.5rem;
    border-radius: 10px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    outline: none;
  }
  .drop-zone:hover:not(.inert),
  .drop-zone:focus:not(.inert) { border-color: #333; background: #1a1a1a; }
  .drag-over                   { border-color: #6c9ef8 !important; background: #1a2030 !important; }
  .inert                       { cursor: default; }

  .drop-hint        { color: #555; font-size: 0.9rem; margin: 0; pointer-events: none; }
  .drop-hint.muted  { color: #444; }
  .drop-hint code   { color: #888; }
  .drop-hint kbd {
    display: inline-block;
    padding: 0.1em 0.4em;
    font-family: inherit;
    font-size: 0.85em;
    border: 1px solid #444;
    border-radius: 4px;
    background: #252525;
    color: #999;
    line-height: 1.4;
  }

  .error-msg {
    color: #eb5757;
    font-size: 0.8rem;
    font-family: monospace;
    max-width: 560px;
    text-align: center;
    white-space: pre-wrap;
    margin: 0;
  }

  /* ── two-pane loaded layout ── */
  .content {
    flex: 1;
    display: grid;
    grid-template-columns: 340px 1fr;
    overflow: hidden;
  }

  .left-pane {
    overflow-y: auto;
    border-right: 1px solid #2a2a2a;
  }

  .right-pane {
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ── status bar ── */
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0 0.9rem;
    height: 22px;
    background: #111;
    border-top: 1px solid #1f1f1f;
    flex-shrink: 0;
    font-size: 0.72rem;
    color: #555;
    user-select: none;
  }

  .status-info { white-space: nowrap; }
  .status-dim  { color: #444; }

  .status-actions {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    white-space: nowrap;
  }

  .status-sep { color: #333; }

  .status-link {
    background: none;
    border: none;
    padding: 0;
    font-size: inherit;
    font-family: inherit;
    color: #555;
    cursor: pointer;
    text-decoration: none;
    transition: color 0.12s;
  }
  .status-link:hover { color: #6c9ef8; text-decoration: underline; }
</style>
