# mf4u — MF4 utility

A desktop MF4 / MDF file inspector and exporter, built with [Tauri 2](https://tauri.app), [SvelteKit](https://kit.svelte.dev), and a Python sidecar powered by [asammdf](https://github.com/danielhrisca/asammdf).

Open `.mf4` and `.mdf` files, browse the full channel-group hierarchy, inspect per-channel statistics, **decode raw bus frames using DBC / ARXML databases**, **filter signals**, and export to **MATLAB `.mat`**, **NI TDMS `.tdms`**, **Apache Parquet**, **CSV**, **TSV**, **Excel `.xlsx`**, or back to **`.mf4`** — with background-threaded progress tracking and cancellation throughout.

---

## Features

### File opening

- **Open** `.mf4` / `.mdf` files via the toolbar button, **File → Open…** (⌘O / Ctrl+O), or by **drag-and-drop** onto the window
- The toolbar Open button shows a spinner while the file is being parsed; the rest of the UI is blocked until metadata is ready
- The OS window title updates to `<filename> — mf4 utility` while a file is open

---

### Inspector pane

The left panel presents structured metadata extracted from the MDF4 header, organised into cards.

#### File
| Field | Description |
|---|---|
| File | Base filename |
| Size | Human-readable file size |
| MDF version | Version string from the file header (e.g. `4.10`, `4.20`) |
| Finalized | `Yes` when the on-disk identification block reads `MDF`; an amber `⚠ no` badge (with tooltip listing pending finalization tasks) when the file is unfinalized |
| Sorted | `Yes` when every data group has `record_id_len == 0` (single CG per DG, contiguous records); an amber `⚠ no` badge when records are interleaved across channel groups |

#### Timing
| Field | Description |
|---|---|
| Start | Recording start timestamp (locale-formatted, ms precision) |
| End | Recording end timestamp |
| Duration | Total duration, auto-scaled (ms / s / m:ss / h:mm:ss) |

#### Structure
| Field | Description |
|---|---|
| Total channel groups | All channel groups, including empty ones |
| Non-empty groups | Groups containing at least one channel |
| Total signals | Sum of all channels across all groups |
| Physical signals | Channels belonging to non-raw-frame groups |

#### Recording
Shown only when at least one of the following is present in the HD block:
`Author`, `Subject`, `Project`, `Department` — parsed from both standard MDF4 `<HDcomment>` XML and ETAS INCA `<common_properties>` XML formats.

#### Bus Frames
Shown only when the file contains bus-logged data. One row per detected bus type, each label colour-coded to match the signal-tree badges:

| Bus | Colour |
|---|---|
| CAN | Blue `#5b9cf6` |
| CAN FD | Cyan `#38bdf8` |
| LIN | Green `#4ade80` |
| MOST | Purple `#b77ff0` |
| FlexRay | Orange `#fb923c` |
| Ethernet | Teal `#2dd4bf` |
| K-Line | Yellow `#f0c040` |
| USB | Red `#f07070` |

#### Attachments
Lists embedded attachment filenames; hidden when none are present.

#### Comments
Full recording comment rendered in a scrollable monospace block; hidden when absent.

---

### Signal tree

The right panel is a collapsible channel-group hierarchy.

#### Filter bar
- **Live search** filters channel names across all groups as you type (case-insensitive substring match)
- A group · signal summary counter sits to the right of the input

#### Group rows

| Element | Meaning |
|---|---|
| ▸ / ▾ chevron | Collapsed / expanded; click anywhere on the row to toggle |
| Acquisition name | `acq_name` from the MDF4 CG block, or `Group N` if absent |
| `zip` / `t-zip` badge | Channel group data is deflate-compressed or transposed-compressed |
| Bus-type badge | Colour-coded pill showing the detected bus type (e.g. `CAN FD`) |
| `raw frames` badge | Grey pill alongside the bus badge; indicates raw bus frames, not decoded physical values |
| `phy` badge (red) | Non-raw-frames group that contains at least one physical channel |
| Channel count | Right-aligned, fixed 4-character width |

**Bus-type detection** uses a two-stage strategy:
1. **Channel-name matching** — presence of `CAN_DataFrame`, `LIN_Frame`, etc.; CAN FD distinguished by `CAN_DataFrame.BRS` / `CAN_DataFrame.EDL`.
2. **`acq_source.bus_type` field** — reads the asammdf v4 `BUS_TYPE_*` constant from the CG acquisition source block.

#### Channel rows (expanded group)

| Column | Content |
|---|---|
| Name | Truncated with ellipsis; full name + comment visible on hover |
| `phy` badge | Red pill when the channel has a unit or a non-trivial conversion |
| Unit | Physical unit string, right-aligned |
| Statistics | `n=`, `min=`, `max=`, `μ=` once loaded |
| `stats` button | Click to lazily load statistics for that channel; cached for the session |

---

### Frame decoding

Opened via **File → Frame Decoding…** or the toolbar **decode** button; enabled only when the open file contains at least one raw-frame channel group.

- Load one or more `.dbc` or `.arxml` bus description files and **assign each to one or more raw-frame channel groups** in priority order
- A **live preview panel** shows matched message count and decoded signal count per assignment
- On export, `asammdf.extract_bus_logging` is used to decode the raw frames into named physical signals
- Raw frames that match no message in any assigned description are omitted from the output
- Assignments persist as session state and are visible on the toolbar (badge showing the number of active assignments)

---

### Channel filter

Opened via **File → Configure channel filter…** or the toolbar **filter** button; available for both physical and decoded channels.

- **Dual-panel picker**: Available channels on the left, selected channels to export on the right
- Add, remove, add-all, remove-all controls and a live search box in each panel
- The available list is pre-populated with all physical signals from the file; a **"Preview decoded channels"** button enriches it with the signals that would result from the configured frame decoding
- The selection is saved as session state and applied at export time
- The toolbar shows an active filter badge (`N selected`) when a filter is in effect
- Resetting the frame decoding configuration clears any active channel filter automatically

---

### Export dialog

Opened via **File → Export…** (⌘E / Ctrl+E) or the Export toolbar button; enabled only when a file is loaded.

#### Supported formats

| Format | Extension | Notes |
|---|---|---|
| NI TDMS | `.tdms` | One TDMS group per MDF4 channel group |
| MATLAB | `.mat` | `scipy.io.savemat` with compression; channel names sanitised to valid MATLAB variable names |
| Apache Parquet | `.parquet` | Snappy-compressed; one file per channel group for multi-group files |
| CSV | `.csv` | One file per channel group for multi-group files; UTF-8, `timestamps` first column |
| TSV | `.tsv` | Same as CSV with tab delimiter |
| Excel | `.xlsx` | Single workbook; one worksheet per channel group |
| MF4 | `.mf4` | Re-export with decoded signals and/or filtered channels; HD metadata preserved |

#### Frame decoding in export
When at least one DB assignment is configured, a **Frame decoding** row shows the number of active assignments. Decoding is applied using `asammdf.extract_bus_logging` before writing; decoded groups in the output MF4 have their `BUS_EVENT` channel-group flag cleared so downstream viewers no longer classify them as raw-frame groups.

#### Flatten output
Available for MAT, Parquet, CSV, TSV, and XLSX (not TDMS or MF4). Merges all channel groups into a single timestamp-union table; cells where a channel has no record at a given timestamp are filled with `NaN` (MAT / Parquet) or an empty cell (CSV / TSV / XLSX).

#### Channel filter in export
When a signal filter is active, a **Signal filter** row shows the number of selected signals. Only the listed channels are written; all others are silently skipped.

#### Progress & control
- Live progress bar: `{done}/{total} groups ({pct}%)`
- **Cancel** stops the background export thread and removes any partial output files
- Export / Close / Cancel buttons shown contextually based on state

---

### Preferences dialog

Opened via **File → Preferences…** or ⌘, (macOS).

| Setting | Default | Description |
|---|---|---|
| Link MATLAB groups by time axis | On | Appends `_t1`, `_t2`, … suffixes to channel variable names in `.mat` exports so each channel's time-axis membership is explicit in MATLAB |

---

### Status bar

A slim strip at the bottom of the window, visible whenever a file is loaded:

```
3 groups · 142 signals · 47 physical · 2 empty groups     hide empty groups · expand all · collapse all
```

| Right-side controls | Behaviour |
|---|---|
| hide / show empty groups | Toggles zero-channel groups in the tree |
| expand all / collapse all | Opens or closes every group simultaneously |

---

### OS integration

#### Native menus (macOS)

| Menu | Items |
|---|---|
| **mf4u** | About mf4u · Preferences ⌘, · Quit |
| **File** | Open… `⌘O` · Export… `⌘E` · Frame Decoding… · Configure channel filter… · Close Window |
| **Help** | About mf4u |

On Windows the About / Preferences items appear under the Help menu; the macOS app menu is omitted.

#### About dialog
Shows the app icon, version (read from `package.json` at build time), and copyright.

---

## Distribution

### Packaged releases

Pre-built installers are published on the [Releases](../../releases) page via GitHub Actions:

| Platform | Artifact | Architecture |
|---|---|---|
| macOS | `.dmg` universal installer | Apple Silicon + Intel (arm64 + x86_64) |
| Windows | `.exe` NSIS installer | x86_64 |

The macOS app is **code-signed** with a Developer ID Application certificate and **notarized** through Apple's notarization service; Gatekeeper opens it without a quarantine warning.

### GitHub Actions workflow

Triggered by pushing a `v*` tag (or manually via workflow dispatch):

1. **sidecar-macos-arm64** — builds the Python sidecar with PyInstaller on `macos-14` (arm64)
2. **sidecar-macos-x86_64** — builds the Python sidecar with PyInstaller on `macos-14` (x86_64 via Rosetta 2)
3. **release-macos** — downloads both sidecar artifacts, merges them into a universal binary with `lipo`, signs and notarizes, publishes to the GitHub release draft
4. **release-windows** — builds the sidecar and NSIS installer on `windows-latest`, publishes to the same draft

The release is created as a **draft**; review and publish it manually on GitHub.

---

## Development toolchain

| Component | Technology | Version |
|---|---|---|
| App framework | [Tauri 2](https://tauri.app) | 2.x |
| Frontend | [SvelteKit](https://kit.svelte.dev) + [Svelte 5](https://svelte.dev) | 5.x runes |
| Language | TypeScript | 5.x |
| Build tool | [Vite](https://vitejs.dev) | 6.x |
| Rust backend | [Rust](https://rust-lang.org) | stable |
| MDF4 parsing | [asammdf](https://github.com/danielhrisca/asammdf) | 8.x |
| TDMS export | [nptdms](https://github.com/adamreeve/npTDMS) | 1.9+ |
| MATLAB export | [scipy](https://scipy.org) `io.savemat` | 1.12+ |
| Parquet export | [pyarrow](https://arrow.apache.org/docs/python/) | 14.0+ |
| XLSX export | [openpyxl](https://openpyxl.readthedocs.io) | 3.1+ |
| Sidecar packaging | [PyInstaller](https://pyinstaller.org) | 6.x |

See [DEPENDENCIES.md](DEPENDENCIES.md) for a full third-party license audit.

---

## Getting started

### Prerequisites

| Tool | Version | macOS | Windows |
|---|---|---|---|
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` | [rustup.rs](https://rustup.rs) |
| Node.js | ≥ 22 | [nvm](https://github.com/nvm-sh/nvm): `nvm install 22` | [nvm-windows](https://github.com/coreybutler/nvm-windows) |
| Python | ≥ 3.10 | [python.org](https://python.org) or `brew install python@3.12` | [python.org](https://python.org) |
| Xcode CLT | — | `xcode-select --install` | — |
| WebView2 | — | — | Pre-installed on Windows 10/11 |

### First-time setup

```bash
# 1. JS dependencies
npm install

# 2. Python sidecar virtualenv
cd sidecar
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
cd ..
```

### Run in development mode

```bash
# macOS — source toolchains first
source "$HOME/.cargo/env"
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh"

npm run tauri dev
```

This starts Vite (hot-reload UI), compiles the Tauri Rust shell, and launches the Python sidecar automatically using `sidecar/.venv/bin/python3`.

> **After a local release build:** if you ran `tauri build` or a local PyInstaller invocation, the dev wrapper script may have been overwritten by the frozen binary. Restore it with:
> ```bash
> git restore src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
> ```

### Run the test suite

```bash
cd sidecar
source .venv/bin/activate
pytest tests/ -v
```

101 tests across metadata extraction, per-channel statistics, all seven export formats, bus frame decoding preview, and channel filter / exportable-signal enumeration.

### Build a release locally

Build the PyInstaller sidecar first (see [COMMANDS.md](COMMANDS.md) for the full commands), then:

```bash
# macOS arm64
npm run tauri build -- --target aarch64-apple-darwin

# macOS universal
npm run tauri build -- --target universal-apple-darwin

# Windows (run on Windows)
npm run tauri build -- --target x86_64-pc-windows-msvc
```

### Trigger a CI release

```bash
# Bump version in all three files, commit, push, then tag:
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

See [COMMANDS.md](COMMANDS.md) for the complete version-bump, tagging, and release reference.

---

## Architecture

### Sidecar IPC

The Python sidecar communicates with the Rust host via **JSON-RPC 2.0 over stdio** (one JSON line per request/response) using `tauri-plugin-shell`.

```
Svelte UI  →  invoke("command", params)
              ↓
Rust command handler  (src-tauri/src/lib.rs)
              ↓  write JSON-RPC to sidecar stdin
Python sidecar  (sidecar/__main__.py)
              ↓  parse with asammdf / export
Rust command handler
              ↓  return result
Svelte UI
```

Export jobs run in **background daemon threads** inside the sidecar; the UI polls progress via `get_export_progress` every 400 ms.

### JSON-RPC methods

| Method | Purpose |
|---|---|
| `ping` | Health check |
| `open_file` | Parse file, return full metadata + session ID |
| `get_structure` | Return channel groups and channel list |
| `get_signal_stats` | Lazily compute min/max/mean for one channel |
| `preview_bus_decoding` | Count matched messages/signals per DB assignment without decoding |
| `get_exportable_signals` | Enumerate physical + decoded channel groups for the filter picker |
| `start_export` | Start a background export job, return job ID |
| `get_export_progress` | Poll job status (`running` / `done` / `error` / `cancelled`) |
| `cancel_export` | Request job cancellation |
| `close_session` | Release the open MDF object |

### Sidecar modules

| File | Responsibility |
|---|---|
| `__main__.py` | JSON-RPC router; session management |
| `metadata.py` | MDF4 header extraction; HD comment XML parser; finalization & sort state; two-stage bus-type detection |
| `stats.py` | Per-channel min / max / mean / sample count |
| `export.py` | Background-threaded export for all formats; bus decoding via `extract_bus_logging`; channel filter; flatten; MF4 re-export |

---

## Project structure

```
mf4u/
├── SPEC.md                           Feature specification
├── COMMANDS.md                       Dev, build & release command reference
├── DEPENDENCIES.md                   Third-party license audit
├── package.json
├── src/
│   ├── routes/
│   │   └── +page.svelte              App shell, OS menus, session state
│   └── lib/
│       ├── rpc.ts                    Typed Tauri invoke wrappers
│       ├── busColors.ts              Per-bus-type colour tokens
│       └── components/
│           ├── Toolbar.svelte
│           ├── MetadataPanel.svelte
│           ├── SignalTree.svelte
│           ├── ExportDialog.svelte
│           ├── FrameDecodingDialog.svelte
│           ├── ChannelFilterDialog.svelte
│           ├── PreferencesDialog.svelte
│           └── AboutDialog.svelte
├── src-tauri/
│   ├── src/
│   │   ├── main.rs
│   │   └── lib.rs                    Tauri commands + sidecar JSON-RPC relay
│   ├── binaries/                     Dev wrapper shell scripts (git-tracked)
│   ├── capabilities/default.json     Tauri ACL permissions
│   ├── entitlements.macos.plist      cs.disable-library-validation for PyInstaller
│   └── tauri.conf.json
├── sidecar/
│   ├── __main__.py
│   ├── metadata.py
│   ├── stats.py
│   ├── export.py
│   ├── requirements.txt
│   └── tests/
│       ├── conftest.py
│       ├── generate_fixtures.py
│       ├── test_metadata.py
│       ├── test_stats.py
│       ├── test_export.py
│       └── fixtures/                 Synthetic .mf4 files + .dbc (git-tracked)
└── .github/workflows/
    └── release.yml                   macOS universal + Windows CI/CD
```

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE) for full text.

```
SPDX-License-Identifier: MIT
Copyright (c) 2026 Brice LECOLE
```

> **Note on bundled dependencies:** the Python sidecar bundles [asammdf](https://github.com/danielhrisca/asammdf) (LGPL-3.0-or-later) and [nptdms](https://github.com/adamreeve/npTDMS) (LGPL-2.1-or-later). See [DEPENDENCIES.md](DEPENDENCIES.md) for the full license audit and PyInstaller bundling compliance notes.
