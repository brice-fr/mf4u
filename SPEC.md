# mf4u — Specification

**v0.1.0** released 2026-04-19 · **v0.2.0** in development
**Target platforms:** macOS (arm64 + x86_64), Windows (x86_64). Linux buildable as side-effect but not officially supported.

---

## 1. Overview

mf4u is a desktop GUI tool that opens ASAM MDF 4.x (`.mf4`, `.mdf`) measurement files — primarily produced by automotive data loggers (Vector VN, CSS Electronics CANedge, ETAS INCA, dSPACE, etc.) — and presents a fast, read-only inspection view of the file's contents. It offers export of signal data to multiple formats for downstream analysis, with opt-in bus decoding, signal filtering, and time-merged flattening.

---

## 2. Goals & Non-goals

### Goals (v0.1.0) ✅

- Open `.mf4` / `.mdf` files up to ~2 GB in well under a second (metadata-only parse, no signal load).
- Display file-level metadata:
  - MDF version (e.g. `4.10`, `4.20`)
  - File size, internal start/end time, duration
  - Measurement comment, author, subject, project, department (parsed from HD block XML or plain text; handles MDF4 `<HDcomment>` and ETAS INCA `<common_properties>` formats)
  - Data groups count, non-empty channel groups count, total signals (channels) count
  - Presence of bus-logging raw frames (CAN / CAN FD / LIN / FlexRay / Ethernet / MOST) vs. decoded signal groups
  - Attachments list (embedded files, if any)
  - Compression state per data group (uncompressed / zipped / transposed-zipped)
- Display per-signal statistics on demand (lazily loaded, only when user expands a group):
  - Name, unit, description, source, data type, samples count
  - min / max / mean (numeric channels only)
  - First/last timestamp
- Export the complete measurement to:
  - `.mat` (MATLAB, HDF5-compatible) — via `scipy.io.savemat`
  - `.tdms` — via `npTDMS` `TdmsWriter`, one group per channel group
  - `.parquet` — via `pyarrow`, one file per channel group (single-group files: exact output path)
  - `.csv` — one file per channel group, header + one row per sample
  - `.tsv` — same as CSV with tab delimiter
  - `.xlsx` — single workbook, one worksheet per channel group, via `openpyxl`
- Export default filename derived from the open MF4 file name (extension stripped).
- Progress reporting + cancellation for any long-running export (polled at 400 ms intervals).

### Goals (v0.2.0) — in development

#### A. Frame decoding via external bus description files

- Load one or more `.dbc` or `.arxml` bus description files and assign them (in user-defined priority order) to raw-frame channel groups in the open file.
- On export, `asammdf.MDF.extract_bus_logging()` decodes the assigned raw groups into named physical signals. Raw frames that match no message in any assigned DB are omitted from the output.
- A live preview badge on each assigned DB shows matched message count and decoded signal count before exporting (lightweight RPC scan — no full decode).
- Configuration is **session-level state** set via a dedicated dialog at any time before export; it persists until the file is closed or changed.

#### B. Channel filter

- A dual-panel signal picker (available ↔ to export) lets the user select exactly which signals to include in the export.
- The available list is pre-populated immediately from the existing `get_structure` data (physical signals only, no RPC needed on open).
- A **"Preview decoded channels"** button — active only when at least one DB assignment exists — fires `get_exportable_signals` and enriches the list with signals that would result from decoding, shown with a "decoded" badge.
- Add, Remove, Add All, Remove All buttons act on whatever is highlighted on each side; a live search box filters the available list.
- Default state: all signals selected (no filter active). Removing all filters resets to "export everything".
- Configuration is session-level state, set via a dedicated dialog.

#### C. Flatten output (time-merged table)

