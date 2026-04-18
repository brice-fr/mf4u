# mf4u — Specification

**Status:** Draft v0.1 — 2026-04-18
**Target platforms:** macOS (arm64 + x86_64), Windows (x86_64). Linux buildable as side-effect but not officially supported in v1.

---

## 1. Overview

mf4u is a desktop GUI tool that opens ASAM MDF 4.x (`.mf4`, `.mdf`) measurement files — primarily produced by automotive data loggers (Vector VN, CSS Electronics CANedge, ETAS INCA, dSPACE, etc.) — and presents a fast, read-only inspection view of the file's contents. It also offers one-click export of the signal data to MATLAB `.mat` and NI `.tdms` formats for downstream analysis.

It is **not** a signal plotter or a signal database (DBC/ARXML) decoder in v1 — scope is intentionally limited to inspection + re-export.

---

## 2. Goals & Non-goals

### Goals (v1)

- Open `.mf4` / `.mdf` files up to ~2 GB in well under a second (metadata-only parse, no signal load).
- Display file-level metadata:
  - MDF version (e.g. `4.10`, `4.20`)
  - File size, creation/modification timestamps (OS), internal start/end time, duration
  - Measurement comment / author / subject / project (if present in the HD block)
  - Data groups count, channel groups count, total signals (channels) count
  - Presence of bus-logging raw frames (CAN / CAN-FD / LIN / FlexRay) vs. decoded signal groups
  - Attachments list (embedded files, if any)
  - Compression state per data group (uncompressed / zipped / transposed-zipped)
- Display per-signal statistics on demand (lazily loaded, only when user expands a group):
  - Name, unit, description, source, data type, samples count
  - min / max / mean (numeric channels only)
  - First/last timestamp
- Export the complete measurement to:
  - `.mat` (MATLAB v7.3 / HDF5-backed) — native via `asammdf.MDF.export("mat")`
  - `.tdms` — via `npTDMS` writer, one group per channel group
- Progress reporting + cancellation for any long-running parse/export.

### Non-goals (v1)

