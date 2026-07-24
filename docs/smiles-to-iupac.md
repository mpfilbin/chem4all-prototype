# Feature Specification: SMILES-to-IUPAC Name Conversion

**Product:** Chem4All
**Status:** Draft for review
**Author:** Mike Filbin
**Last updated:** 2026-07-24

## 1. Summary

Chem4All's chemistry-structure tool produces SMILES strings for molecules. This feature adds the ability to convert those SMILES strings into IUPAC names, so users see human-readable chemical names alongside (or instead of) raw SMILES.

## 2. Problem Statement

The app currently has no way to translate a SMILES string into an IUPAC name. Users working in the desktop app need this for readability and reporting, across batch workloads of tens to hundreds of structures per session.

## 3. Goals

- Convert SMILES to IUPAC names for structures already known to public chemical databases.
- Support batch conversion (10s–100s of SMILES per run) without freezing the UI.
- Ship inside a PyQt + PyInstaller macOS desktop app, portable to Windows/Linux, without introducing per-architecture build or notarization risk.
- Stay GPL-compatible and free for academic/non-commercial use.

## 4. Non-Goals

- Naming genuinely novel structures not present in any public database (out of scope for v1; see §9).
- Offline/air-gapped operation (out of scope for v1; see §10).
- Independent chemical validation of returned names (e.g., round-tripping through a second naming engine).

## 5. Constraints

| Constraint | Detail |
|---|---|
| Distribution | PyQt + PyInstaller desktop app |
| Platforms | macOS (Apple Silicon + Intel), Windows, Linux |
| Licensing | GPL-compatible |
| Use case | Academic, non-commercial |
| Dependencies | Must avoid compiled/native extensions where possible (build + notarization risk) |
| Batch size | Tens to hundreds of SMILES per workload |
| UI | Must not block the Qt main thread during batch lookups |

## 6. Options Considered

