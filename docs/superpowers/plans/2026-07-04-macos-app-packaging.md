# Standalone macOS App Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a signed, notarized `chem4all.app` for both Apple Silicon and Intel Macs, built and released automatically via GitHub Actions from a version tag.

**Architecture:** PyInstaller bundles `main.py` and all dependencies into `chem4all.app`. A post-build step uses `dylibbundler` to pull in the Homebrew-installed `libcairo` dylib (which `cairosvg`/`cairocffi` load dynamically at runtime, so PyInstaller's static scanner never sees it), and a PyInstaller runtime hook points `DYLD_FALLBACK_LIBRARY_PATH` at the bundled copy. GitHub Actions builds natively on `macos-14` (arm64) and `macos-13` (Intel), codesigns every bundled dylib plus the app itself, notarizes and staples the result, packages it as a `.dmg`, and attaches both architecture's `.dmg` files to a GitHub Release when a version tag is pushed.

**Tech Stack:** PyInstaller, `pyinstaller-hooks-contrib`, `dylibbundler`, `codesign`/`notarytool`/`stapler` (Xcode command line tools), GitHub Actions.

## Global Constraints

- Support both Apple Silicon (arm64) and Intel (x86_64) Macs — native builds on each, not a universal2 binary (TensorFlow's universal2 wheel support is unreliable).
- Do not bundle the DECIMER model — it continues to download on first use exactly as it does today (`gui/model_manager.py`, unchanged).
- The packaged app must be code-signed and notarized — no Gatekeeper warnings, no right-click-to-open workaround, since recipients are outside the developer's control.
- Python version for the build must stay within `>=3.9,<3.13` (`pyproject.toml:8`) — TensorFlow does not publish wheels for 3.13+.
- Packaging tool is PyInstaller (decided in the spec — not py2app, not Briefcase).
- CI runners: `macos-14` for arm64, `macos-13` for Intel (confirm availability at implementation time — GitHub periodically retires older macOS images; substitute the nearest available Intel image if `macos-13` is gone).
- Out of scope: CLI changes, config/API-key UX changes, Windows/Linux packaging.

---

### Task 1: PyInstaller spec and cairo runtime hook

**Files:**
- Create: `packaging/chem4all.spec`
- Create: `packaging/hooks/rthook_cairo.py`

**Interfaces:**
- Produces: `packaging/chem4all.spec` — the PyInstaller spec file consumed by `pyinstaller packaging/chem4all.spec` in Task 2's build script and Task 4's CI workflow.
- Produces: `packaging/hooks/rthook_cairo.py` — referenced by `runtime_hooks=` in the spec.

- [ ] **Step 1: Create the runtime hook**

```python
# packaging/hooks/rthook_cairo.py
import os
import sys

if getattr(sys, "frozen", False):
    frameworks_dir = os.path.normpath(
        os.path.join(os.path.dirname(sys.executable), "..", "Frameworks")
    )
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
        f"{frameworks_dir}:{existing}" if existing else frameworks_dir
    )
```

This runs before any application code, so by the time `cairosvg` imports `cairocffi` and `cairocffi` calls `ctypes.util.find_library("cairo")`, the bundled `Frameworks/` directory is already on the search path.

- [ ] **Step 2: Create the PyInstaller spec**

```python
# packaging/chem4all.spec
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ["DECIMER", "pystow", "cairosvg", "cairocffi"]

for pkg in ("DECIMER", "cairosvg", "cairocffi", "pystow"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["../main.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=["hooks/rthook_cairo.py"],
    excludes=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="chem4all",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="chem4all")
app = BUNDLE(
    coll,
    name="chem4all.app",
    icon=None,
    bundle_identifier="com.mpfilbin.chem4all",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
    },
)
```

- [ ] **Step 3: Verify the spec parses**

Run: `python -c "import PyInstaller; print('ok')"` to confirm PyInstaller is importable (install it first if needed: `pip install pyinstaller pyinstaller-hooks-contrib`), then:

```bash
cd packaging && python -m py_compile chem4all.spec hooks/rthook_cairo.py && echo OK
```

Expected: `OK` (this only checks the files are valid Python syntax — the full build happens in Task 3).

- [ ] **Step 4: Commit**

```bash
git add packaging/chem4all.spec packaging/hooks/rthook_cairo.py
git commit -m "build: add PyInstaller spec and cairo runtime hook"
```

---

### Task 2: Build script (PyInstaller + dylib bundling + dmg)

**Files:**
- Create: `packaging/build_dmg.sh`
- Create: `packaging/entitlements.plist`

**Interfaces:**
- Consumes: `packaging/chem4all.spec` and `packaging/hooks/rthook_cairo.py` from Task 1.
- Produces: `dist/chem4all.app` (built app bundle) and `chem4all-<version>-<arch>.dmg` in the working directory, consumed by Task 4's CI workflow and Task 9's manual verification.
- Environment contract: if `CODESIGN_IDENTITY` is set in the environment, the script signs; if unset, it produces an unsigned build for local iteration.

- [ ] **Step 1: Create the entitlements file**

```xml
<!-- packaging/entitlements.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
</dict>
</plist>
```

`disable-library-validation` is deliberately omitted — every bundled dylib gets its own signature in Step 3 below, so Hardened Runtime's library validation passes without needing to disable it. `allow-unsigned-executable-memory` is required because TensorFlow JIT-compiles code at runtime.

- [ ] **Step 2: Create the build script**

```bash
#!/usr/bin/env bash
# packaging/build_dmg.sh
set -euo pipefail

VERSION="${1:?Usage: build_dmg.sh <version> <arch>}"
ARCH="${2:?Usage: build_dmg.sh <version> <arch>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Building chem4all.app for ${ARCH}, version ${VERSION}"

pip install --quiet pyinstaller pyinstaller-hooks-contrib
pyinstaller packaging/chem4all.spec --clean --noconfirm --distpath dist --workpath build

APP_PATH="dist/chem4all.app"
CAIRO_LIB="$(brew --prefix cairo)/lib/libcairo.2.dylib"

echo "Bundling cairo and its transitive dependencies..."
dylibbundler -od \
  -x "${APP_PATH}/Contents/MacOS/chem4all" \
  -x "${CAIRO_LIB}" \
  -d "${APP_PATH}/Contents/Frameworks" \
  -p "@executable_path/../Frameworks"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  echo "Codesigning bundled dylibs individually..."
  find "${APP_PATH}/Contents/Frameworks" -name "*.dylib" -print0 \
    | while IFS= read -r -d '' dylib; do
        codesign --force --sign "${CODESIGN_IDENTITY}" --options runtime "${dylib}"
      done

  echo "Codesigning app bundle..."
  codesign --force --deep --options runtime \
    --entitlements packaging/entitlements.plist \
    --sign "${CODESIGN_IDENTITY}" "${APP_PATH}"
else
  echo "CODESIGN_IDENTITY not set — producing an unsigned build for local testing."
fi

DMG_NAME="chem4all-${VERSION}-${ARCH}.dmg"
echo "Creating ${DMG_NAME}..."
hdiutil create -volname "chem4all" -srcfolder "${APP_PATH}" -ov -format UDZO "${DMG_NAME}"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  codesign --force --sign "${CODESIGN_IDENTITY}" "${DMG_NAME}"
fi

echo "Built ${DMG_NAME}"
```

```bash
chmod +x packaging/build_dmg.sh
```

- [ ] **Step 3: Verify the script's syntax**

Run: `bash -n packaging/build_dmg.sh && echo OK`
Expected: `OK` (full execution requires `dylibbundler` and a real build environment — that's Task 3).

- [ ] **Step 4: Commit**

```bash
git add packaging/build_dmg.sh packaging/entitlements.plist
git commit -m "build: add local build script for app bundling and dmg creation"
```

---

### Task 3: Local unsigned build verification

This task has no new files — it validates Tasks 1–2 actually work on real hardware before wiring anything into CI, per the spec's testing plan ("build an unsigned `.app` with plain `pyinstaller` on a local machine first to validate the cairo-bundling fix quickly").

**Files:** none (verification only)

- [ ] **Step 1: Install build-time tools**

```bash
brew install dylibbundler
```

- [ ] **Step 2: Run an unsigned local build**

```bash
./packaging/build_dmg.sh 0.1.0-dev local
```

Expected: completes without error and produces `dist/chem4all.app` and `chem4all-0.1.0-dev-local.dmg`. This step can take several minutes — PyInstaller has to trace TensorFlow's large dependency graph.

- [ ] **Step 3: Verify cairo resolves inside the bundle**

```bash
ls dist/chem4all.app/Contents/Frameworks | grep -i cairo
```

Expected: `libcairo.2.dylib` (or similar) is listed.

- [ ] **Step 4: Launch the built app and confirm it starts**

```bash
open dist/chem4all.app
sleep 5
pgrep -f "dist/chem4all.app/Contents/MacOS/chem4all" && echo "still running"
```

Expected: `still running` — confirms no immediate startup crash (e.g. a missing hidden import). Manually confirm the file picker window appeared, then quit the app.

- [ ] **Step 5: Exercise the SVG/cairo path specifically**

Open a `.pptx` containing at least one SVG or vector image through the built app's file picker, and confirm image extraction doesn't raise a cairo-related error. If it does, the `dylibbundler` invocation in `packaging/build_dmg.sh` Step 2 needs adjustment (e.g. `dylibbundler` version differences can require `-b` for framework bundling, or the search paths in `rthook_cairo.py` may need `DYLD_LIBRARY_PATH` in addition to `DYLD_FALLBACK_LIBRARY_PATH`) — fix and re-run Steps 2–5 until it passes.

- [ ] **Step 6: Clean up local build artifacts**

```bash
rm -rf dist build chem4all-0.1.0-dev-local.dmg
```

(No commit — this task only validates Tasks 1–2; `dist/`, `build/`, and `*.dmg` are already covered by the existing PyInstaller section of `.gitignore`.)

---

### Task 4: GitHub Actions workflow — unsigned matrix build smoke test

**Files:**
- Create: `.github/workflows/release-macos.yml`

**Interfaces:**
- Consumes: `packaging/build_dmg.sh`, `packaging/chem4all.spec` from Tasks 1–2.
- Produces: a `build` job matrix (`arm64`, `x86_64`) that later tasks extend with signing (Task 5), notarization (Task 6), and release publishing (Task 7). Job name `build` and matrix variable `matrix.arch`/`matrix.runner` are relied on by those tasks.

- [ ] **Step 1: Create the workflow with an unsigned build only**

```yaml
# .github/workflows/release-macos.yml
name: Build macOS App

on:
  push:
    tags:
      - "v*"
  workflow_dispatch: {}

jobs:
  build:
    strategy:
      matrix:
        include:
          - arch: arm64
            runner: macos-14
          - arch: x86_64
            runner: macos-13
    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install system dependencies
        run: brew install cairo dylibbundler

      - name: Install Python dependencies
        run: pip install -e .

      - name: Build unsigned app and dmg
        run: ./packaging/build_dmg.sh "${{ github.ref_name }}" "${{ matrix.arch }}"

      - uses: actions/upload-artifact@v4
        with:
          name: chem4all-${{ matrix.arch }}
          path: chem4all-*.dmg
```

- [ ] **Step 2: Verify workflow YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release-macos.yml')); print('OK')"
```

Expected: `OK`. (Install with `pip install pyyaml` if not already available.)

- [ ] **Step 3: Commit and push to trigger a real CI run**

```bash
git add .github/workflows/release-macos.yml
git commit -m "ci: add unsigned macOS build workflow"
git push
```

Then manually trigger it once via GitHub's UI (Actions tab → "Build macOS App" → "Run workflow") since it's not tag-triggered yet on a normal branch push. Confirm both `build (arm64)` and `build (x86_64)` jobs succeed and each uploads a `.dmg` artifact.

---

### Task 5: Wire up code signing (requires one-time manual Apple setup)

This task has a manual prerequisite that only the repo owner can do (it requires their Apple Developer account), followed by workflow changes.

**Files:**
- Modify: `.github/workflows/release-macos.yml`

**Interfaces:**
- Consumes: `build` job and `matrix.arch` from Task 4.
- Produces: a signed `.app`/`.dmg` inside the same `build` job, consumed by Task 6 (notarization).

- [ ] **Step 1 (manual, one-time, done by the repo owner): Export the Developer ID certificate**

In Keychain Access, locate the "Developer ID Application: \<Name\> (\<Team ID\>)" certificate (create one at developer.apple.com → Certificates if it doesn't exist yet), right-click → Export, save as `cert.p12` with a password.

```bash
base64 -i cert.p12 -o cert_base64.txt
```

- [ ] **Step 2 (manual, one-time): Add GitHub Actions secrets**

In the repo's Settings → Secrets and variables → Actions, add:
- `MACOS_CERT_P12` — contents of `cert_base64.txt`
- `MACOS_CERT_PASSWORD` — the password chosen during export
- `CODESIGN_IDENTITY` — the full identity string, e.g. `Developer ID Application: Jane Doe (ABCDE12345)` (find it with `security find-identity -v -p codesigning`)

Delete the local `cert.p12` and `cert_base64.txt` afterward — they must not be committed.

- [ ] **Step 3: Add keychain setup and signing steps to the workflow**

Insert this step in `.github/workflows/release-macos.yml` between "Install Python dependencies" and "Build unsigned app and dmg" (and rename the build step since it's now signed):

```yaml
      - name: Import signing certificate
        env:
          MACOS_CERT_P12: ${{ secrets.MACOS_CERT_P12 }}
          MACOS_CERT_PASSWORD: ${{ secrets.MACOS_CERT_PASSWORD }}
        run: |
          KEYCHAIN_PATH="$RUNNER_TEMP/build.keychain-db"
          KEYCHAIN_PASSWORD="$(uuidgen)"
          echo "$MACOS_CERT_P12" | base64 --decode > "$RUNNER_TEMP/cert.p12"
          security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
          security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security import "$RUNNER_TEMP/cert.p12" -P "$MACOS_CERT_PASSWORD" -A \
            -t cert -f pkcs12 -k "$KEYCHAIN_PATH"
          security set-key-partition-list -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_PATH"
          security list-keychains -d user -s "$KEYCHAIN_PATH" $(security list-keychains -d user | tr -d '"')
          rm "$RUNNER_TEMP/cert.p12"

      - name: Build, sign, and package app
        env:
          CODESIGN_IDENTITY: ${{ secrets.CODESIGN_IDENTITY }}
        run: ./packaging/build_dmg.sh "${{ github.ref_name }}" "${{ matrix.arch }}"
```

Remove the old unsigned "Build unsigned app and dmg" step (replaced by "Build, sign, and package app" above, which is the same `build_dmg.sh` invocation but now with `CODESIGN_IDENTITY` set).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release-macos.yml
git commit -m "ci: sign the built app and dmg with the Developer ID certificate"
```

- [ ] **Step 5: Verify via manual workflow dispatch**

Trigger the workflow manually (Actions tab → "Run workflow") and confirm both jobs succeed. Download one of the artifacts and check:

```bash
codesign --verify --deep --strict chem4all.app
spctl -a -vvv --type execute chem4all.app
```

Expected: `codesign` reports no errors; `spctl` reports `rejected` at this stage is expected (notarization isn't wired up yet — that's Task 6) as long as the reason given is about notarization/Gatekeeper, not a signature failure.

---

### Task 6: Notarization and stapling

**Files:**
- Modify: `.github/workflows/release-macos.yml`

**Interfaces:**
- Consumes: signed `chem4all-<version>-<arch>.dmg` from Task 5, produced in the same working directory by `build_dmg.sh`.
- Produces: a notarized, stapled `.dmg` in the same job, consumed by Task 7 (release publishing).

- [ ] **Step 1 (manual, one-time): Create an App Store Connect API key**

At appstoreconnect.apple.com → Users and Access → Integrations → App Store Connect API, create a key with "Developer" access. Download the `.p8` file (only downloadable once), and note the Key ID and Issuer ID.

- [ ] **Step 2 (manual, one-time): Add GitHub Actions secrets**

```bash
base64 -i AuthKey_XXXXXXXXXX.p8 -o authkey_base64.txt
```

Add secrets:
- `APPLE_API_KEY_ID` — the Key ID
- `APPLE_API_ISSUER` — the Issuer ID
- `APPLE_API_KEY_P8` — contents of `authkey_base64.txt`

Delete the local `.p8` and `authkey_base64.txt` afterward.

- [ ] **Step 3: Add a notarization step to the workflow**

Insert after "Build, sign, and package app" in `.github/workflows/release-macos.yml`:

```yaml
      - name: Notarize dmg
        env:
          APPLE_API_KEY_ID: ${{ secrets.APPLE_API_KEY_ID }}
          APPLE_API_ISSUER: ${{ secrets.APPLE_API_ISSUER }}
          APPLE_API_KEY_P8: ${{ secrets.APPLE_API_KEY_P8 }}
        run: |
          echo "$APPLE_API_KEY_P8" | base64 --decode > "$RUNNER_TEMP/authkey.p8"
          DMG_FILE=$(ls chem4all-*.dmg)
          xcrun notarytool submit "$DMG_FILE" \
            --key "$RUNNER_TEMP/authkey.p8" \
            --key-id "$APPLE_API_KEY_ID" \
            --issuer "$APPLE_API_ISSUER" \
            --wait
          xcrun stapler staple "$DMG_FILE"
          rm "$RUNNER_TEMP/authkey.p8"
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release-macos.yml
git commit -m "ci: notarize and staple the signed dmg"
```

- [ ] **Step 5: Verify via manual workflow dispatch**

Trigger the workflow, download an artifact `.dmg`, and confirm:

```bash
spctl -a -vvv --type install chem4all-*.dmg
```

Expected: output includes `accepted` and `source=Notarized Developer ID`.

---

### Task 7: Release job — publish both dmgs to a GitHub Release

**Files:**
- Modify: `.github/workflows/release-macos.yml`

**Interfaces:**
- Consumes: `chem4all-${{ matrix.arch }}` artifacts uploaded by the `build` job (Tasks 4–6).
- Produces: a GitHub Release for the pushed tag with both `.dmg` files attached.

- [ ] **Step 1: Add a `release` job that runs after `build`**

Append to `.github/workflows/release-macos.yml`:

```yaml
  release:
    needs: build
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Flatten artifact directories
        run: |
          mkdir -p dmgs
          find artifacts -name "*.dmg" -exec mv {} dmgs/ \;

      - uses: softprops/action-gh-release@v2
        with:
          files: dmgs/*.dmg
```

- [ ] **Step 2: Verify workflow YAML syntax**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/release-macos.yml')); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-macos.yml
git commit -m "ci: publish signed, notarized dmgs to a GitHub Release on tag push"
```

- [ ] **Step 4: Verify end-to-end with a real tag**

```bash
git tag v0.1.0
git push origin v0.1.0
```

Watch the Actions tab: both `build` matrix jobs should succeed, followed by `release`. Confirm the GitHub Release for `v0.1.0` has both `chem4all-0.1.0-arm64.dmg` and `chem4all-0.1.0-x86_64.dmg` attached.

---

### Task 8: README updates

**Files:**
- Modify: `README.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add a packaged-app installation path above the existing source-install instructions**

In `README.md`, insert a new subsection right after the `## Installation` heading (before the existing "### 1. Clone the repository"):

```markdown
### Option A: Download the app (recommended for most users)

1. Download the `.dmg` for your Mac from the [latest release](../../releases/latest) — `arm64` for Apple Silicon Macs, `x86_64` for Intel Macs.
2. Open the `.dmg` and drag `chem4all.app` to your Applications folder.
3. Launch chem4all from Applications. No Python, Homebrew, or terminal setup is required — the app is self-contained except for the DECIMER model, which downloads automatically on first use.

### Option B: Run from source (for development)
```

- [ ] **Step 2: Note that Homebrew/cairo is a source-install-only requirement**

In the existing `## Requirements` section, change:

```markdown
- Homebrew (macOS only) — required for the `cairo` system library used for SVG support
```

to:

```markdown
- Homebrew (macOS only, source install only) — required for the `cairo` system library used for SVG support. Not needed if you download the packaged `.app` — cairo is bundled.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document downloading the packaged macOS app"
```

---

### Task 9: End-to-end manual verification

No new files — this is the spec's final manual pre-distribution check, run against the real `v0.1.0` release produced in Task 7.

**Files:** none (verification only)

- [ ] **Step 1: Download the release dmg on a real Mac (not the build machine)**

Download `chem4all-0.1.0-<arch>.dmg` matching that Mac's architecture from the GitHub Release page in a browser (so Gatekeeper's quarantine flag is actually set, replicating a real recipient's experience).

- [ ] **Step 2: Confirm Gatekeeper allows it without warnings**

Double-click the `.dmg`, drag `chem4all.app` to Applications, then double-click the app from Applications.

Expected: the app opens directly with no "unidentified developer" dialog.

- [ ] **Step 3: Run the full pipeline through the GUI**

Open a `.pptx` or `.docx` containing at least one chemical structure image and one SVG image through the app's file picker. Let the DECIMER model download if this is the first run on this machine. Complete image selection, recognition, and review, then confirm the output file has alt-text written back.

Expected: no crashes, no cairo-related errors on the SVG image, and the output file opens correctly with the expected alt-text.

- [ ] **Step 4: Note the outcome**

If any step fails, identify which earlier task's artifact is responsible (build config → Task 1/2, signing → Task 5, notarization → Task 6) and fix there rather than patching around it in this verification task.

---

## Self-Review Notes

- **Spec coverage:** Section 1 (PyInstaller build) → Task 1; Section 2 (cairo bundling) → Tasks 1–3; Section 3 (signing/notarization) → Tasks 5–6; Section 4 (CI workflow & release) → Tasks 4, 7; Section 5 (runtime behavior) → unchanged by design, verified in Task 9; Testing section → Tasks 3 (local), 4–6 (CI smoke checks), 9 (manual pre-distribution check).
- **Placeholder scan:** no TBDs; the two "manual, one-time" steps in Tasks 5–6 are genuine external prerequisites (Apple credentials only the account owner holds), not deferred design work — the exact commands and secret names they produce are specified.
- **Type/name consistency:** `CODESIGN_IDENTITY` env var name is consistent between `packaging/build_dmg.sh` (Task 2) and the workflow secret (Task 5). Job name `build` and matrix key `matrix.arch` introduced in Task 4 are reused unchanged through Tasks 5–7. Artifact name `chem4all-${{ matrix.arch }}` (Task 4) matches the `download-artifact` consumption in Task 7.
