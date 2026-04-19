# mf4u — Specification

**Status:** v0.1.0 — 2026-04-19
**Target platforms:** macOS (arm64 + x86_64), Windows (x86_64). Linux buildable as side-effect but not officially supported in v1.

---

## 1. Overview

mf4u is a desktop GUI tool that opens ASAM MDF 4.x (`.mf4`, `.mdf`) measurement files — primarily produced by automotive data loggers (Vector VN, CSS Electronics CANedge, ETAS INCA, dSPACE, etc.) — and presents a fast, read-only inspection view of the file's contents. It also offers one-click export of the signal data to multiple formats for downstream analysis: MATLAB `.mat`, NI `.tdms`, Apache Parquet, CSV, TSV, and Excel `.xlsx`.

It is **not** a signal plotter or a signal database (DBC/ARXML) decoder in v1 — scope is intentionally limited to inspection + re-export.

---

## 2. Goals & Non-goals

### Goals (v1)

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
┌─────────────────────────────────────────────────────────────────┐
│                       Tauri application                         │
│                                                                 │
│  ┌───────────────────────────┐      ┌─────────────────────────┐ │
│  │   SvelteKit UI (webview)  │◄────►│   Tauri core (Rust)     │ │
│  │   - Toolbar               │ IPC  │   - commands            │ │
│  │   - MetadataPanel         │      │   - sidecar manager     │ │
│  │   - SignalTree            │      │   - file dialogs        │ │
│  │   - ExportDialog          │      └──────────┬──────────────┘ │
│  │   - AboutDialog           │                 │                │
│  └───────────────────────────┘                 │ stdio          │
│                                                │ JSON-RPC 2.0   │
│                                     ┌──────────▼─────────────┐  │
│                                     │  Python sidecar        │  │
│                                     │  (PyInstaller .exe)    │  │
│                                     │  libraries:            │  │
│                                     │  - asammdf             │  │
│                                     │  - numpy               │  │
│                                     │  - scipy               │  │
│                                     │  - npTDMS              │  │
│                                     │  - pyarrow             │  │
│                                     │  - openpyxl            │  │
│                                     │  handlers:             │  │
│                                     │  - ping                │  │
│                                     │  - open_file           │  │
│                                     │  - get_structure       │  │
│                                     │  - get_signal_stats    │  │
│                                     │  - start_export        │  │
│                                     │  - get_export_progress │  │
│                                     │  - cancel_export       │  │
│                                     │  - close_session       │  │
│                                     └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Process lifecycle

- Sidecar is spawned once on app startup (not per-request) to amortize Python interpreter init cost.
- Each open file becomes a **session** (UUID) held in a dict inside the sidecar; `close_session` releases the `asammdf.MDF` object and its mmap'd file handle.
- Export jobs run in background daemon threads; progress is polled via `get_export_progress`. Cancellation sets a `threading.Event` checked between channel groups.
- In dev mode (`npm run tauri dev`) Tauri copies the sidecar binary to `src-tauri/target/debug/` before running it. The dev-mode wrapper script uses an upward-walking loop to locate the project root regardless of working directory.

### JSON-RPC surface (v0.1.0)

All messages are JSON-RPC 2.0 (single line, `\n`-terminated).

| Method | Params | Result |
|---|---|---|
| `ping` | — | `{version: str}` |
| `open_file` | `{path}` | `{session_id, metadata}` |
| `get_structure` | `{session_id}` | `{groups: [GroupInfo]}` |
| `get_signal_stats` | `{session_id, group_index, channel_name}` | `{min, max, mean, count, unit, ...}` |
| `start_export` | `{session_id, format, output_path}` | `{job_id}` |
| `get_export_progress` | `{job_id}` | `{status, done, total, error}` |
| `cancel_export` | `{job_id}` | `{}` |
| `close_session` | `{session_id}` | `{}` |

`format` values: `"mat"` · `"tdms"` · `"parquet"` · `"csv"` · `"tsv"` · `"xlsx"`

Export status values: `"running"` · `"done"` · `"error"` · `"cancelled"` · `"not_found"`

**Metadata fields** returned by `open_file`:
`file_name`, `file_size`, `version`, `start_time`, `end_time`, `duration_s`,
`num_channel_groups`, `num_nonempty_channel_groups`, `num_channels`,
`has_bus_frames`, `bus_types`, `bus_frame_counts`,
`comment`, `author`, `department`, `project`, `subject`,
`dg_compression` (list, one entry per group),
`attachments`