| Option | License | Deterministic | Verdict |
|---|---|---|---|
| OpenEye Lexichem TK | Proprietary | Yes | Rejected — not GPL-compatible; Apple Silicon support unconfirmed |
| ChemAxon/Certara Naming Toolkit | Proprietary, license-key gated | Yes | Rejected — not GPL-compatible |
| STOUT v2 | MIT (OSS) | No (ML/NMT-based) | Rejected — not accuracy-rated by its own authors; model weights hosting reportedly broken (404) as of mid-2026 |
| `smiles2iupac` (PubChem + OPSIN wrapper) | OSS | Partial (OPSIN cross-check) | Rejected — alpha/single-maintainer, not on PyPI (supply-chain risk), RDKit dependency needs per-architecture builds, requires bundling a Java 17+ JRE for OPSIN |
| **Direct PubChem PUG REST integration** | Free public API (NIH) | Yes (deterministic, PubChem's own naming) | **Selected** |

## 7. Decision

Integrate directly with PubChem's PUG REST API to look up IUPAC names for SMILES-derived structures.

**Rationale:**

- Pure Python, zero compiled dependencies — no RDKit, no JVM.
- Trivially portable across all target architectures and platforms.
- No macOS notarization risk.
- Free, publicly run (NIH), long track record — no license to reconcile against GPL.
- Clears the academic/non-commercial bar by default.

## 8. Design

### 8.1 Lookup flow

1. User (or batch job) submits one or more SMILES strings.
2. Each SMILES is pre-processed (see §8.4, salt/mixture handling).
3. Check local cache (§8.3) for a match. If found, return cached name immediately.
4. On cache miss, submit a POST request to PubChem PUG REST:
   `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/IUPACName/TXT`
   - Use POST, not URL-embedded SMILES, since SMILES characters (`/`, `\`, `#`, etc.) conflict with URL path syntax.
5. Parse the response:
   - Success → store in cache, return name to UI.
   - No match → return "IUPAC name not available" (see §9).
   - Error/timeout → retry per backoff policy (§8.2); surface a network error if retries are exhausted.
6. All of the above runs off the Qt main thread (see §8.5).

### 8.2 Rate limiting and backoff

- PubChem's usage policy caps requests at roughly 5/second.
- Implement a client-side token-bucket or simple sleep-based throttle to stay under this limit during batch runs.
- On HTTP 429 or 5xx, apply exponential backoff with a capped number of retries before marking that lookup as failed.
- Batch jobs should report partial progress (e.g., "80/120 looked up") rather than failing the whole batch on one bad response.

### 8.3 Caching

- **Storage:** persistent local SQLite database (bundled alongside the app's other local data).
- **Key:** canonical SMILES string.
- **Schema (minimal):**

  ```sql
  CREATE TABLE iupac_cache (
      lookup_key   TEXT PRIMARY KEY,   -- canonical SMILES
      smiles       TEXT NOT NULL,
      iupac_name   TEXT,               -- NULL if PubChem returned no name
      found        INTEGER NOT NULL,   -- 0/1, distinguishes "not found" from "not yet looked up"
      queried_at   TEXT NOT NULL       -- ISO timestamp, for cache-invalidation policy if ever needed
  );
  ```

- Rationale: persistence survives app restarts, reduces repeat PubChem calls across sessions, and directly mitigates the rate-limit constraint. Caching "not found" results (not just successes) avoids re-querying PubChem for structures already confirmed absent.

### 8.4 Salt/mixture handling

- Before lookup, strip counter-ions/salts from multi-component SMILES (e.g., `.` separated fragments) so the query targets the parent structure.
- Lookups are performed by canonical SMILES directly via PUG REST, accepting PubChem's own canonicalization behavior. An InChIKey-based lookup was considered (it can be more robust to cross-toolkit canonicalization differences), but was deliberately omitted: computing an InChIKey locally requires a compiled library (the official InChI C library, or an RDKit/OpenBabel binding), which would reintroduce the exact per-architecture build and notarization complexity that ruled out the RDKit-dependent options in §6. This keeps the feature dependency-free as designed.

### 8.5 Threading

- All PubChem lookups (single or batch) run off the Qt main thread via `QThread`/`QRunnable`, or via an async client with results marshaled back to the UI thread.
- Batch jobs should be cancelable and should update a progress indicator as individual lookups complete.

## 9. UX Behavior

| Case | Behavior |
|---|---|
| Name found | Display IUPAC name in place of/alongside the SMILES string |
| Name not available | Display "IUPAC name not available." The SMILES string remains visible in the UI, so no additional fallback identifier display is needed |
| Network/API error | Surface a distinct error state (not conflated with "not available"), with retry |
| Batch in progress | Non-blocking progress indicator; partial results shown as they arrive |

## 10. Known Limitations

- **Coverage:** PubChem indexes ~120M compounds; only returns a name for structures already in its database. Novel structures generated by the app will return "not available." No fallback naming engine is in scope for v1.
- **No offline mode:** requires network access at lookup time.
- **Rate limits:** ~5 requests/second per PubChem policy; batch runs must throttle accordingly.
- **No independent cross-check:** unlike the rejected `smiles2iupac` option's OPSIN round-trip, there is no second-engine validation of the returned name. This is an accepted accuracy tradeoff in exchange for packaging simplicity.

## 11. Future Considerations

Revisit the "PubChem-only, no offline mode" decision if any of the following occur:

- The app needs to support field/no-network use.
- Typical batch sizes grow from hundreds into the thousands, making network latency or rate limits a recurring bottleneck.
- PubChem coverage gaps or rate-limiting become a frequent, reported user pain point (at which point a fallback engine, such as a properly-packaged OPSIN or a revisited STOUT once its weights hosting is fixed, could be reconsidered).

## 12. Implementation Notes

- Use `requests` directly, or `pubchempy` as a thin convenience wrapper — both pure Python, no compiled extensions.
- Batch lookups should dedupe identical SMILES within a single submitted batch before hitting the cache/network.
- Log cache hit/miss and PubChem error rates to inform whether the v1 tradeoffs (no InChIKey, no fallback naming) need revisiting.

## 13. Open Questions

None outstanding — the three open questions from initial research have been resolved above (§8.3 cache design, §9 no-name UX, §11 offline revisit triggers).