- Signal plotting / time-series visualization.
- DBC/ARXML decoding of raw bus frames into physical signals (could be a v2 feature; `asammdf` supports this).
- Editing the MF4 file.
- `.tdm` (legacy NI) export — would require the proprietary NI DataPlugin, effectively Windows-only, not worth the complexity. We expose `.tdms` instead, which is the modern NI format and round-trips losslessly in the NI ecosystem (DIAdem, LabVIEW).
- `.mdf` 3.x support — possible via `asammdf` but explicitly out of scope for v1 UI testing (the library will still open them; we just won't test/market it).

---

## 3. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Shell | **Tauri 2** | Native webview, small binary (~10 MB), signed/notarized builds on macOS and Windows, mature sidecar process API. |
| UI framework | **SvelteKit** (SPA mode, `@sveltejs/adapter-static`) | Matches the user's existing hex-editor stack; concise reactive components; great for tree/table-heavy UIs. |
| UI components | Headless primitives (`bits-ui` or `melt-ui`) + custom CSS | No heavyweight component library; tables/trees are the only complex widgets. |
| Tauri ↔ UI IPC | Tauri commands (JSON) + Tauri events (for progress streams) | Standard. |
| MF4 parsing engine | **Python 3.12 + `asammdf` 8.x** packaged via **PyInstaller** as a Tauri **sidecar binary** | `asammdf` is the only production-grade, fully-featured MDF 4.x library. Rust crates (`mf4`, `mdflib`) cover only a subset of blocks and lack raw bus-frame handling. |
| Tauri ↔ Python IPC | **JSON-RPC 2.0 over stdio** (line-delimited) | Simple, no extra port, easy to unit-test the Python side alone. Requests carry an `id`, progress events are notifications (no `id`). |
| `.mat` export | `asammdf.MDF.export(fmt="mat", version="7.3")` | Native; HDF5 under the hood, handles large files and Unicode names. |
| `.tdms` export | `npTDMS` `TdmsWriter` | Pure-Python, cross-platform, writes the canonical TDMS 2.0 layout. |
| Packaging | `tauri build` → `.dmg` (macOS, universal binary via lipo) + `.msi` (Windows, WiX) | Standard Tauri outputs. |
| Code signing | macOS: Developer ID + notarization. Windows: Authenticode (EV cert preferred for SmartScreen). | Required for frictionless install. Out-of-scope for first dev builds, in-scope for v1.0 release. |
| CI | GitHub Actions matrix: `macos-14` (arm64), `macos-13` (x86_64), `windows-2022` | Standard tauri-action workflow. |

### Why not PySide6 / pure Python Qt?

Considered and rejected. Pros: single language, native `asammdf`. Cons: much heavier install (~80 MB Qt runtime), less polished modern look, the user already owns the Tauri+Svelte toolchain from hex-editor. Reusing that knowledge wins.

### Why not a pure-Rust MF4 parser?

Considered. `asammdf` implements ~15 years of accumulated corner-case handling (VLSD blocks, transposed compression, CG-master syncs, nested dependency trees, byte-order quirks of legacy loggers). Re-implementing this in Rust would be a multi-month project on its own. Python sidecar is the pragmatic choice; cost is ~40 MB added to the installer (frozen interpreter + `asammdf` + `numpy`).

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tauri application                       │
│                                                             │
│  ┌─────────────────────────┐      ┌─────────────────────┐   │
│  │   SvelteKit UI (webview)│◄────►│   Tauri core (Rust) │   │
│  │   - FileDropZone        │ IPC  │   - commands        │   │
│  │   - MetadataPanel       │      │   - sidecar mgr     │   │
│  │   - SignalTree          │      │   - file dialogs    │   │
│  │   - ExportDialog        │      │   - progress relay  │   │
│  │   - ProgressBar         │      └──────────┬──────────┘   │
│  └─────────────────────────┘                 │              │
│                                              │ stdio        │
│                                              │ JSON-RPC 2.0 │
│                                   ┌──────────▼──────────┐   │
│                                   │  Python sidecar     │   │
│                                   │  (PyInstaller .exe) │   │
│                                   │  - asammdf          │   │
│                                   │  - npTDMS           │   │
│                                   │  - handlers:        │   │
│                                   │    open_file        │   │
│                                   │    get_metadata     │   │
│                                   │    get_signal_stats │   │
│                                   │    export_mat       │   │
│                                   │    export_tdms      │   │
│                                   │    cancel           │   │
│                                   └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Process lifecycle

- Sidecar is spawned once on app startup (not per-request) to amortize the Python interpreter init cost (~400 ms).
- Each open file becomes a **session** (UUID) held in a dict inside the sidecar; `close_session` releases the `asammdf.MDF` object and its mmap'd file handle.
- A single in-flight long operation is cancellable via a `cancel` RPC that sets a threading.Event checked by `asammdf`'s progress callback.

### JSON-RPC surface (v1)

Request → Response:
- `open_file({path}) → {session_id, metadata}`
- `get_signal_stats({session_id, channel_ids: [int]}) → {stats: [...]}`
- `export({session_id, format: "mat"|"tdms", out_path}) → {ok: true}`  (progress events streamed during)
- `close_session({session_id}) → {}`
- `cancel({session_id}) → {}`
- `ping() → {version}`

Notifications (sidecar → host):
- `progress({session_id, op, fraction: 0..1, stage: str})`
- `log({level, msg})`

### Error handling

- Python sidecar wraps every RPC in a try/except that returns `{"error": {"code": int, "message": str, "data": {...}}}` per JSON-RPC 2.0.
- Codes: `1001` invalid file, `1002` session not found, `1003` export failed, `1004` cancelled, `1005` unsupported MDF version.
- Rust side maps these to typed errors that the UI renders as toast + detail modal.

---

## 5. UI layout

Single-window app, three-pane layout (top-down on narrow widths):

```
┌──────────────────────────────────────────────────────────────┐
│  [Open…]   foo_2026-04-15.mf4   (412 MB)         [Export ▾]  │ ← toolbar
├──────────────────────────────────────────────────────────────┤
│ File metadata              │ Signal tree                     │
│ ─────────────────          │ ────────────                    │
│ Version      4.20          │ ▾ DG 0 — CAN_DataFrame (raw)    │
│ Start        14:02:11.003  │    (lazy-loaded)                │
│ End          14:48:57.412  │ ▾ DG 1 — EngineSignals          │
│ Duration     46m 46.4s     │    • EngineSpeed  [rpm]   stats │
│ DG count     4             │    • ThrottlePos  [%]     stats │
│ CG count     12            │    • CoolantTemp  [°C]    stats │
│ Signals      187           │ ▸ DG 2 — VehicleBus (raw)       │
│ Raw bus      Yes (CAN-FD)  │ ▸ DG 3 — GPS                    │
│ Comment      "Test run 7"  │                                 │
└──────────────────────────────────────────────────────────────┘
```

- Signal tree is virtualized (`svelte-virtual-list`) — some files have 10k+ signals.
- Clicking "stats" on a signal issues `get_signal_stats` for that single channel and inlines the result.
- `[Export ▾]` opens a small dialog: format radio (MAT / TDMS), destination path picker, optional "raster" resample dropdown (passed straight through to `asammdf.export`).

---

## 6. Project structure

```
mf4u/
├── SPEC.md                         (this file)
├── README.md
├── package.json                    (SvelteKit + Tauri JS deps)
├── svelte.config.js
├── vite.config.js
├── src/                            (SvelteKit UI)
│   ├── routes/
│   │   └── +page.svelte            (main window)
│   └── lib/
│       ├── components/
│       │   ├── MetadataPanel.svelte
│       │   ├── SignalTree.svelte
│       │   ├── ExportDialog.svelte
│       │   └── ProgressBar.svelte
│       ├── rpc.js                  (Tauri ↔ sidecar wrapper)
│       └── stores.js               (current session, metadata, progress)
├── src-tauri/                      (Rust Tauri shell)
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── build.rs
│   └── src/
│       ├── main.rs
│       ├── sidecar.rs              (spawn + stdio JSON-RPC)
│       └── commands.rs             (Tauri commands called from UI)
└── sidecar/                        (Python engine)
    ├── pyproject.toml
    ├── requirements.txt            (asammdf, npTDMS, numpy)
    ├── mf4u_sidecar/
    │   ├── __main__.py             (JSON-RPC stdio loop)
    │   ├── rpc.py
    │   ├── handlers.py
    │   ├── metadata.py
    │   ├── stats.py
    │   └── export.py
    ├── tests/
    │   └── fixtures/               (small synthetic .mf4 files)
    └── build.py                    (PyInstaller build → binary placed in src-tauri/binaries/)
```

The `src-tauri/binaries/` directory holds the platform-triple-suffixed sidecar binaries (`mf4u_sidecar-aarch64-apple-darwin`, `mf4u_sidecar-x86_64-pc-windows-msvc.exe`, …) per Tauri's sidecar convention.

---

## 7. Development phases

Each phase ends in a runnable artifact.

**Phase 0 — Scaffolding** (½ day)
- `npm create tauri-app` with Svelte template.
- Add `sidecar/` Python project with a stub `ping` handler.
- Wire Tauri to spawn the sidecar and respond to a "Ping" button in the UI.
- Verify end-to-end JSON-RPC round trip.

**Phase 1 — Metadata display** (1 day)
- Implement `open_file` + `get_metadata` in Python.
- Build `MetadataPanel.svelte`.
- Drag-and-drop file open + native Open dialog.

**Phase 2 — Signal tree + stats** (1 day)
- Virtualized tree of DG → CG → channels.
- `get_signal_stats` on demand.
- Loading and empty states.

**Phase 3 — Export** (1 day)
- `.mat` export + progress streaming.
- `.tdms` export via `npTDMS`.
- Cancel button wired to `cancel` RPC.

**Phase 4 — Packaging & signing** (1 day)
- PyInstaller one-file build for both macOS arches + Windows.
- `tauri build` produces signed `.dmg` and `.msi`.
- GitHub Actions workflow.

**Phase 5 — Polish** (½ day)
- App icon, About dialog, error toasts, keyboard shortcuts (Cmd/Ctrl+O, Cmd/Ctrl+E).
- macOS file-type association (`CFBundleDocumentTypes` for `.mf4`).

Total: ~5 engineering days to v1.0.

---

## 8. Test fixtures

Three categories in `sidecar/tests/fixtures/`, all small (<1 MB):

1. **`minimal.mf4`** — hand-crafted via `asammdf`, one channel group, three float channels, 100 samples. Round-trip sanity.
2. **`bus_raw.mf4`** — synthesized CAN-FD raw-frame group. Exercises the "raw frames present" metadata path.
3. **`multi_group.mf4`** — four data groups with mixed compression (uncompressed + DZ zipped). Exercises tree rendering and compressed-read path.

Generation script (`tests/generate_fixtures.py`) is checked in; fixtures themselves are checked in too (tiny).

CI runs `pytest` on the sidecar independently of the Tauri build.

---

## 9. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| PyInstaller bundle size (~50 MB with numpy) bloats the installer. | Acceptable for a desktop tool. Use `--strip` on macOS, UPX on Windows. Exclude `tkinter`, `matplotlib`, and `pandas` if asammdf doesn't pull them. |
| macOS notarization of the bundled Python binary flagged for missing entitlements. | Use `--codesign-identity` in PyInstaller and sign the inner binary too, then re-sign the outer `.app`. Documented recipe, no novel work. |
| Very large files (>2 GB) on 32-bit-mmap'd Windows paths. | `asammdf` already streams; set `memory="low"` for files >500 MB (detected by size). |
| TDMS writer performance on files with >1000 channels. | Benchmark on `multi_group.mf4` scaled up; if slow, fall back to chunked writes (npTDMS supports this). |
| Python sidecar crashes mid-export. | Tauri detects stdio EOF, shows an error, auto-respawns the sidecar. No data corruption — we never write in place. |

---

## 10. Out of scope but worth flagging

- **v2 candidates:** signal plotter (uPlot), DBC decoding of raw bus frames, CSV export, batch-mode CLI, file diff view, side-by-side session comparison.
- **Legacy `.tdm`:** revisit only if a user-documented demand appears; would need a Windows-only code path using NI's System Configuration API. Current `.tdms` output is importable by DIAdem directly.

---

*End of spec.*
