# mf4u — mf4 utility

A desktop MF4 / MDF file inspector and exporter, built with Tauri 2, SvelteKit, and a Python sidecar powered by [asammdf](https://github.com/danielhrisca/asammdf).

Supports opening `.mf4` and `.mdf` files, browsing their channel-group hierarchy, loading per-channel statistics on demand, and exporting all physical signals to **MATLAB `.mat`** or **NI TDMS `.tdms`** format.

---

## Features

### File Opening
- **Open** `.mf4` / `.mdf` files via the toolbar button, the **File → Open…** menu item, or the keyboard shortcut **⌘O** / **Ctrl+O**
- **Drag and drop** any `.mf4` or `.mdf` file directly onto the window
- The toolbar Open button displays a **spinner** during the load; the button is disabled until the file is fully parsed
- The OS window title updates to **`<filename> — mf4 utility`** while a file is open and resets to `mf4 utility` on close

### Inspector Pane
The left panel presents structured metadata extracted from the MDF4 header, organised into cards:

#### File
| Field | Description |
|---|---|
| File | Base filename |
| Size | Human-readable file size (B / KB / MB / GB) |
| MDF version | MDF standard version string from the file header |

#### Timing
| Field | Description |
|---|---|
| Start | Recording start timestamp (locale-formatted, millisecond precision) |
| End | Recording end timestamp |
| Duration | Total recording duration (auto-scaled: ms / s / m / h) |

#### Structure
| Field | Description |
|---|---|
| Total channel groups | Total number of channel groups (including empty ones) |
| Non-empty groups | Groups that contain at least one channel |
| Total signals | Sum of all channels across all groups |
| Physical signals | Channels belonging to groups that are **not** raw bus-frame groups |

#### Bus Frames
Shown only when the file contains bus-logged data. One row per detected bus type, each label colour-coded to match the signal tree badges:

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
Lists any embedded attachment filenames; hidden when none are present.

#### Comment
Full recording comment rendered in a scrollable monospace block; hidden when absent.

---

### Signal Tree
The right panel is a collapsible channel-group hierarchy, always visible when a file is loaded.

#### Filter bar
- **Live search input** at the top of the tree filters channel names across all groups as you type (case-insensitive substring match)
- A **group · signal summary** counter sits to the right of the filter input

#### Group rows
Each group is rendered as a single clickable row:

| Element | Meaning |
|---|---|
| **▸ / ▾ chevron** | Collapsed / expanded state; click anywhere on the row to toggle |
| **Acquisition name** | The `acq_name` field from the MDF4 channel-group block, or `Group N` if absent |
| **Bus-type badge** | Colour-coded pill showing the detected bus type (e.g. `CAN FD`) — see colour table above |
| **`raw frames` badge** | Muted grey pill shown alongside the bus badge; indicates this group holds raw bus frames, not decoded physical values |
| **`phy` badge** (red) | Shown on non-raw-frames groups that contain at least one physical channel |
| **Channel count** | Right-aligned tabular numeral count; fixed 4-character width so all counts stay column-aligned regardless of magnitude |

#### Bus-type detection
mf4u uses a two-stage detection strategy to correctly identify bus-frame groups:

1. **Channel-name matching** — checks for the presence of well-known MDF4 bus-logging channel names (`CAN_DataFrame`, `LIN_Frame`, `MOST_Message`, etc.).  CAN FD is distinguished from plain CAN by the presence of the FD-specific sub-signals `CAN_DataFrame.BRS` and `CAN_DataFrame.EDL`.
2. **`acq_source.bus_type` field** — reads the acquisition source metadata from the channel-group block using asammdf's v4 constants (`BUS_TYPE_CAN=2`, `BUS_TYPE_LIN=3`, `BUS_TYPE_MOST=4`, etc.).

Both methods are combined: a group is tagged with whichever bus type either method detects first.

#### Channel rows (expanded group)
Expanding a group reveals one row per channel, laid out in a fixed grid:

| Column | Content |
|---|---|
| **Name** | Channel name; truncated with ellipsis if too long; the full name and comment are shown in a tooltip on hover |
| **`phy` badge** | Red pill present when the channel has a non-empty unit string **or** a non-trivial conversion rule (linear with a ≠ 1 or b ≠ 0, rational, algebraic, look-up table, etc.) |
| **Unit** | Physical unit string, right-aligned |
| **Statistics** | Shows `n=` (sample count), `min=`, `max=`, `μ=` once loaded; hidden until requested |
| **`stats` button** | Small grey pill button; click to load statistics for that channel on demand (lazy — no data is read at open time) |

Statistics are fetched asynchronously from the Python sidecar and cached for the session. A `…` placeholder is shown while the request is in flight; errors are surfaced inline with a ⚠ prefix.

---

### Export Dialog
Opened via **File → Export…** (⌘E / Ctrl+E) or the Export toolbar button; only enabled when a file is loaded.

- **Format selector** — choose between **TDMS** (NI LabVIEW format, `.tdms`) or **MAT** (MATLAB format, `.mat`)
- **Output path** — text field populated by the native OS **Save As** dialog (Browse button); pre-fills the current filename with the chosen extension
- **Progress bar** — live fill showing export progress once started; below it: `{done}/{total} groups ({pct}%)`
- **Cancel** — stops the background export thread; the partial output file is removed
- **Export / Close / Cancel** buttons are shown contextually based on current state (idle / running / done / cancelled / error)

Export runs in a Python background thread and does not block the UI. Signals from raw bus-frame groups are exported verbatim (no decoding); physical groups are exported with calibrated values.

---

### Status Bar
A 22 px strip at the very bottom of the window, visible whenever a file is loaded:

```
3 groups · 142 signals · 47 physical · 2 empty groups     hide empty groups · expand all · collapse all
```

| Left section | Content |
|---|---|
| `N groups` | Total group count in the loaded file |
| `N signals` | Total channel count |
| `N physical` | Channels in non-raw-frames groups |
| `N empty groups` | Groups with zero channels — shown only when present |

| Right section — action links | Behaviour |
|---|---|
| **hide empty groups** / **show empty groups** | Toggles visibility of zero-channel groups in the tree; link is hidden entirely when the file has no empty groups |
| **expand all** | Opens every group in the tree simultaneously |
| **collapse all** | Closes every group |

---

### OS Integration

#### Toolbar
A slim 36 px icon bar sits below the OS title bar at all times:

| Button | Icon | Shortcut | State |
|---|---|---|---|
| Open | Folder-open | ⌘O / Ctrl+O | Shows spinner while loading |
| Export | Document with down-arrow | ⌘E / Ctrl+E | Disabled until a file is loaded |

#### Native menu bar (macOS)
| Menu | Items |
|---|---|
| **mf4u** | About mf4u, Services, Hide mf4u, Hide Others, Show All, Quit |
| **File** | Open… `⌘O`, Export… `⌘E`, ─, Close Window |
| **Help** | About mf4u |

On Windows and Linux the About item appears under Help; the app menu is omitted.

#### About dialog
Shows the app icon, the `mf4u` / `u` two-colour wordmark, the `mf4 utility` subtitle, the version number (read from `package.json` at build time), and the copyright line.

---

## Distribution

### Packaged releases
Pre-built installers are published on the [Releases](../../releases) page via GitHub Actions:

| Platform | Artifact | Architecture |
|---|---|---|
| macOS | `.dmg` universal installer | Apple Silicon + Intel (arm64 + x86_64) |
| Windows | `.exe` NSIS installer | x86_64 |

The macOS app is **code-signed** with a Developer ID Application certificate and **notarized** through Apple's notarization service; Gatekeeper will open it without a quarantine warning.

### GitHub Actions workflow
Triggered by pushing a `v*` tag (or manually via workflow dispatch):

1. **sidecar-macos-arm64** — builds the Python sidecar with PyInstaller on `macos-14` (arm64)
2. **sidecar-macos-x86_64** — builds the Python sidecar with PyInstaller on `macos-13` (Intel)
3. **release-macos** — downloads both sidecar artifacts, joins them into a fat universal binary with `lipo`, imports the Developer ID certificate into a temporary keychain, builds a universal Tauri app, signs and notarizes, publishes to the GitHub Release draft
4. **release-windows** — builds the sidecar with PyInstaller on `windows-latest`, builds the Tauri NSIS installer, publishes to the same release draft

The release is created as a **draft**; review and publish it manually on GitHub.

---

## Development Toolchain

| Component | Technology | Version |
|---|---|---|
| App framework | [Tauri 2](https://tauri.app) | 2.x |
| Frontend | [SvelteKit](https://kit.svelte.dev) + [Svelte 5](https://svelte.dev) | 5.x runes |
| Build tool | [Vite](https://vitejs.dev) | 6.x |
| Rust backend | [Rust](https://rust-lang.org) | stable |
| MDF4 parsing | [asammdf](https://github.com/danielhrisca/asammdf) | 8.x |
| TDMS export | [nptdms](https://github.com/adamreeve/npTDMS) | 1.9+ |
| MATLAB export | [scipy.io.savemat](https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.savemat.html) | 1.12+ |
| Sidecar packaging | [PyInstaller](https://pyinstaller.org) | 6.x |
| Native dialogs | `@tauri-apps/plugin-dialog` | 2.x |
| Shell / sidecar IPC | `@tauri-apps/plugin-shell` | 2.x |

---

## Getting Started

### Prerequisites

| Tool | macOS | Windows |
|---|---|---|
| Rust toolchain | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` | [rustup.rs](https://rustup.rs) |
| Node.js LTS | [nvm](https://github.com/nvm-sh/nvm) or [nodejs.org](https://nodejs.org) | [nvm-windows](https://github.com/coreybutler/nvm-windows) |
| Python 3.12+ | [python.org](https://python.org) or `brew install python@3.12` | [python.org](https://python.org) |
| Xcode CLT | `xcode-select --install` | — |
| WebView2 | — | pre-installed on Windows 10/11 |

### Build the Python sidecar (required before first run)

The Tauri app expects a native executable at `src-tauri/binaries/mf4u_sidecar-<target-triple>`.  Build it once with PyInstaller:

```bash
# Install sidecar dependencies
pip install -r sidecar/requirements.txt pyinstaller

# Build (run from the repo root)
cd sidecar
pyinstaller --onefile --clean \
  --name mf4u_sidecar \
  --collect-all asammdf \
  __main__.py
cd ..

# macOS arm64
cp sidecar/dist/mf4u_sidecar \
   src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin

# macOS x86_64
cp sidecar/dist/mf4u_sidecar \
   src-tauri/binaries/mf4u_sidecar-x86_64-apple-darwin

# Windows
copy sidecar\dist\mf4u_sidecar.exe ^
     src-tauri\binaries\mf4u_sidecar-x86_64-pc-windows-msvc.exe
```

### Run in development mode

```bash
npm install
npm run tauri dev
```

Hot-reload is active for the SvelteKit frontend.  Changes to the Python sidecar require re-running the PyInstaller step above.

### Build a release locally

```bash
npm run tauri build
# macOS  → src-tauri/target/release/bundle/dmg/
# Windows → src-tauri/target/release/bundle/nsis/
```

### Trigger a CI release

```bash
# Bump version in package.json and src-tauri/tauri.conf.json first, then:
git tag v0.2.0
git push origin v0.2.0
```

The GitHub Actions workflow builds and publishes a draft release for both platforms automatically.

---

## Architecture

### Sidecar IPC
The Python sidecar (`sidecar/`) communicates with the Rust host via **JSON-RPC 2.0 over stdio** using `tauri-plugin-shell`.  Each request is a single JSON line on stdin; each response is a single JSON line on stdout.

```
Svelte frontend
    │  invoke("command", params)
    ▼
Rust command handler  (src-tauri/src/lib.rs)
    │  write JSON-RPC request to sidecar stdin
    ▼
Python sidecar  (sidecar/__main__.py)
    │  parse MDF4 with asammdf
    ▼
Rust command handler
    │  return result
    ▼
Svelte frontend
```

### Sidecar modules

| File | Responsibility |
|---|---|
| `__main__.py` | JSON-RPC router; session management (`SESSIONS` dict); `_is_phy()` helper |
| `metadata.py` | MDF4 header extraction; `group_bus_type()` two-stage bus detection |
| `stats.py` | Per-channel min / max / mean / sample count (loads samples lazily) |
| `export.py` | Background-threaded TDMS and MAT export with progress tracking and cancellation |

---

## Project Structure

```
mf4u/
├── src/                              # SvelteKit frontend
│   ├── lib/
│   │   ├── rpc.ts                    # Typed Tauri invoke wrappers
│   │   ├── busColors.ts              # Per-bus-type colour tokens
│   │   └── components/
│   │       ├── MetadataPanel.svelte  # Left inspector pane
│   │       ├── SignalTree.svelte     # Right channel-group tree
│   │       ├── Toolbar.svelte        # Icon toolbar (Open, Export)
│   │       ├── ExportDialog.svelte   # TDMS / MAT export with progress
│   │       └── AboutDialog.svelte    # About modal
│   └── routes/
│       └── +page.svelte              # App shell, OS menus, status bar
├── src-tauri/
│   ├── src/
│   │   ├── main.rs                   # Entry point
│   │   └── lib.rs                    # Tauri builder + Rust command handlers
│   ├── binaries/                     # Compiled sidecar executables (gitignored)
│   │   └── .gitkeep
│   ├── capabilities/
│   │   └── default.json              # Tauri ACL permissions
│   ├── icons/                        # Full icon set (.icns, .ico, .png)
│   └── tauri.conf.json               # App configuration
├── sidecar/                          # Python sidecar
│   ├── __main__.py                   # JSON-RPC 2.0 entry point & router
│   ├── metadata.py                   # MDF4 metadata + bus-type detection
│   ├── stats.py                      # Channel statistics
│   ├── export.py                     # TDMS + MAT export engine
│   └── requirements.txt              # Python dependencies
├── static/                           # Web-accessible static assets
├── .github/workflows/
│   └── release.yml                   # macOS universal + Windows CI/CD
├── vite.config.js
├── svelte.config.js
├── package.json
└── README.md
```

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE) for full text.

```
SPDX-License-Identifier: MIT
Copyright (c) 2026 Brice LECOLE
```