- An opt-in toggle that changes the export shape from *one table per group* to *one single time-ordered table*.
- The master timestamp column is the **union** of all selected groups' timestamps, sorted ascending.
- Cells are filled only when the signal's group has a record at that exact timestamp; all other rows are left as `NaN` (MAT), `null` (Parquet), or an empty cell/string (XLSX / CSV / TSV). No interpolation.
- Because the output is always a single table, per-group multi-file splitting no longer applies.
- **Not available for TDMS or MF4** — those formats require synchronised channels within a group and have no native sparse/null-per-sample representation. The toggle is disabled when either format is selected, with an explanatory tooltip.
- A client-side memory estimate (`total_samples × total_selected_channels × 8 bytes`) is shown before exporting; a warning badge appears when the estimate exceeds 500 MB.
- Configuration is session-level state (a single boolean toggle).

#### D. MF4 re-export

- Export back to `.mf4` with the original HD-block metadata preserved (timestamps, author, comment, etc.) but with frame decoding (feature A) and/or channel filtering (feature B) applied.
- Implemented via `asammdf.MDF.extract_bus_logging()` for decoding and `asammdf.MDF.filter(channel_names)` for channel selection, followed by `MDF.save(path)`.
- Progress is reported as a single indeterminate step (total = 1) since `MDF.save()` does not expose a per-group callback.
- Flatten (feature C) is **not supported** for MF4 (same reason as TDMS above).

### Non-goals

- Signal plotting / time-series visualization.
- Editing the MF4 file in-place.
- `.tdm` (legacy NI) export — would require the proprietary NI DataPlugin, effectively Windows-only. `.tdms` is the modern NI format and round-trips losslessly in DIAdem / LabVIEW.
- MDF 3.x explicit support — the library opens them; we just don't test/market it.
- Batch-mode CLI, file diff view, side-by-side session comparison (v3+ candidates).

---

## 3. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Shell | **Tauri 2** | Native webview, small binary (~10 MB), signed/notarized builds on macOS and Windows, mature sidecar process API. |
| UI framework | **SvelteKit** (SPA mode, `@sveltejs/adapter-static`) | Concise reactive components; great for tree/table-heavy UIs. |
| UI language | **TypeScript** | Type-safe Tauri command bindings, typed RPC interfaces. |
| Tauri ↔ UI IPC | Tauri commands (JSON) | Standard; progress polled via `get_export_progress` RPC. |
| MF4 parsing engine | **Python 3.10+ + `asammdf` 8.x** packaged via **PyInstaller** as a Tauri **sidecar binary** | `asammdf` is the only production-grade, fully-featured MDF 4.x library. Rust crates cover only a subset of blocks and lack raw bus-frame handling. |
| Tauri ↔ Python IPC | **JSON-RPC 2.0 over stdio** (line-delimited) | Simple, no extra port, easy to unit-test the Python side alone. |
| `.mat` export | `scipy.io.savemat` with `do_compression=True` | Direct scipy API; channel names sanitised to MATLAB-safe variable names. |
| `.tdms` export | `npTDMS` `TdmsWriter` | Pure-Python, cross-platform, writes the canonical TDMS 2.0 layout. |
| `.parquet` export | `pyarrow.parquet.write_table` with Snappy compression | Columnar format; timestamps as float64 first column. |
| `.csv` / `.tsv` export | Python stdlib `csv` module | No extra dependency; one file per channel group for multi-group files. |
| `.xlsx` export | `openpyxl` write-only workbook | One sheet per channel group; respects Excel sheet-name length and character rules. |
| `.mf4` re-export *(v0.2.0)* | `asammdf.MDF.filter()` + `MDF.save()` | Native round-trip; preserves all HD-block metadata. |
| Bus decoding *(v0.2.0)* | `asammdf.MDF.extract_bus_logging()` + **`canmatrix`** | `canmatrix` is already a transitive dependency of `asammdf`; supports `.dbc` and `.arxml`. No new PyInstaller `--collect-all` flag needed beyond what asammdf already requires. |
| Packaging | `tauri build` → `.dmg` (macOS, arm64 / x86_64 / universal) + `.nsis` (Windows) | Standard Tauri outputs. |
| Code signing | macOS: Developer ID + notarization (entitlements: `cs.disable-library-validation` for PyInstaller dylibs). Windows: Authenticode. | Required for frictionless install. |
| CI | GitHub Actions matrix: `macos-14` (arm64), `macos-13-xlarge` (x86_64), `windows-2022` | PyInstaller sidecar built per-arch; universal binary assembled with `lipo`. |

