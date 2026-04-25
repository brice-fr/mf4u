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

## Git & GitHub housekeeping

### Everyday workflow — save a change locally

```bash
# 1. See what changed (files modified / new / deleted)
git status

# 2. Stage the files you want to include in the commit
#    Stage a specific file:
git add src/lib/components/MetadataPanel.svelte

#    Stage everything in the current directory:
git add .

# 3. Commit with a message
git commit -m "fix: clear BUS_EVENT flag on decoded MF4 groups"

# 4. Check the log to confirm
git log --oneline -5
```

> **Tip:** use a short prefix to keep the history readable:
> `feat:` new feature · `fix:` bug fix · `refactor:` code cleanup ·
> `test:` test-only change · `docs:` docs only · `chore:` housekeeping

---

### Push a local commit to GitHub

```bash
# Push the current branch to its upstream remote branch
git push

# First-ever push of a new branch (sets the upstream tracking reference)
git push -u origin main
```

---

### Bump the version number

The version lives in **three files** — keep them in sync:

| File | Field |
|---|---|
| `package.json` | `"version": "…"` |
| `src-tauri/tauri.conf.json` | `"version": "…"` |
| `src-tauri/Cargo.toml` | `version = "…"` |

**Option A — Edit manually** (open each file, find the `version` line, type the new value).

**Option B — One-liner on macOS/Linux** (replace `0.1.0` with current, `0.2.0` with new):
```bash
OLD=0.1.0
NEW=0.2.0

# macOS sed requires the empty-string argument after -i
sed -i '' "s/\"version\": \"$OLD\"/\"version\": \"$NEW\"/" package.json
sed -i '' "s/\"version\": \"$OLD\"/\"version\": \"$NEW\"/" src-tauri/tauri.conf.json
sed -i '' "s/^version = \"$OLD\"/version = \"$NEW\"/"     src-tauri/Cargo.toml

# Verify all three changed
grep '"version"' package.json src-tauri/tauri.conf.json
grep '^version'  src-tauri/Cargo.toml
```

> After bumping, commit the three files together:
> ```bash
> git add package.json src-tauri/tauri.conf.json src-tauri/Cargo.toml
> git commit -m "chore: bump version to 0.2.0"
> git push
> ```

---

### Tag a version and trigger the CI release

The release workflow (`release.yml`) starts automatically when a tag of the
form `v0.2.0` is pushed to GitHub.  It builds the macOS and Windows installers
and creates a **draft** release — nothing is public yet.

```bash
# 1. Make sure your local main is up to date and clean
git status            # should say "nothing to commit"
git pull              # pull any remote changes

# 2. Create an annotated tag (the message appears on the GitHub release page)
git tag -a v0.2.0 -m "Release v0.2.0"

# 3. Push the tag — this fires the CI workflow immediately
git push origin v0.2.0

# Verify the tag was pushed
git ls-remote --tags origin
```

> **Annotated vs lightweight tags:** `-a` (annotated) tags include author,
> date, and a message — always prefer these for releases.  Plain
> `git tag v0.2.0` (no `-a`) creates a lightweight tag that still works but
> carries no metadata.

#### Alternatively — trigger without pushing a tag (manual dispatch)

If you want to run the release workflow without creating a permanent tag
(useful for testing CI):

1. Go to **GitHub → Actions → Release** workflow.
2. Click **Run workflow**.
3. Type the tag name (e.g. `v0.2.0`) in the input field and click **Run workflow**.

> This does *not* push a git tag to the repository; the artifacts are uploaded
> to a draft release but you must create the tag separately if you want it in
> the git history.

---

### Monitor the CI build

After pushing the tag, the workflow runs three parallel jobs and then
assembles the release:

```
sidecar-macos-arm64  ──┐
                        ├──► release-macos  (signs + notarises + uploads DMGs)
sidecar-macos-x86_64 ──┘
release-windows             (builds NSIS installer + uploads to same draft)
```

Watch progress:  **GitHub → Actions → Release** — click the run that appeared
after your `git push`.  The whole pipeline takes roughly 15–25 minutes.

---

### Publish the draft release

Once all CI jobs are green the release exists as a **draft** — only you can
see it.  To make it public:

1. Go to **GitHub → Releases** (side panel on the repo home page, or
   `https://github.com/<you>/mf4u/releases`).
2. Find the draft labelled **mf4u v0.2.0** and click the pencil ✏️ icon.
3. Review the auto-generated release notes / body text; edit if needed.
4. Click **Publish release**.

The release is now public and the download links are live.

---

### Useful tag management commands

```bash
# List all local tags
git tag

# List tags with their messages
git tag -n

# Delete a local tag (e.g. if you mis-typed it before pushing)
git tag -d v0.2.0-typo

# Delete a tag from GitHub (use with care — breaks any release that references it)
git push origin --delete v0.2.0-typo

# Move a tag to a different commit (delete + re-create)
git tag -d v0.2.0
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin --delete v0.2.0
git push origin v0.2.0
```

---

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
