# mf4u — Development & Build Commands

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 22 | `nvm install 22` |
| Rust | stable | `rustup update stable` |
| Python | ≥ 3.10 | system or pyenv |

> **macOS:** always source the toolchains first:
> ```bash
> source "$HOME/.cargo/env"
> export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh"
> ```

---

## First-time setup

```bash
# 1. JS dependencies
npm install

# 2. Python sidecar virtualenv (only needed once)
cd sidecar
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
cd ..
```

---

## Development

### Start the full app (Tauri + hot-reload UI)

The dev wrapper script (`src-tauri/binaries/mf4u_sidecar-*`) **auto-detects the
venv** at `sidecar/.venv` — no manual activation needed.  Tauri copies the
script to `src-tauri/target/debug/` at build time and runs it from there; the
script walks upward to find the project root automatically.  Just run:

```bash
# macOS — source toolchains first, then launch
source "$HOME/.cargo/env"
export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh"
cd ~/mf4u
npm run tauri dev
```

That single command starts Vite (hot-reload UI), compiles the Tauri Rust shell,
and spawns the Python sidecar using `sidecar/.venv/bin/python3` automatically.

> **Prerequisite:** the venv must exist with asammdf installed (see First-time
> setup above). If the venv is missing, the sidecar falls back to system Python
> which won't have asammdf — file-open will fail with an import error.

### Start the full app (one-liner, all env setup included)
```bash
source "$HOME/.cargo/env" && \
  export NVM_DIR="$HOME/.nvm" && source "$NVM_DIR/nvm.sh" && \
  cd ~/mf4u && \
  npm run tauri dev
```

### Frontend only (browser, no Tauri APIs)
```bash
npm run dev
# open http://localhost:5173
```

### Type-check the Svelte frontend
```bash
npm run check
```

### Rust type-check only (fast)
```bash
cd src-tauri && cargo check
```

### Test the Python sidecar directly
```bash
# Ping
echo '{"jsonrpc":"2.0","method":"ping","id":1}' | python3 sidecar/__main__.py

# Open a file
echo '{"jsonrpc":"2.0","method":"open_file","params":{"path":"/path/to/file.mf4"},"id":2}' \
  | python3 sidecar/__main__.py
```

### Run Python sidecar tests
```bash
cd sidecar
source .venv/bin/activate
pytest tests/ -v
```

---

## Release build

> **Important — build the PyInstaller sidecar binary first.**
> The dev-mode wrapper script in `src-tauri/binaries/` only works for
> `npm run tauri dev`.  Any `tauri build` invocation must find a real
> frozen binary there or the packaged app will throw *broken pipe* on
> launch.  See the **Python sidecar — PyInstaller release binary** section
> below for the exact commands, then come back here.

### macOS — arm64 (Apple Silicon)
```bash
# 1. Build arm64 sidecar (see PyInstaller section below)
# 2. Build the app
npm run tauri build -- --target aarch64-apple-darwin
# Output: src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/
```

### macOS — x86_64 (Intel)
```bash
# 1. Build x86_64 sidecar via Rosetta 2 (see PyInstaller section below)
# 2. Build the app
rustup target add x86_64-apple-darwin   # only needed once
npm run tauri build -- --target x86_64-apple-darwin
# Output: src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/
```

### macOS — Universal binary (arm64 + x86_64)
```bash
# 1. Build both arch sidecars and lipo-merge them (see PyInstaller section below)
# 2. Build the app
rustup target add x86_64-apple-darwin   # only needed once
npm run tauri build -- --target universal-apple-darwin
# Output: src-tauri/target/universal-apple-darwin/release/bundle/dmg/
```

### Windows — x86_64 (run on Windows or CI)
```powershell
# 1. Build the Windows sidecar (see PyInstaller section below)
# 2. Build the app
npm run tauri build -- --target x86_64-pc-windows-msvc
# Output: src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/
```

---

## Python sidecar — PyInstaller release binary

The dev-mode wrapper script in `src-tauri/binaries/` delegates to the Python
source tree and **only works with `npm run tauri dev`**.  For any packaged
release build the wrapper must be replaced with a PyInstaller-frozen binary.

> **Why `--hidden-import`?**  `metadata`, `stats`, and `export` are imported
> lazily inside handler functions.  PyInstaller's static analyser may not trace
> them through `try/except` blocks, so we declare them explicitly.
>
> **Why `--collect-all`?**  `asammdf`, `canmatrix`, and `pyarrow` rely on
> data files, native extensions, and sub-packages that PyInstaller won't bundle
> unless told to collect everything.