### Why not PySide6 / pure Python Qt?

Considered and rejected. Pros: single language, native `asammdf`. Cons: much heavier install (~80 MB Qt runtime), less polished modern look. Reusing the existing Tauri+Svelte toolchain wins.

### Why not a pure-Rust MF4 parser?

Considered. `asammdf` implements ~15 years of accumulated corner-case handling (VLSD blocks, transposed compression, CG-master syncs, nested dependency trees, byte-order quirks of legacy loggers). Re-implementing this in Rust would be a multi-month project. Python sidecar is the pragmatic choice.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Tauri application                           │
│                                                                     │
│  ┌─────────────────────────────┐      ┌─────────────────────────┐   │
│  │   SvelteKit UI (webview)    │◄────►│   Tauri core (Rust)     │   │
│  │   - Toolbar                 │ IPC  │   - commands            │   │
│  │   - MetadataPanel           │      │   - sidecar manager     │   │
│  │   - SignalTree              │      │   - file dialogs        │   │
│  │   - ExportDialog            │      └──────────┬──────────────┘   │
│  │   - AboutDialog             │                 │                  │
│  │   - FrameDecodingDialog (v2)│                 │ stdio            │
│  │   - ChannelFilterDialog (v2)│                 │ JSON-RPC 2.0     │
│  └─────────────────────────────┘                 │                  │
│                                       ┌──────────▼─────────────┐   │
│                                       │  Python sidecar        │   │
│                                       │  (PyInstaller .exe)    │   │
│                                       │  libraries:            │   │
│                                       │  - asammdf             │   │
│                                       │  - canmatrix     (v2)  │   │
│                                       │  - numpy               │   │
│                                       │  - scipy               │   │
│                                       │  - npTDMS              │   │
│                                       │  - pyarrow             │   │
│                                       │  - openpyxl            │   │
│                                       │  handlers:             │   │
│                                       │  - ping                │   │
│                                       │  - open_file           │   │
│                                       │  - get_structure       │   │
│                                       │  - get_signal_stats    │   │
│                                       │  - start_export        │   │
│                                       │  - get_export_progress │   │
│                                       │  - cancel_export       │   │
│                                       │  - close_session       │   │
│                                       │  - preview_bus_dec.(v2)│   │
│                                       │  - get_exp_signals (v2)│   │
│                                       └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Process lifecycle

- Sidecar is spawned once on app startup (not per-request) to amortize Python interpreter init cost.
- Each open file becomes a **session** (UUID) held in a dict inside the sidecar; `close_session` releases the `asammdf.MDF` object and its mmap'd file handle.
- Export jobs run in background daemon threads; progress is polled via `get_export_progress`. Cancellation sets a `threading.Event` checked between channel groups.
- In dev mode (`npm run tauri dev`) Tauri copies the sidecar binary to `src-tauri/target/debug/` before running it. The dev-mode wrapper script uses an upward-walking loop to locate the project root regardless of working directory.

### JSON-RPC surface

All messages are JSON-RPC 2.0 (single line, `\n`-terminated).

#### v0.1.0 methods

| Method | Params | Result |
|---|---|---|
| `ping` | — | `{version: str}` |
| `open_file` | `{path}` | `{session_id, metadata}` |
| `get_structure` | `{session_id}` | `{groups: [GroupInfo]}` |
| `get_signal_stats` | `{session_id, group_index, channel_name}` | `{min, max, mean, count, unit, …}` |
| `start_export` | `{session_id, format, output_path}` | `{job_id}` |
| `get_export_progress` | `{job_id}` | `{status, done, total, error}` |
| `cancel_export` | `{job_id}` | `{}` |
| `close_session` | `{session_id}` | `{}` |