**GroupInfo fields** returned by `get_structure`:
`index`, `acq_name`, `is_bus_raw`, `bus_type`, `has_phy`, `compression`, `channels`

### Error handling

- Python sidecar wraps every RPC in a try/except that returns `{"error": {"code": int, "message": str}}` per JSON-RPC 2.0.
- Codes: `1001` invalid params / unsupported format, `1002` session not found, `1003` export / stats error.

---

## 5. UI layout

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
│       │   └── AboutDialog.svelte
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
    ├── export.py                    (MAT / TDMS / Parquet / CSV / TSV / XLSX export jobs)
    └── tests/
        ├── conftest.py              (pytest fixtures + sys.path setup)
        ├── generate_fixtures.py     (creates fixture .mf4 files via asammdf)
        ├── test_metadata.py         (21 tests — unit + integration)
        ├── test_stats.py            (8 tests)
        ├── test_export.py           (21 tests — all six formats + cancellation)
        └── fixtures/
            ├── minimal.mf4
            ├── bus_raw.mf4
            └── multi_group.mf4
```

The `src-tauri/binaries/` dev wrapper scripts are **git-tracked** (`.gitignore` has explicit `!` un-ignore rules). Running a local PyInstaller release build overwrites them with frozen binaries; restore with `git restore src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin`.

---

## 7. Development phases

Each phase ends in a runnable artifact. All phases completed as of v0.1.0.

**Phase 0 — Scaffolding** ✅
- Tauri 2 + SvelteKit SPA skeleton.
- Stub Python sidecar with `ping` handler.
- End-to-end JSON-RPC round trip verified.

**Phase 1 — Metadata display** ✅
- `open_file` + metadata extraction in Python.
- HD block XML comment parser (MDF4 `<HDcomment>`, ETAS INCA `<common_properties>`).
- `MetadataPanel.svelte`: File / Timing / Structure / Recording / Bus Frames / Attachments / Comments cards.
- Drag-and-drop + native Open dialog file open.

**Phase 2 — Signal tree + stats** ✅
- Channel group tree with filter input.
- Per-group badges: compression (`zip` / `t-zip`), bus type (colour-coded), `raw frames`, `phy`.
- `get_signal_stats` on demand (lazy, per channel).

**Phase 3 — Export** ✅
- Background export threads with progress polling and cancellation.
- Six formats: MAT · TDMS · Parquet · CSV · TSV · XLSX.
- Multi-group files: one output file per group for Parquet/CSV/TSV; one workbook with multiple sheets for XLSX.
- Export dialog defaults to MF4 filename stem.

**Phase 4 — Packaging & signing** ✅
- PyInstaller one-file sidecar for macOS arm64, x86_64 (via Rosetta 2), universal (lipo-merged), and Windows x86_64.
- `tauri build` produces signed `.dmg` and `.nsis` installer.
- GitHub Actions matrix CI (arm64 + x86_64 + universal macOS, Windows).
- macOS notarization via `APPLE_ID` / `APPLE_PASSWORD` / `APPLE_TEAM_ID` env vars.
- Entitlements: `cs.disable-library-validation` required for PyInstaller-bundled unsigned dylibs.

**Phase 5 — Polish** ✅
- App icon, About dialog, window title tracking open file.
- Custom scrollbars (signal tree, comment card).
- Dev wrapper shell script with upward-walking project-root discovery (works from `target/debug/` when Tauri copies it there).

---

## 8. Test fixtures

Three fixture files in `sidecar/tests/fixtures/`, all small (< 1 MB), generated by `generate_fixtures.py`:

1. **`minimal.mf4`** — one channel group, three float channels (`Ch1`/`Ch2`/`Ch3`), 100 samples, XML HD comment with author/project/subject/department.
2. **`bus_raw.mf4`** — one channel group with `CAN_DataFrame` channel. Exercises bus-frame detection.
3. **`multi_group.mf4`** — four data groups saved with `compression=1` (deflate). Exercises tree rendering, compression-state detection, and multi-file/multi-sheet export.

CI runs `pytest sidecar/tests/ -v` independently of the Tauri build (50 tests total).

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

---

## 10. Out of scope but worth flagging

- **v2 candidates:** signal plotter (uPlot), DBC decoding of raw bus frames, batch-mode CLI, file diff view, side-by-side session comparison, MDF3 explicit support.
- **Legacy `.tdm`:** revisit only if user-documented demand appears; would need a Windows-only code path using NI's System Configuration API. Current `.tdms` output is importable by DIAdem directly.

---

*End of spec.*
