# Design: Standalone macOS App Packaging

## Context

chem4all currently requires cloning the repo, running `setup.sh` (installs a system `cairo` library via Homebrew, then `pip install -e .`), and launching via `python main.py` or the `chem4all` console script. This is unworkable for distributing the app to instructors who aren't comfortable with a Python dev environment.

Goal: produce a signed, notarized `chem4all.app` that a recipient can double-click to run, with no Python, Homebrew, or terminal setup on their end.

Constraints established during design:
- **Target Apple Silicon (arm64) Macs only for now.** Intel Mac and Windows (arm64/x64) support are planned follow-ups, not part of this effort — see "Future platforms" below. Architecture-specific naming (`chem4all-<version>-arm64.dmg`) is used from the start so adding Intel later doesn't require a breaking rename.
- The DECIMER model (~500 MB) is **not** bundled — it continues to download on first use, as it does today. The app itself stays small and this matches current behavior.
- Recipients are instructors/users outside the developer's control, so the app must be code-signed and notarized (an Apple Developer Program membership is already in place) — no Gatekeeper warnings or right-click workarounds.
- Builds happen on GitHub Actions using a native `arm64` macOS runner rather than a universal2 build. TensorFlow (a DECIMER dependency) does not have reliable universal2 wheel support, so a native-architecture build is the reliable path — and also the right shape to extend to a second (Intel) matrix leg later with minimal change.
- Packaging tool: **PyInstaller**. Chosen over py2app (weaker dependency-scanning for large native packages like TensorFlow — `modulegraph` misses dynamically-loaded native extensions) and Briefcase (project-template-based, no first-class handling for arbitrary native dylibs like cairo, not designed for this dependency mix). PyInstaller has a maintained TensorFlow hook and the largest body of prior art for this exact combination (Qt + TensorFlow).

Out of scope: bundling the DECIMER model, changes to the CLI (`--review`, etc.), changes to config/API-key UX (already functional), Intel Mac packaging, Windows packaging.

### Future platforms

Intel Mac and Windows (arm64/x64) packaging are explicitly deferred, not abandoned. When picked up:
- **Intel Mac** slots into Section 4's CI matrix as a second `macos-13`-or-nearest-available job (see the original multi-arch version of this section in git history, commit `c22a36d`, for the once-planned shape); Sections 1-3 (spec, cairo bundling, signing) are architecture-agnostic and should need no changes.
- **Windows** is a materially different effort — different packaging tool considerations (PyInstaller still applies, but no cairo/Homebrew equivalent, different signing mechanism — Authenticode instead of Developer ID/notarization), and deserves its own design pass rather than an extension of this spec.

---

## Section 1 — PyInstaller build

One `.spec` file, built on an `arm64` runner in CI. Entry point is the existing `main.py` — no code changes needed there, since double-clicking the app bundle invokes the executable with no `argv`, and `main.py`'s existing `if args.file is None: _launch_gui(config)` branch already handles that case.

Build invocation:
```bash
pip install pyinstaller pyinstaller-hooks-contrib
pyinstaller chem4all.spec --clean --noconfirm
```