`format` values (v0.1.0): `"mat"` · `"tdms"` · `"parquet"` · `"csv"` · `"tsv"` · `"xlsx"`

#### v0.2.0 additions

| Method | Params | Result |
|---|---|---|
| `preview_bus_decoding` | `{session_id, db_assignments: [{group_index, db_path}]}` | `{groups: [{group_index, matched_messages, signal_count, unmatched_frame_count}]}` |
| `get_exportable_signals` | `{session_id, db_assignments}` | `{groups: [{id, name, source: "physical"\|"decoded", signals: [str]}]}` |

`start_export` extended params (v0.2.0):

| New param | Type | Meaning |
|---|---|---|
| `db_assignments` | `[{group_index, db_path}]` | Ordered DB files per raw group; omit = no decoding |
| `signal_filter` | `[{group_id, channel_name}]` | Explicit inclusion list; omit = all signals |
| `flatten` | `bool` | Merge all groups into a single time-ordered table |

`format` values added in v0.2.0: `"mf4"`

Export status values: `"running"` · `"done"` · `"error"` · `"cancelled"` · `"not_found"`

**Metadata fields** returned by `open_file`:
`file_name`, `file_size`, `version`, `start_time`, `end_time`, `duration_s`,
`num_channel_groups`, `num_nonempty_channel_groups`, `num_channels`,
`has_bus_frames`, `bus_types`, `bus_frame_counts`,
`comment`, `author`, `department`, `project`, `subject`,
`dg_compression` (list, one entry per group), `attachments`

**GroupInfo fields** returned by `get_structure`:
`index`, `acq_name`, `is_bus_raw`, `bus_type`, `has_phy`, `compression`, `channels`

### Error handling

- Python sidecar wraps every RPC in a try/except that returns `{"error": {"code": int, "message": str}}` per JSON-RPC 2.0.
- Codes: `1001` invalid params / unsupported format, `1002` session not found, `1003` export / stats error.

---

## 5. UI layout

### v0.1.0 layout

Single-window app. Toolbar across the top; two-pane split below (metadata left, signal tree right).

```
┌────────────────────────────────────────────────────────────────┐
│  [⊞ Open]   foo_2026-04-15.mf4   (412 MB)          [↑ Export] │ ← toolbar
├─────────────────────────┬──────────────────────────────────────┤
│ FILE                    │  🔍  filter signals...               │
│  File    foo.mf4        │ ▾ [zip] EngineSignals        3       │
│  Size    412 MB         │    • EngineSpeed  [rpm]   ···stats   │
│  MDF ver 4.20           │    • ThrottlePos  [%]     ···stats   │
│ TIMING                  │    • CoolantTemp  [°C]    ···stats   │
│  Start   14:02:11.003   │ ▸ [CAN][raw frames]  VehicleBus  12  │
│  End     14:48:57.412   │ ▸ GPS                         4      │
│  Duration 46m 46.4s     │                                      │
│ STRUCTURE               │                                      │
│  Groups  4              │                                      │
│  Signals 187            │                                      │
│ RECORDING               │                                      │
│  Author  J. Doe         │                                      │
│  Project Vehicle X      │                                      │
│ BUS FRAMES              │                                      │
│  CAN     2 groups       │                                      │
│ COMMENTS                │                                      │
│  "Test run 7 …"         │                                      │
└─────────────────────────┴──────────────────────────────────────┘
```

- **MetadataPanel** cards: File · Timing · Structure · Recording (author/subject/project/department — hidden when all empty) · Bus Frames (hidden when none) · Attachments (hidden when none) · Comments (full-width, scrollable `<pre>`, min-height 4rem).
- **SignalTree**: filter input, group rows with badges (`zip`/`t-zip` compression, `CAN`/`LIN`/… bus type, `raw frames`, `phy`), channel count. Compression badge always occupies a fixed slot so bus/phy badges stay column-aligned.
- **ExportDialog**: six format radio buttons (wrapping to two rows) — NI TDMS · MATLAB · Parquet · CSV · TSV · Excel. Output path picker defaults to the MF4 filename with the new extension. Progress bar + cancel during export.
- Custom scrollbars throughout (grey thumb, `thin` width, transparent or card-background track).