> ⚠️ **Local PyInstaller builds overwrite the dev wrapper script.**
> The `cp dist/mf4u_sidecar ../src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin`
> step replaces the shell-script dev wrapper with the frozen Mach-O binary.
> After a local release build, **`npm run tauri dev` will break** (the frozen
> binary expects a different launch path).
>
> To restore the dev wrapper after a local release build:
> ```bash
> git restore src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
> ```
> The dev wrappers are tracked by git (see `.gitignore`) precisely to make this
> recovery instant.  If you accidentally committed the binary, run
> `git checkout HEAD -- src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin`
> instead.

### macOS — arm64 (Apple Silicon)
```bash
cd sidecar
source .venv/bin/activate
pip install pyinstaller

pyinstaller --onefile --clean \
  --name mf4u_sidecar \
  --collect-all asammdf \
  --collect-all canmatrix \
  --collect-all pyarrow \
  --hidden-import metadata \
  --hidden-import stats \
  --hidden-import export \
  __main__.py

cp dist/mf4u_sidecar \
   ../src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
chmod +x ../src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
cd ..
```

### macOS — x86_64 (Intel, built via Rosetta 2 on Apple Silicon)

macOS 13 (Intel) GitHub runners are no longer available, and building a true
Intel binary requires an Intel Mac or Rosetta 2.  On an Apple Silicon machine
the system Python from `actions/setup-python` is a universal2 binary — invoking
it with `arch -x86_64` makes pip resolve x86_64 wheels and PyInstaller emit an
x86_64-only executable.

```bash
cd sidecar

# Capture the universal2 Python that setup-python (or Homebrew) provides
PY=$(python3 -c "import sys; print(sys.executable)")

arch -x86_64 "$PY" -m pip install --upgrade pip
arch -x86_64 "$PY" -m pip install -r requirements.txt pyinstaller

arch -x86_64 "$PY" -m PyInstaller --onefile --clean \
  --name mf4u_sidecar \
  --collect-all asammdf \
  --collect-all canmatrix \
  --collect-all pyarrow \
  --hidden-import metadata \
  --hidden-import stats \
  --hidden-import export \
  __main__.py

lipo -info dist/mf4u_sidecar   # must say: x86_64

cp dist/mf4u_sidecar \
   ../src-tauri/binaries/mf4u_sidecar-x86_64-apple-darwin
chmod +x ../src-tauri/binaries/mf4u_sidecar-x86_64-apple-darwin
cd ..
```

### macOS — Universal (lipo-merge after building both arches above)
```bash
lipo -create \
  src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin \
  src-tauri/binaries/mf4u_sidecar-x86_64-apple-darwin \
  -output src-tauri/binaries/mf4u_sidecar-universal-apple-darwin
chmod +x src-tauri/binaries/mf4u_sidecar-universal-apple-darwin
lipo -info src-tauri/binaries/mf4u_sidecar-universal-apple-darwin
# must say: x86_64 arm64
```

### Windows — x86_64
```powershell
cd sidecar
.\.venv\Scripts\activate
pip install pyinstaller

pyinstaller --onefile --clean `
  --name mf4u_sidecar `
  --collect-all asammdf `
  --collect-all canmatrix `
  --collect-all pyarrow `
  --hidden-import metadata `
  --hidden-import stats `
  --hidden-import export `
  __main__.py

copy dist\mf4u_sidecar.exe `
     ..\src-tauri\binaries\mf4u_sidecar-x86_64-pc-windows-msvc.exe
```

> **Size note:** expect ~60–80 MB for the frozen binary (Python + asammdf +
> numpy + pyarrow).  This is normal; PyInstaller bundles the full interpreter.

---

## Code signing (release)

### macOS (notarization)
```bash
# Set in environment before tauri build:
export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="app-specific-password"
export APPLE_TEAM_ID="XXXXXXXXXX"

npm run tauri build -- --target aarch64-apple-darwin
```

### Windows (Authenticode)
Set `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` in the
environment, or configure `bundle.windows.certificateThumbprint` in `tauri.conf.json`.

---

## Useful one-liners

```bash
# Check installed Rust targets
rustup target list --installed

# Add a missing target
rustup target add x86_64-apple-darwin
rustup target add x86_64-pc-windows-msvc

# Wipe Rust build cache (frees disk space)
cd src-tauri && cargo clean

# Check npm outdated packages
npm outdated
```