`chem4all.spec` key settings:
- `--windowed` (no terminal window)
- `hiddenimports` covering `DECIMER`, `pystow`, `cairosvg`/`cairocffi` as needed (PyInstaller's static scanner can miss dynamic imports in these packages)
- App icon, bundle identifier (`com.<org>.chem4all`), version pulled from the git tag at build time

## Section 2 — Bundling the cairo system library

`cairosvg` → `cairocffi` locates `libcairo` via `ctypes.util.find_library` at runtime, which PyInstaller's static import scanner cannot see, so it isn't bundled automatically. This is the one real technical risk in the build and needs to work before signing is even attempted.

Fix, applied as a post-`pyinstaller` step in the build:
1. `brew install dylibbundler`
2. Run `dylibbundler` against the built `.app`, pointed at the Homebrew-installed `libcairo.dylib`. It copies `libcairo` and its transitive dependencies (`libpixman`, `libpng`, `libfreetype`, etc.) into `chem4all.app/Contents/Frameworks/` and rewrites install names to reference the bundled copies.
3. Add a PyInstaller runtime hook (`hooks/rthook_cairo.py`, loaded before any application code runs) that sets `DYLD_FALLBACK_LIBRARY_PATH` to the bundle's `Frameworks/` directory. This ensures `ctypes.util.find_library("cairo")` resolves to the bundled dylib instead of expecting Homebrew on the target machine.

Result: the packaged app no longer depends on Homebrew at all. The Homebrew/cairo requirement in the README remains only for the source-install path.

## Section 3 — Signing & notarization

Prerequisites (already available): Apple Developer Program membership.

Setup (one-time):
- Export a **Developer ID Application** certificate (.p12) from Keychain Access, base64-encode it, store as GitHub Actions secrets `MACOS_CERT_P12` and `MACOS_CERT_PASSWORD`.
- Create an **App Store Connect API key** for notarization (preferred over Apple ID + app-specific password for CI reliability — no 2FA session concerns). Store as secrets `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`, `APPLE_API_KEY_P8`.

Per-build CI steps:
1. Import the certificate into a temporary, ephemeral keychain (created and destroyed within the job).
2. Codesign **each dylib bundled by `dylibbundler` individually** with the Developer ID certificate. Homebrew dylibs are ad-hoc-signed or unsigned by default, which fails Hardened Runtime library validation unless every bundled dylib carries a matching signature.
3. Codesign `chem4all.app` itself: `codesign --deep --force --options runtime --entitlements entitlements.plist --sign "<Developer ID>" chem4all.app`
4. Package into a `.dmg`: stage `chem4all.app` plus an `Applications` symlink in a temp folder, then `hdiutil create` from that folder — gives a standard drag-to-install layout without depending on Finder/AppleScript automation (tried `create-dmg` for a styled layout; its Finder-scripting step proved unreliable even in an interactive local terminal, `AppleEvent timed out (-1712)` — too fragile for CI).
5. Submit for notarization: `xcrun notarytool submit chem4all-<version>-<arch>.dmg --key-id ... --issuer ... --key ... --wait`
6. Staple the ticket: `xcrun stapler staple chem4all-<version>-<arch>.dmg` — this lets Gatekeeper verify offline on the recipient's machine.

## Section 4 — CI workflow & release process

GitHub Actions workflow, triggered on pushing a version tag (e.g. `v0.2.0`):

```yaml
jobs:
  build-arm64:
    runs-on: macos-14      # Apple Silicon
```

The job: checkout → install Python 3.12 (within the existing `<3.13` TensorFlow constraint) → `brew install cairo dylibbundler` → `pip install -e .` → PyInstaller build (Section 1) → dylib bundling (Section 2) → codesign + notarize + staple (Section 3) → upload the resulting `.dmg` as a workflow artifact.

A final job attaches the artifact to a GitHub Release for the tag:
- `chem4all-0.2.0-arm64.dmg`

Adding Intel later means adding a second `build-intel` job (nearest-available Intel GitHub-hosted runner — confirm availability at that time, since GitHub periodically retires older macOS runner images) and one more line in the release job's artifact list; no other section of this design changes.

## Section 5 — Runtime behavior on the recipient's machine

No behavior changes from what exists today:
- First launch: Gatekeeper sees the stapled notarization ticket and opens the app with no warning.
- GUI opens directly to the file picker (no CLI args passed).
- First use of DECIMER triggers `ModelDownloadWorker` (`gui/model_manager.py`), which already shows per-file download progress — unchanged.
- OpenRouter API key is entered via the existing Settings dialog and stored in `~/.chem4all/config.json` — unchanged.

## Testing

- **Local dev loop:** build an unsigned `.app` with plain `pyinstaller` on a local (arm64) machine first to validate the cairo-bundling fix quickly, before wiring signing into CI.
- **CI smoke checks**, after each build:
  - `codesign --verify --deep --strict chem4all.app`
  - `spctl -a -vvv --type execute chem4all.app` (Gatekeeper assessment)
  - Launch the app in the background and confirm the process is still alive after a few seconds (catches immediate startup crashes, e.g. a missed hidden import).
- **Manual pre-distribution check:** download the actual `.dmg` from the GitHub Release on a real Mac and do a full run-through (open a `.pptx`, run the pipeline end to end, confirm alt-text is written back) before sending it to instructors.
