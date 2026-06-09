<script lang="ts">
  import { open as openDialog } from "@tauri-apps/plugin-dialog";
  import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
  import { Menu, Submenu, MenuItem, CheckMenuItem, PredefinedMenuItem } from "@tauri-apps/api/menu";
  import { onMount } from "svelte";
  import { openFile, getStructure, closeSession, saveConfig, loadConfig } from "$lib/rpc";
  import type { Metadata, GroupInfo, DbAssignment, FilteredChannel, AppConfig, ExportFormat, DbcPathMode } from "$lib/rpc";
  import { loadPrefs, savePrefs } from "$lib/prefs";
  import type { AppPrefs } from "$lib/prefs";
  import MetadataPanel from "$lib/components/MetadataPanel.svelte";
  import SignalTree from "$lib/components/SignalTree.svelte";
  import ExportDialog from "$lib/components/ExportDialog.svelte";
  import FrameDecodingDialog from "$lib/components/FrameDecodingDialog.svelte";
  import ChannelFilterDialog from "$lib/components/ChannelFilterDialog.svelte";
  import PreferencesDialog from "$lib/components/PreferencesDialog.svelte";
  import AboutDialog from "$lib/components/AboutDialog.svelte";
  import SaveConfigDialog from "$lib/components/SaveConfigDialog.svelte";
  import Toolbar from "$lib/components/Toolbar.svelte";

  // ── state ─────────────────────────────────────────────────────────────── //
  type Phase = "idle" | "loading" | "loaded" | "error";
  let phase: Phase              = $state("idle");
  let errorMsg: string          = $state("");
  let metadata: Metadata | null = $state(null);
  let groups: GroupInfo[]       = $state([]);
  let sessionId: string | null  = $state(null);
  let dragging: boolean         = $state(false);
  let showExport:        boolean  = $state(false);
  let showAbout:         boolean  = $state(false);
  let showFrameDecoding: boolean  = $state(false);
  let showChannelFilter: boolean  = $state(false);
  let showPreferences:   boolean  = $state(false);
  let showSaveConfig:    boolean  = $state(false);
  let flatten:           boolean  = $state(false);

  // ── App-wide preferences (persisted in localStorage) ──────────────────── //
  let prefs: AppPrefs = $state(loadPrefs());

  // ── Configuration save / load ─────────────────────────────────────────── //
  /** Last export format the user selected; persisted in saved configs. */
  let lastExportFormat: ExportFormat = $state("tdms");
  /** Last directory the user exported into; persisted in saved configs. */
  let lastOutputFolder: string       = $state("");
  /**
   * Config that was loaded before a file was open.  Applied automatically
   * (DBC matching by group name) once the next file finishes loading.
   */
  let pendingConfig: AppConfig | null = $state(null);
  /** Brief toast message ("Saved." / "Loaded." / error) shown for 2 s. */
  let configToast: string = $state("");

  // ── Phase A: frame decoding session config ─────────────────────────────── //
  let decodingConfig: DbAssignment[] = $state([]);
  /** Path of the last file dropped while the FrameDecodingDialog is open. */
  let frameDecodingDropPath: string | null = $state(null);

  // ── Phase B: channel filter session config ─────────────────────────────── //
  /** null = no filter (export everything); array = explicit inclusion list. */
  let selectedSignals: FilteredChannel[] | null = $state(null);

  // ── signal tree controls (driven from status bar) ─────────────────────── //
  let showEmptyGroups:    boolean              = $state(false);
  let showEmptyRecGroups: boolean              = $state(true);
  let treeExpanded: Record<number, boolean> = $state({});

  function expandAll()   { treeExpanded = Object.fromEntries(groups.map((g) => [g.index, true])); }
  function collapseAll() { treeExpanded = {}; }

  // counts for status bar and metadata panel
  const emptyGroupCount      = $derived(groups.filter((g) => g.channels.length === 0).length);
  const emptyRecGroupCount   = $derived(groups.filter((g) => g.channels.length > 0 && g.cycles_nr === 0).length);
  const totalChannelCount    = $derived(groups.reduce((n, g) => n + g.channels.length, 0));
  const physicalSignalCount  = $derived(
    groups.filter((g) => !g.is_bus_raw).reduce((n, g) => n + g.channels.length, 0),
  );

  // Phase A derived
  const hasRawFrameGroups   = $derived(groups.some(g => g.is_bus_raw));
  const decodingActive      = $derived(decodingConfig.length > 0);
  const uniqueDecodingDbs   = $derived(new Set(decodingConfig.map(a => a.db_path)));

  // Phase B derived
  const totalPhysicalSignals = $derived(
    groups.filter(g => !g.is_bus_raw).reduce((n, g) => n + g.channels.length, 0)
  );
  const filterActive  = $derived(selectedSignals !== null);
  const filterCount   = $derived.by(() => selectedSignals !== null ? selectedSignals.length : 0);

  // Keep native menu items in sync with reactive state
  $effect(() => { exportMenuItem?.setEnabled(phase === "loaded" && !!sessionId); });
  $effect(() => { frameDecodingMenuItem?.setEnabled(hasRawFrameGroups); });
  $effect(() => { channelFilterMenuItem?.setEnabled(phase === "loaded" && !!sessionId); });
  $effect(() => { flattenCheckItem?.setChecked(flatten); });
  $effect(() => { flattenCheckItem?.setEnabled(phase === "loaded" && !!sessionId); });

  // Native menu items we need to update at runtime
  let exportMenuItem:         Awaited<ReturnType<typeof MenuItem.new>>      | null = null;
  let frameDecodingMenuItem:  Awaited<ReturnType<typeof MenuItem.new>>      | null = null;
  let channelFilterMenuItem:  Awaited<ReturnType<typeof MenuItem.new>>      | null = null;
  let flattenCheckItem:       Awaited<ReturnType<typeof CheckMenuItem.new>> | null = null;
  let preferencesMenuItem:    Awaited<ReturnType<typeof MenuItem.new>>      | null = null;
  let saveConfigMenuItem:     Awaited<ReturnType<typeof MenuItem.new>>      | null = null;
  let loadConfigMenuItem:     Awaited<ReturnType<typeof MenuItem.new>>      | null = null;

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
    phase          = "loading";
    errorMsg       = "";
    metadata       = null;
    groups         = [];
    decodingConfig  = [];   // reset Phase A config on new file open
    selectedSignals = null; // reset Phase B filter on new file open
    flatten         = false; // reset flatten on new file open
    try {
      const result  = await openFile(path);
      sessionId = result.session_id;
      metadata  = result.metadata;
      const struct = await getStructure(result.session_id);
      groups = struct.groups;
      phase  = "loaded";
      await setWindowTitle(result.metadata.file_name);
      // Apply any config that was loaded before a file was open.
      if (pendingConfig) {
        await applyConfig(pendingConfig);
        pendingConfig = null;
      }
    } catch (e) {
      errorMsg = String(e);
      phase    = "error";
      await setWindowTitle();
    }
  }

  async function pickFile() {
    const path = await openDialog({
      multiple: false,
      filters: [{ name: "MF4 / MDF / BLF", extensions: ["mf4", "mdf", "blf"] }],
    });
    if (path) await loadFile(path as string);
  }

  // ── Config helpers ────────────────────────────────────────────────────── //

  function showToast(msg: string) {
    configToast = msg;
    setTimeout(() => { configToast = ""; }, 2500);
  }

  /**
   * Build a config snapshot from the current UI state.
   * channel_filter is stored as bare signal names (without group_index) so it
   * is portable across structurally similar files.
   */
  function buildConfig(): AppConfig {
    return {
      version:        1,
      decoding:       decodingConfig.map(a => ({
        group_index: a.group_index,
        group_name:  groups[a.group_index]?.acq_name ?? "",
        db_path:     a.db_path,
      })),
      channel_filter: selectedSignals
        ? [...new Set(selectedSignals.map(s => s.channel_name))]
        : null,
      flatten,
      export_format:  lastExportFormat,
      output_folder:  lastOutputFolder,
      mat_link_groups: prefs.matLinkGroups,
      ...(prefs.splitMode !== "none" && {
        split_mode:       prefs.splitMode,
        split_size_mb:    prefs.splitSizeMB,
        split_period_s:   prefs.splitPeriodS,
        split_first_time: prefs.splitFirstTime,
      }),
    };
  }

  /**
   * Apply a loaded config to the current state.
   * - `decoding`: matched by group name, falling back to group index.
   *   DBC paths that don't exist on disk are silently skipped.
   * - `channel_filter`: signal names matched across all groups.
   * - All other fields applied directly.
   * When called with no file open the decoding and filter parts of the config
   * are stored as `pendingConfig` for the next file open.
   */
  async function applyConfig(cfg: AppConfig) {
    if (cfg.flatten       !== undefined) flatten          = cfg.flatten;
    if (cfg.export_format !== undefined) lastExportFormat = cfg.export_format as ExportFormat;
    if (cfg.output_folder !== undefined) lastOutputFolder = cfg.output_folder;
    if (cfg.mat_link_groups !== undefined) {
      prefs = { ...prefs, matLinkGroups: cfg.mat_link_groups };
      savePrefs(prefs);
    }
    if (cfg.split_mode !== undefined) {
      prefs = {
        ...prefs,
        splitMode:      cfg.split_mode,
        ...(cfg.split_size_mb   !== undefined && { splitSizeMB:   cfg.split_size_mb }),
        ...(cfg.split_period_s  !== undefined && { splitPeriodS:  cfg.split_period_s }),
        ...(cfg.split_first_time !== undefined && { splitFirstTime: cfg.split_first_time }),
      };
      savePrefs(prefs);
    }

    if (phase !== "loaded" || groups.length === 0) {
      // Store the structural parts for when a file is opened.
      pendingConfig = cfg;
      return;
    }

    // ── DBC assignments ──────────────────────────────────────────────────── //
    if (cfg.decoding && cfg.decoding.length > 0) {
      const newDecoding: DbAssignment[] = [];
      for (const d of cfg.decoding) {
        // Try name match first, fall back to index.
        let idx = groups.findIndex(g => g.acq_name === d.group_name);
        if (idx === -1 && d.group_index < groups.length) idx = d.group_index;
        if (idx < 0 || idx >= groups.length) continue;
        // Avoid duplicate (same group + same db).
        if (!newDecoding.some(a => a.group_index === idx && a.db_path === d.db_path)) {
          newDecoding.push({ group_index: idx, db_path: d.db_path });
        }
      }
      decodingConfig   = newDecoding;
      selectedSignals  = null;  // filter is recomputed below from cfg.channel_filter
    }

    // ── Channel filter ───────────────────────────────────────────────────── //
    if (cfg.channel_filter === null) {
      selectedSignals = null;
    } else if (cfg.channel_filter && cfg.channel_filter.length > 0) {
      const nameSet = new Set(cfg.channel_filter);
      const matched: FilteredChannel[] = [];
      for (const g of groups) {
        for (const ch of g.channels) {
          if (nameSet.has(ch.name)) {
            matched.push({
              group_index:  g.index,
              channel_name: ch.name,
              acq_name:     g.acq_name,
              unit:         ch.unit,
              source:       "physical",
            });
          }
        }
      }
      selectedSignals = matched.length > 0 ? matched : null;
    }
  }

  /**
   * Convert the stored absolute first-split datetime (prefs.splitFirstTime) to a
   * seconds offset relative to the open file's start_time.
   * Returns 0 when no first-split time is set or when the file has no start_time.
   */
  function computeSplitFirstOffsetS(): number {
    if (!prefs.splitFirstTime || !metadata?.start_time) return 0;
    try {
      const splitMs = new Date(prefs.splitFirstTime).getTime();
      const startMs = new Date(metadata.start_time).getTime();
      return Math.max(0, (splitMs - startMs) / 1000);
    } catch {
      return 0;
    }
  }

  function doSaveConfig() {
    showSaveConfig = true;
  }

  async function handleSaveConfig(path: string, mode: DbcPathMode) {
    showSaveConfig = false;
    try {
      await saveConfig(path, buildConfig(), mode);
      showToast("Configuration saved.");
    } catch (e) {
      showToast(`Save failed: ${e}`);
    }
  }

  async function doLoadConfig() {
    const path = await openDialog({
      multiple: false,
      filters: [{ name: "mf4u config", extensions: ["mf4u"] }],
    });
    if (!path) return;
    try {
      const cfg = await loadConfig(path as string);
      await applyConfig(cfg);
      showToast(phase === "loaded" ? "Configuration applied." : "Configuration loaded — will apply on next file open.");
    } catch (e) {
      showToast(`Load failed: ${e}`);
    }
  }

  // ── OS menus ──────────────────────────────────────────────────────────── //
  onMount(() => {
    const win = getCurrentWebviewWindow();

    // ── drag-and-drop (async, store cleanup for later) ──
    let dndCleanup: (() => void) | null = null;
    win.onDragDropEvent((ev) => {
      const t = ev.payload.type;
      if (t === "enter" || t === "over") {
        // Suppress the main drop-zone highlight while the frame decoding dialog
        // is open — the dialog handles its own visual feedback.
        if (!showFrameDecoding) dragging = true;
      } else if (t === "leave") {
        dragging = false;
      } else if (t === "drop") {
        dragging = false;
        const paths = (ev.payload as unknown as { paths: string[] }).paths ?? [];
        if (paths.length > 0) {
          if (showFrameDecoding) {
            // Route the drop to the frame decoding dialog instead of opening as MF4.
            frameDecodingDropPath = paths[0];
          } else {
            loadFile(paths[0]);
          }
        }
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

      frameDecodingMenuItem = await MenuItem.new({
        id: "frame_decoding",
        text: "Configure frame decoding…",
        enabled: false,
        action: () => { if (sessionId) showFrameDecoding = true; },
      });

      channelFilterMenuItem = await MenuItem.new({
        id: "channel_filter",
        text: "Configure channel filter…",
        enabled: false,
        action: () => { if (sessionId) showChannelFilter = true; },
      });

      flattenCheckItem = await CheckMenuItem.new({
        id: "flatten",
        text: "Flatten output",
        checked: false,
        enabled: false,
        action: () => { flatten = !flatten; },
      });

      preferencesMenuItem = await MenuItem.new({
        id: "preferences",
        text: "Preferences…",
        accelerator: "CmdOrCtrl+,",
        action: () => { showPreferences = true; },
      });

      saveConfigMenuItem = await MenuItem.new({
        id: "save_config",
        text: "Save configuration…",
        accelerator: "CmdOrCtrl+Shift+S",
        action: doSaveConfig,
      });

      loadConfigMenuItem = await MenuItem.new({
        id: "load_config",
        text: "Load configuration…",
        accelerator: "CmdOrCtrl+Shift+O",
        action: doLoadConfig,
      });

      const menu = await Menu.new({
        items: [
          // ① App menu — macOS system menu
          await Submenu.new({
            text: "mf4u",
            items: [
              aboutItem,
              await PredefinedMenuItem.new({ item: "Separator" }),
              preferencesMenuItem,
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
              await PredefinedMenuItem.new({ item: "Separator" }),
              saveConfigMenuItem,
              loadConfigMenuItem,
              await PredefinedMenuItem.new({ item: "Separator" }),
              await PredefinedMenuItem.new({ item: "CloseWindow" }),
            ],
          }),

          // ③ Export menu (v0.2.0+)
          await Submenu.new({
            text: "Export",
            items: [
              frameDecodingMenuItem,
              channelFilterMenuItem,
              flattenCheckItem,
              await PredefinedMenuItem.new({ item: "Separator" }),
              exportMenuItem,
            ],
          }),

          // ④ Help menu — non-macOS About lives here
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

  {#if showSaveConfig}
    <SaveConfigDialog
      onconfirm={handleSaveConfig}
      oncancel={() => { showSaveConfig = false; }}
    />
  {/if}

  {#if showPreferences}
    <PreferencesDialog
      {prefs}
      fileStartTime={metadata?.start_time ?? null}
      fileEndTime={metadata?.end_time ?? null}
      onchange={(p) => { prefs = p; }}
      onclose={() => (showPreferences = false)}
    />
  {/if}

  {#if showExport && sessionId}
    <ExportDialog
      {sessionId}
      fileName={metadata?.file_name ?? ""}
      dbAssignments={decodingConfig}
      {flatten}
      matLinkGroups={prefs.matLinkGroups}
      signalFilter={selectedSignals}
      totalSignals={totalPhysicalSignals}
      initialFormat={lastExportFormat}
      initialFolder={lastOutputFolder}
      splitMode={prefs.splitMode}
      splitSizeMB={prefs.splitSizeMB}
      splitPeriodS={prefs.splitPeriodS}
      splitFirstTime={prefs.splitFirstTime}
      splitFirstOffsetS={computeSplitFirstOffsetS()}
      onfmtchange={(fmt) => { lastExportFormat = fmt; }}
      onfolderchange={(folder) => { lastOutputFolder = folder; }}
      onclose={() => (showExport = false)}
    />
  {/if}

  {#if showFrameDecoding && sessionId}
    <FrameDecodingDialog
      {groups}
      {sessionId}
      dbAssignments={decodingConfig}
      onchange={(cfg) => { decodingConfig = cfg; selectedSignals = null; }}
      onclose={() => (showFrameDecoding = false)}
      externalDropPath={frameDecodingDropPath}
      onclearexternaldrop={() => { frameDecodingDropPath = null; }}
    />
  {/if}

  {#if showChannelFilter && sessionId}
    <ChannelFilterDialog
      {groups}
      {sessionId}
      dbAssignments={decodingConfig}
      selectedSignals={selectedSignals}
      onchange={(sigs) => { selectedSignals = sigs; }}
      onclose={() => (showChannelFilter = false)}
    />
  {/if}

  <!-- ── icon toolbar ── -->
  <Toolbar
    loading={phase === "loading"}
    hasFile={phase === "loaded" && !!sessionId}
    hasRawFrameGroups={hasRawFrameGroups}
    decodingActive={decodingActive}
    decodingDbCount={uniqueDecodingDbs.size}
    {filterActive}
    {filterCount}
    {flatten}
    onopen={pickFile}
    onsaveconfig={doSaveConfig}
    onloadconfig={doLoadConfig}
    onexport={() => { if (sessionId) showExport = true; }}
    onframedecoding={() => { if (sessionId) showFrameDecoding = true; }}
    onchannelfilter={() => { if (sessionId) showChannelFilter = true; }}
    onflattentoggle={() => { flatten = !flatten; }}
    onpreferences={() => { showPreferences = true; }}
  />

  <!-- ── idle / error ── -->
  {#if phase === "idle" || phase === "error"}
    <div class="drop-zone" class:drag-over={dragging} role="button" tabindex="0"
         onclick={pickFile} onkeydown={(e) => e.key === "Enter" && pickFile()}>
      <p class="drop-hint">Drop an <code>.mf4</code> or <code>.blf</code> file here or press <kbd>⌘O</kbd></p>
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
          {showEmptyGroups} {showEmptyRecGroups} bind:expanded={treeExpanded} />
      </div>
    </div>
  {/if}

  <!-- ── config toast ── -->
  {#if configToast}
    <div class="config-toast" role="status" aria-live="polite">{configToast}</div>
  {/if}

  <!-- ── status bar (only when loaded) ── -->
  {#if phase === "loaded"}
    <div class="status-bar">
      <span class="status-info">
        {groups.length} group{groups.length !== 1 ? "s" : ""}
        · {totalChannelCount.toLocaleString()} signal{totalChannelCount !== 1 ? "s" : ""}
        · {physicalSignalCount.toLocaleString()} physical
        {#if emptyGroupCount > 0}
          · <span class="status-dim">{emptyGroupCount} empty sig group{emptyGroupCount !== 1 ? "s" : ""}</span>
        {/if}
        {#if emptyRecGroupCount > 0}
          · <span class="status-dim">{emptyRecGroupCount} empty rec group{emptyRecGroupCount !== 1 ? "s" : ""}</span>
        {/if}
      </span>
      <span class="status-actions">
        {#if emptyGroupCount > 0}
          <button class="status-link" onclick={() => (showEmptyGroups = !showEmptyGroups)}>
            {showEmptyGroups ? "hide empty sig groups" : "show empty sig groups"}
          </button>
          <span class="status-sep">·</span>
        {/if}
        {#if emptyRecGroupCount > 0}
          <button class="status-link" onclick={() => (showEmptyRecGroups = !showEmptyRecGroups)}>
            {showEmptyRecGroups ? "hide empty rec groups" : "show empty rec groups"}
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

  /* ── config toast ── */
  .config-toast {
    position: fixed;
    bottom: 2.4rem;   /* just above the status bar */
    left: 50%;
    transform: translateX(-50%);
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 0.35rem 0.9rem;
    font-size: 12px;
    color: #c8c8c8;
    pointer-events: none;
    white-space: nowrap;
    z-index: 9999;
  }
</style>