### v0.2.0 toolbar additions

Three new controls are added to the toolbar between the file name label and the Export button, and mirrored in a new **Export** OS menu:

```
┌───────────────────────────────────────────────────────────────────────┐
│ [⊞ Open]  foo.mf4  (412 MB)  [⛓ DB ▸]  [≋ Filter ▸]  [⊟ Flatten]  [↑] │
└───────────────────────────────────────────────────────────────────────┘
```

| Control | Enabled when | Active indicator |
|---|---|---|
| **⛓ Frame decoding** icon button | File has raw-frame groups | Blue tint + "N DB" badge |
| **≋ Channel filter** icon button | File is open | Blue tint + "N/M" badge |
| **⊟ Flatten** toggle button | File is open and format supports flatten | Blue tint when on |

**OS Export menu:**
```
Export
  Configure frame decoding…    (disabled when no raw-frame groups)
  Configure channel filter…
  ─────────────────────────
  ✓ Flatten output              (checkmark item, synced with toolbar toggle)
  ─────────────────────────
  Export…
```

### v0.2.0 ExportDialog additions

An **Active settings** strip is shown in the export dialog when any v0.2.0 feature is non-default:

```
╌ Active settings ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Frame decoding   2 groups · 2 DB files
 Channel filter   187 / 234 signals
 Flatten          On  ⚠ ~1.1 GB estimated
```

MF4 is added as a seventh format option. The Flatten toggle is disabled (with tooltip) when MF4 or TDMS is selected.

### FrameDecodingDialog

Two-column floating dialog.

**Left — Group list:** scrollable list of all raw-frame groups (`is_bus_raw: true`), each row with a checkbox, group name, and bus-type badge. A "Select all / none" toggle sits above the list. Multi-select supported (Ctrl/Cmd+click, Shift+click).

**Right — DB assignment panel:**

Title: "Select a group to configure" (0 selected) · group name (1 selected) · "Applying to N groups" (N selected). When N > 1 groups with differing configs are selected: "⚠ Configs differ — changes will replace all selected groups."

DB list rows (in priority order):
```
1.  can_vehicle.dbc         ↑  ↓  ✕    ✓ 47 messages · 312 signals
2.  can_powertrain.dbc      ↑  ↓  ✕    ✓ 23 messages · 178 signals
3.  chassis_fd.arxml           ↓  ✕    ✗ 0 messages matched
```

- First row: Up arrow absent. Last row: Down arrow absent. All other rows show both arrows.
- Preview badge (✓ green / ✗ red / spinner) fetched via `preview_bus_decoding` after each change.
- **"Add DB file…"** button appends to the bottom; **"Clear all"** link removes all.
- All mutations apply to every currently selected group simultaneously.
- Changes are live — no OK/Apply.

### ChannelFilterDialog

Classic dual-panel (shuttle) layout.

