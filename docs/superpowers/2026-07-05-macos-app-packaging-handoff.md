# macOS App Packaging — Handoff Note (paused 2026-07-05)

> **Resolved 2026-07-07:** the open question below was confirmed and fixed.
> `dylibbundler -b` (bundle mode) was missing from the invocation, so it
> never actually copied the 4 missing transitive deps — the `LC_RPATH`
> fallback hypothesis was correct. Fix landed in
> `packaging/build_dmg.sh` (the `-b` flag plus copy-cairo-first ordering).
> Verified in the real `v0.1.0` release CI log: `libpixman-1.0.dylib`,
> `libXext.6.dylib`, `libXrender.1.dylib`, and `libxcb-render.0.0.0.dylib`
> are all present in `Contents/Frameworks` with rewritten install names, and
> the app installed and ran cleanly on a clean recipient Mac with no
> Homebrew dependency. Tasks 3-9 are complete; see
> `docs/superpowers/plans/2026-07-04-macos-app-packaging.md` for final status.

**Scope update (2026-07-05, on resuming):** narrowed to Apple Silicon (arm64)
only for this effort. Intel Mac and Windows (arm64/x64) are deferred to
follow-up work — see the spec's new "Future platforms" section. The spec and
plan have been updated accordingly (single-entry CI matrix, single dmg
artifact, no Intel runner). `packaging/build_dmg.sh`'s `<arch>` parameter is
kept as-is so Intel remains an additive change later.

Work is paused mid-Task-3 to investigate an open correctness question before
continuing. This note is the durable record — `.superpowers/sdd/` (progress
ledger, task briefs/reports, review diffs) is git-ignored local scratch and
will not survive `git clean -fdx` or a fresh clone.

## Branch

`macos-app-packaging`, branched from `master` at `6285614`. Commits so far:

```
c22a36d docs: add design spec for standalone macOS app packaging
b6f5efc docs: add implementation plan for macOS app packaging
166cd56 build: add PyInstaller spec and cairo runtime hook          (Task 1)
695da10 build: allow-list the tracked PyInstaller spec in .gitignore (Task 1)
d2655fb build: add local build script for app bundling and dmg creation (Task 2)
96b62fa fix: add missing -b flag to dylibbundler invocation          (Task 2 fix)
179c6a1 fix: resolve chem4all.spec paths via SPECPATH instead of CWD-relative literals (Task 1 fix — found during live build)
896f639 fix: copy cairo into app bundle before running dylibbundler  (Task 2 fix — found during live build)
```

Spec: `docs/superpowers/specs/2026-07-04-macos-app-packaging-design.md`
Plan: `docs/superpowers/plans/2026-07-04-macos-app-packaging.md` (9 tasks; process is
superpowers:subagent-driven-development)

## Status by task

- **Task 1** (PyInstaller spec + cairo runtime hook): done, reviewed, approved.
  One bug found later during real build (`179c6a1`, see below).
- **Task 2** (build script): done, reviewed, approved. Two bugs found later
  during real build (`96b62fa`, `896f639`, see below).
- **Task 3** (local unsigned build verification — a MANUAL GATE, run by the
  human, not a subagent): **in progress, paused on an open question.**
- Tasks 4-9, final review: not started.

## Bugs found so far during real (not just reviewed) builds

Both of these slipped past task review because they only manifest when
`pyinstaller`/`dylibbundler` actually run — a good argument for why Task 3
(a human running a real build) exists as its own gate rather than trusting
review alone.

1. **`packaging/chem4all.spec` CWD-relative paths** — `runtime_hooks` and the
   main script path were literal relative strings, which PyInstaller
   resolves against the process's CWD, not the spec file's directory. Since
   `build_dmg.sh` does `cd "$REPO_ROOT"` before invoking `pyinstaller
   packaging/chem4all.spec`, this broke. Fixed in `179c6a1` using
   PyInstaller's injected `SPECPATH` variable to build absolute paths.

2. **`dylibbundler -x <file>` doesn't copy `<file>` itself** — it only
   copies *that file's* dependencies and rewrites *that file's* load
   commands. Pointing `-x` at the live Homebrew `libcairo.2.dylib` never
   actually copied cairo into the bundle, and would have mutated the
   system's real Homebrew install in place. Fixed in `896f639`: copy cairo
   into `Contents/Frameworks` first, set its own install-name ID, then run
   `dylibbundler -x` against the **bundled copy**, never the original.

## Open question — where we paused

After the `896f639` fix, a real build was run (`./packaging/build_dmg.sh
0.1.0-dev local`). Results:

- `libcairo.2.dylib` is now correctly bundled in `Contents/Frameworks`.
- `otool -L` on it shows all its declared dependencies rewritten to
  `@executable_path/../Frameworks/...` — looks correct on paper.
- But four of those referenced files are **not actually present** in
  `Contents/Frameworks`: `libpixman-1.0.dylib`, `libXext.6.dylib`,
  `libXrender.1.dylib`, `libxcb-render.0.0.0.dylib`. (Six others — libpng16,
  libfontconfig, libfreetype, libX11, libxcb, libxcb-shm — are present,
  apparently because PyInstaller had already bundled them as transitive
  deps of opencv-python/Pillow before dylibbundler ever ran, and
  dylibbundler treated the coincidentally-matching filename as "already
  handled.")
- Despite those 4 being missing, manual testing on the developer's own
  machine worked: the app launched, processed a plain `.docx`, and
  processed a `.docx` with an embedded SVG successfully.

**Working hypothesis (not yet confirmed):** the bundled `libcairo.2.dylib`
still carries embedded `LC_RPATH` load commands from when Homebrew
originally built it (pointing at e.g. `/opt/homebrew/opt/pixman/lib`),
which travel along unchanged when the file is copied. `dylibbundler`
rewrites the explicit `LC_LOAD_DYLIB` paths but doesn't strip old
`LC_RPATH` entries, so on the *developer's* machine dyld silently falls
back to the real Homebrew-installed copies of pixman/Xext/Xrender/xcb-render
— meaning the build only appears self-contained because Homebrew is
present, and would very likely crash on a recipient's clean Mac (no
Homebrew, no XQuartz) the moment cairo actually needs one of those symbols.
This would directly violate the design spec's goal ("the packaged app no
longer depends on Homebrew at all").

**Next step when resuming:** run, without needing to relaunch the app,

```bash
otool -l dist/chem4all.app/Contents/Frameworks/libcairo.2.dylib | grep -A2 LC_RPATH
```

If it prints Homebrew paths, that confirms the hypothesis, and the real fix
is either stripping those rpaths (`install_name_tool -delete_rpath`) after
copying cairo, or making sure `dylibbundler`/manual copying actually
bundles the 4 missing transitive dependencies (pixman, Xext, Xrender,
xcb-render) regardless of what rpaths happen to paper over the gap on this
machine. Either way, `packaging/build_dmg.sh` needs another fix-and-verify
round before Task 3 can be signed off, and a completely clean recipient
machine (or at minimum a machine with Homebrew's cairo/pixman/X11 libs
temporarily moved aside) would be the only fully convincing test.

## Resuming

1. Re-checkout `macos-app-packaging`.
2. Run the `LC_RPATH` check above.
3. Fix `packaging/build_dmg.sh` accordingly, re-run
   `./packaging/build_dmg.sh 0.1.0-dev local`, and re-verify (Frameworks
   listing + a real SVG document) before considering Task 3 done.
4. Continue with Tasks 4-9 per the plan, using
   superpowers:subagent-driven-development as before.
