# mf4u — Third-party Dependencies

Third-party libraries used in this project, grouped by language and sorted by
license category: **permissive** (MIT · Apache-2.0 · BSD) first, then **less
permissive** (LGPL).  No GPL-licensed dependencies are present.

Versions shown are the minimum requirement declared in the manifest
(`requirements.txt`, `Cargo.toml`, `package.json`); latest available versions
at audit time are noted for reference.

---

## Python (sidecar)

### Permissive

| Package | Required | Latest audited | License | Use |
|---|---|---|---|---|
| numpy | ≥ 1.26.0 | 2.4.4 | BSD-3-Clause | Numerical arrays |
| scipy | ≥ 1.12.0 | 1.17.1 | BSD-3-Clause | `.mat` export (`scipy.io.savemat`) |
| pyarrow | ≥ 14.0.0 | 23.0.1 | Apache-2.0 | Parquet export |
| openpyxl | ≥ 3.1.0 | 3.1.5 | MIT | `.xlsx` export |
| pytest | ≥ 8.0.0 | 9.0.3 | MIT | Test suite (dev only) |

> **numpy license note:** the core library is BSD-3-Clause; bundled third-party
> components carry 0BSD, MIT, Zlib, and CC0-1.0 — all permissive.

### Less permissive (LGPL)

| Package | Required | Latest audited | License | Use |
|---|---|---|---|---|
| asammdf | ≥ 8.0.0 | 8.8.6 | LGPL-3.0-or-later | MF4/MDF4 file reading (core dependency) |
| nptdms | ≥ 1.9.0 | 1.10.0 | LGPL (unversioned¹) | `.tdms` export |

¹ nptdms declares `LGPL` with no version number in its PyPI metadata.
  The project README and source headers reference LGPL-2.1-or-later in
  practice — treat as **LGPL-2.1-or-later** until upstream clarifies.

#### LGPL compliance note for the PyInstaller release build

The LGPL requires that end-users be able to replace the LGPL library with a
modified version.  When PyInstaller bundles everything with `--onefile`, both
`asammdf` and `nptdms` are statically frozen into a single executable, which
can be seen as a form of static linking.  Recommended mitigations:

- Ship the frozen binary alongside a notice that `asammdf` and `nptdms` are
  included under the LGPL, with links to their source repositories.
- Provide instructions for rebuilding the sidecar from source so users can
  substitute a modified version of either library.
- Alternatively, investigate whether `--onedir` mode (separate `.so`/`.dylib`
  files) satisfies the LGPL "user replaceable" requirement for your
  distribution context.

---

## Rust (Tauri shell)

All Rust crates used in this project are dual-licensed **Apache-2.0 OR MIT**,
which is the standard permissive dual-license in the Rust ecosystem.

| Crate | Required | Latest audited | License | Use |
|---|---|---|---|---|
| tauri | 2 | 2.10.3 | Apache-2.0 OR MIT | Desktop app framework |
| tauri-build | 2 | 2.5.6 | Apache-2.0 OR MIT | Build-time code generation (build dep) |
| tauri-plugin-dialog | 2 | 2.7.0 | Apache-2.0 OR MIT | Native save/open dialogs |
| tauri-plugin-opener | 2 | 2.5.3 | Apache-2.0 OR MIT | Open files / URLs with default app |
| tauri-plugin-shell | 2 | 2.3.5 | Apache-2.0 OR MIT | Sidecar process management |
| tokio | 1 | 1.52.1 | MIT | Async runtime |
| serde | 1 | 1.0.228 | MIT OR Apache-2.0 | Serialisation framework |
| serde_json | 1 | 1.0.149 | MIT OR Apache-2.0 | JSON serialisation |

---

## JavaScript / TypeScript (frontend)

All frontend packages are permissive (MIT or Apache-2.0).
Packages marked **(dev)** are build/type-check tools only — they are not
included in the distributed application bundle.

### Permissive — runtime

| Package | Required | Latest audited | License | Use |
|---|---|---|---|---|
| svelte | ^5.0.0 | 5.55.4 | MIT | UI component framework |
| @tauri-apps/api | ^2 | 2.10.1 | Apache-2.0 OR MIT | Tauri JS bindings |
| @tauri-apps/plugin-dialog | ^2.7.0 | 2.7.0 | Apache-2.0 OR MIT | Dialog plugin JS bindings |
| @tauri-apps/plugin-opener | ^2 | 2.5.3 | Apache-2.0 OR MIT | Opener plugin JS bindings |

### Permissive — dev only

| Package | Required | Latest audited | License | Use |
|---|---|---|---|---|
| @sveltejs/kit | ^2.9.0 | 2.57.1 | MIT | SvelteKit app framework |
| @sveltejs/adapter-static | ^3.0.6 | 3.0.10 | MIT | Static site adapter for SvelteKit |
| @sveltejs/vite-plugin-svelte | ^5.0.0 | 7.0.0 | MIT | Vite plugin for Svelte |
| vite | ^6.0.3 | 8.0.8 | MIT | Frontend bundler / dev server |
| svelte-check | ^4.0.0 | 4.4.6 | MIT | Svelte type checker |
| @tauri-apps/cli | ^2 | 2.10.1 | Apache-2.0 OR MIT | Tauri CLI (dev tooling) |
| typescript | ~5.6.2 | 6.0.3 | Apache-2.0 | TypeScript compiler |

---

## Summary

| Category | Count | Packages |
|---|---|---|
| MIT | 10 | openpyxl, pytest, tokio, serde, serde_json, svelte, @sveltejs/\*, vite, svelte-check |
| Apache-2.0 | 2 | pyarrow, typescript |
| Apache-2.0 OR MIT (dual) | 8 | tauri, tauri-build, tauri-plugin-\* (×3), @tauri-apps/\* (×4) |
| BSD-3-Clause | 2 | numpy¹, scipy |
| **LGPL** | **2** | **asammdf (LGPL-3.0+), nptdms (LGPL-2.1+)** |

¹ numpy also bundles components under 0BSD, MIT, Zlib, and CC0-1.0.

---

*Audited: 2026-04-19.  Re-audit when upgrading any LGPL dependency.*
