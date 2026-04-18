# mf4u — Development & Build Commands

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 20 | `nvm install 24` |
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
venv** at `sidecar/.venv` — no manual activation needed. Just run:

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

### macOS — arm64 (Apple Silicon)
```bash
npm run tauri build -- --target aarch64-apple-darwin
# Output: src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/
```

### macOS — x86_64 (Intel)
```bash
npm run tauri build -- --target x86_64-apple-darwin
# Output: src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/
```

### macOS — Universal binary (arm64 + x86_64)
```bash
# Add target first if not present:
rustup target add x86_64-apple-darwin

# Build both sidecar binaries first (PyInstaller, see below), then:
npm run tauri build -- --target universal-apple-darwin
# Output: src-tauri/target/universal-apple-darwin/release/bundle/dmg/
```

### Windows — x86_64 (run on Windows or CI)
```bash
npm run tauri build -- --target x86_64-pc-windows-msvc
# Output: src-tauri/target/x86_64-pc-windows-msvc/release/bundle/msi/
```

---

## Python sidecar — PyInstaller release binary

The dev wrapper script in `src-tauri/binaries/` must be replaced with a frozen
binary before shipping. Run this once per platform:

### macOS arm64
```bash
cd sidecar
source .venv/bin/activate
pip install pyinstaller

pyinstaller \
  --onefile \
  --name mf4u_sidecar \
  --exclude-module tkinter \
  --exclude-module matplotlib \
  --exclude-module pandas \
  __main__.py

# Copy to Tauri binaries dir with platform triple
cp dist/mf4u_sidecar \
   ../src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
chmod +x ../src-tauri/binaries/mf4u_sidecar-aarch64-apple-darwin
```

### macOS x86_64
```bash
# Same as above but run on Intel Mac or under Rosetta, then:
cp dist/mf4u_sidecar \
   ../src-tauri/binaries/mf4u_sidecar-x86_64-apple-darwin
```

### Windows x86_64
```powershell
cd sidecar
.\.venv\Scripts\activate
pip install pyinstaller

pyinstaller `
  --onefile `
  --name mf4u_sidecar `
  --exclude-module tkinter `
  __main__.py

copy dist\mf4u_sidecar.exe `
     ..\src-tauri\binaries\mf4u_sidecar-x86_64-pc-windows-msvc.exe
```

> **Tip:** use `--strip` on macOS and `--upx-dir` on Windows to reduce bundle size.
> Expect ~50 MB for the frozen binary (Python + asammdf + numpy).

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