```
┌─ Configure channel filter ──────────────────────────────────────────────┐
│                                                                         │
│  Available signals                    Signals to export                 │
│  ┌──────────────────────────┐         ┌──────────────────────────────┐  │
│  │ 🔍 search…              │         │                              │  │
│  ├──────────────────────────┤   →     │  EngineSpeed  [rpm]         │  │
│  │ ▾ EngineSignals (3)     │   >>    │  ThrottlePos  [%]           │  │
│  │    EngineSpeed  [rpm]   │   <<    │  CoolantTemp  [°C]          │  │
│  │    ThrottlePos  [%]     │   ←     │  VehicleSpeed [km/h]        │  │
│  │ ▾ GPS (4)               │         │  …                          │  │
│  │    Latitude             │         │                              │  │
│  │    …                    │         │                              │  │
│  └──────────────────────────┘         └──────────────────────────────┘  │
│  [ Preview decoded channels ]          187 / 234 selected               │
│                                                                         │
│                                                           [Close]        │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Left panel (Available):** search box, grouped by channel group (collapsible), multi-select, physical signals populated on open with no RPC; "Preview decoded channels" button (visible only when DB assignments exist) fires `get_exportable_signals` and appends decoded signals with a "decoded" badge.
- **Center buttons (top to bottom):** → Add selected · >> Add all (respects current search filter) · << Remove all · ← Remove selected.
- **Right panel (To export):** multi-select for targeted removal; counter "N / M selected".
- **Initial state on first open:** all signals pre-loaded in the right panel (default = export everything); left panel empty.
- Decoded signals previewed via the button are added to the left panel checked by default; already-selected decoded signals are not duplicated.

---

## 6. Project structure

```
mf4u/
├── SPEC.md                          (this file)
├── COMMANDS.md                      (dev & build commands reference)
├── DEPENDENCIES.md                  (third-party license audit)
├── package.json                     (SvelteKit + Tauri JS deps)
├── svelte.config.js
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── routes/
│   │   └── +page.svelte             (main window — state, layout, dialogs)
│   └── lib/
│       ├── components/
│       │   ├── Toolbar.svelte
│       │   ├── MetadataPanel.svelte
│       │   ├── SignalTree.svelte
│       │   ├── ExportDialog.svelte
│       │   ├── AboutDialog.svelte
│       │   ├── FrameDecodingDialog.svelte   (v0.2.0)
│       │   └── ChannelFilterDialog.svelte   (v0.2.0)
│       ├── rpc.ts                   (typed Tauri command wrappers + interfaces)
│       └── busColors.ts             (bus-type → colour mapping)
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── entitlements.macos.plist     (cs.disable-library-validation for PyInstaller)
│   ├── build.rs
│   ├── binaries/
│   │   ├── mf4u_sidecar-aarch64-apple-darwin    (dev wrapper shell script — git-tracked)
│   │   ├── mf4u_sidecar-x86_64-apple-darwin     (dev wrapper shell script — git-tracked)
│   │   └── mf4u_sidecar-universal-apple-darwin  (dev wrapper shell script — git-tracked)
│   └── src/
│       ├── main.rs
│       └── lib.rs                   (Tauri commands + sidecar JSON-RPC relay)
└── sidecar/
    ├── requirements.txt             (asammdf, npTDMS, numpy, scipy, pyarrow, openpyxl, pytest)
    ├── __main__.py                  (JSON-RPC stdio loop + all handlers)
    ├── metadata.py                  (file-level metadata extraction + HD comment XML parser)
    ├── stats.py                     (per-channel min/max/mean)
    ├── export.py                    (MAT/TDMS/Parquet/CSV/TSV/XLSX export; v0.2.0: MF4/flatten/filter/decode)
    └── tests/
        ├── conftest.py              (pytest fixtures + sys.path setup)
        ├── generate_fixtures.py     (creates fixture .mf4 files via asammdf)
        ├── test_metadata.py         (21 tests — unit + integration)
        ├── test_stats.py            (8 tests)
        ├── test_export.py           (21 tests — all six formats + cancellation; v0.2.0: +decoding/filter/flatten)
        └── fixtures/
            ├── minimal.mf4
            ├── bus_raw.mf4
            ├── multi_group.mf4
            └── can_bus.dbc          (v0.2.0 — synthetic DBC with known message IDs)
```

The `src-tauri/binaries/` dev wrapper scripts are **git-tracked** (`.gitignore` has explicit `!` un-ignore rules). Running a local PyInstaller release build overwrites them with frozen binaries; restore with `git restore src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin`.

---

## 7. Development phases

### v0.1.0 — completed ✅

**Phase 0 — Scaffolding**
Tauri 2 + SvelteKit SPA skeleton; stub Python sidecar with `ping`; end-to-end JSON-RPC round trip verified.

**Phase 1 — Metadata display**
`open_file` + metadata extraction; HD block XML comment parser (MDF4 `<HDcomment>`, ETAS INCA `<common_properties>`); MetadataPanel cards; drag-and-drop + native Open dialog.

**Phase 2 — Signal tree + stats**
Channel group tree with filter input; per-group badges (compression, bus type, `raw frames`, `phy`); `get_signal_stats` on demand.

**Phase 3 — Export**
Background export threads with progress and cancellation; six formats (MAT · TDMS · Parquet · CSV · TSV · XLSX); multi-group file/sheet splitting; export dialog defaults to MF4 filename stem.

**Phase 4 — Packaging & signing**
PyInstaller sidecar for macOS arm64/x86_64/universal and Windows; `tauri build` producing signed `.dmg` and `.nsis`; GitHub Actions matrix CI; macOS notarization.

**Phase 5 — Polish**
App icon, About dialog, window title tracking; custom scrollbars; dev wrapper shell script with upward-walking project-root discovery.

---

### v0.2.0 — in development

Each phase is independently shippable. Natural order: A → B → C/D.

**Phase A — Frame decoding**

| Step | File(s) | Work |
|---|---|---|
| A1 | `sidecar/export.py` | `load_db(path)`, `build_decoded_mdf(mdf, db_assignments)` wrapping `extract_bus_logging` |
| A2 | `sidecar/__main__.py` | `preview_bus_decoding` handler; `start_export` accepts `db_assignments` |
| A3 | `src/lib/rpc.ts` | `previewBusDecoding`; extend `startExport` |
| A4 | `+page.svelte` | `decodingConfig` session state; toolbar button enable/disable; Export menu wiring |
| A5 | `FrameDecodingDialog.svelte` | Two-column dialog: group list with multi-select, ordered DB list with Up/Down/Remove, live preview badges, Add DB file picker |
| A6 | `Toolbar.svelte` | Frame decoding icon button + active badge |
| A7 | `sidecar/tests/` | `can_bus.dbc` fixture; tests for `load_db`, `preview_bus_decoding`, export with decoding |

**Phase B — Channel filter**

| Step | File(s) | Work |
|---|---|---|
| B1 | `sidecar/__main__.py` | `get_exportable_signals` handler |
| B2 | `sidecar/export.py` | `signal_filter` parameter on all format handlers |
| B3 | `src/lib/rpc.ts` | `getExportableSignals`; extend `startExport` |
| B4 | `+page.svelte` | `selectedSignals` session state |
| B5 | `ChannelFilterDialog.svelte` | Dual-panel shuttle: available list (search + grouping + "Preview decoded channels"), center buttons (→ >> << ←), export list, live counter |
| B6 | `Toolbar.svelte` | Channel filter icon button + "N/M" badge |
| B7 | `ExportDialog.svelte` | Active settings summary strip |
| B8 | `sidecar/tests/` | Tests: filtered export excludes unchecked channels; decoded-channel preview adds correct names |

**Phase C — Flatten + Phase D — MF4 re-export**

| Step | File(s) | Work |
|---|---|---|
| C1 | `sidecar/export.py` | `_build_flat_table()` helper; flat write paths for MAT/Parquet/CSV/TSV/XLSX (NaN / null / empty fill per format) |
| C2 | `sidecar/__main__.py` | Pass `flatten` flag through to `start_export` |
| C3 | `src/lib/rpc.ts` | Extend `startExport` |
| C4 | `+page.svelte` | `flatten` session state |
| C5 | `Toolbar.svelte` | Flatten toggle button; disabled when TDMS or MF4 format active |
| C6 | `ExportDialog.svelte` | Flatten row in active settings strip; memory-estimate warning; disable Flatten for TDMS/MF4 |
| D1 | `sidecar/export.py` | `_do_mf4(mdf, output_path, job, db_assignments, signal_filter)` using `MDF.filter()` + `MDF.save()` |
| D2 | `sidecar/__main__.py` | Accept `"mf4"` in format validation |
| D3 | `src/lib/rpc.ts` | Add `"mf4"` to format union |
| D4 | `ExportDialog.svelte` | MF4 as seventh format option; Flatten disabled when MF4 selected |
| CD1 | `sidecar/tests/` | Flatten: master timestamp axis correct, fill values correct per format, single-file output; MF4: round-trip metadata preserved, decoded/filtered channels only |

---

## 8. Test fixtures

Fixture files in `sidecar/tests/fixtures/`, all small (< 1 MB), generated by `generate_fixtures.py`:

| File | Purpose |
|---|---|
| `minimal.mf4` | One group, three float channels (`Ch1`/`Ch2`/`Ch3`), 100 samples, XML HD comment with author/project/subject/department |
| `bus_raw.mf4` | One channel group with `CAN_DataFrame` channel; exercises bus-frame detection |
| `multi_group.mf4` | Four data groups saved with `compression=1` (deflate); exercises tree rendering, compression detection, multi-file/sheet export |
| `can_bus.dbc` *(v0.2.0)* | Synthetic DBC with a small set of messages whose IDs match frames in `bus_raw.mf4`; used to test `preview_bus_decoding` and decoded export |

CI runs `pytest sidecar/tests/ -v` independently of the Tauri build.

---

## 9. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| PyInstaller bundle size (~60–80 MB with numpy + pyarrow) bloats the installer. | Acceptable for a desktop tool. PyInstaller bundles the full interpreter; size documented in COMMANDS.md. |
| macOS notarization of bundled Python binary rejected for missing entitlements. | `cs.disable-library-validation` in `entitlements.macos.plist`. XML comments in the plist cause `AMFIUnserializeXML` parse errors — plist must be comment-free. |
| Local PyInstaller release build silently overwrites the dev wrapper shell script. | Dev wrappers are git-tracked; `git restore` recovers them instantly. Documented in COMMANDS.md with a callout warning. |
| Very large files (> 2 GB) on Windows. | `asammdf` streams with `memory="low"`; no full-file mmap. |
| LGPL libraries (asammdf, nptdms) bundled via PyInstaller `--onefile`. | Documented in DEPENDENCIES.md with compliance guidance (user notice + source rebuild instructions). |
| Python sidecar crashes mid-export. | No in-place writes; partial output files are deleted on error/cancel via `job._cleanup` list. |
| `extract_bus_logging()` memory cost *(v0.2.0)*. | Creates a full in-memory MDF. For large files this could exceed 1 GB RAM. Monitor and consider streaming group-by-group if this becomes a problem in practice. |
| ARXML multi-ECU complexity *(v0.2.0)*. | ARXML files can describe multiple ECUs/clusters. `canmatrix` exposes all networks; if a file contains more than one, the UI will need a way to select which to apply. Defer to a follow-up if the common single-ECU case covers 95%+ of users. |
| Ambiguous message IDs across multiple DB files *(v0.2.0)*. | Two DB files may define the same CAN ID differently. The ordered DB list establishes a clear priority: first match wins. Documented in the dialog tooltip. |
| Flat-table memory ceiling *(v0.2.0)*. | A 1 GB MF4 with 10 groups × 100 channels × 1 M samples produces an ~800 MB float64 array. Client-side estimate shown before export; warning badge at > 500 MB threshold. |
| Signal filter UI scalability *(v0.2.0)*. | Files with > 500 signals require a virtualised list in the filter dialog. The dual-panel shuttle must use a virtual scroll implementation rather than a plain DOM list. |

---

## 10. Out of scope

- Signal plotting / time-series visualization (v3+ candidate; uPlot would be the likely choice).
- DBC/ARXML signal database export to formats other than the decoded MF4 channels (e.g. a standalone `.csv` mapping file).
- Batch-mode CLI processing of multiple files.
- File diff view / side-by-side session comparison.
- MDF 3.x explicit support / testing.
- Legacy `.tdm` export — would require the proprietary NI DataPlugin, Windows-only.

---

*End of spec.*
