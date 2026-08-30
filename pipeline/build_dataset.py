from __future__ import annotations
# Maintainer tool: builds the local naming dataset SQLite index from PubChem's
# bulk data files, for upload to Azure Blob Storage. Not run by the shipped
# app — see docs/superpowers/specs/2026-08-30-offline-naming-dataset-design.md.
#
# Usage: python -m pipeline.build_dataset [--work-dir DIR] [--output FILE]
import argparse
import gzip
import logging
import sqlite3
from pathlib import Path
from urllib.request import urlopen

log = logging.getLogger(__name__)

_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras"
_INCHIKEY_URL = f"{_BASE_URL}/CID-InChI-Key.gz"
_IUPAC_URL = f"{_BASE_URL}/CID-IUPAC.gz"
_SYNONYM_URL = f"{_BASE_URL}/CID-Synonym-filtered.gz"


def _download(url: str, dest: Path) -> None:
    log.info("Downloading %s -> %s", url, dest)
    with urlopen(url) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)


def _iter_tsv(path: Path):
    """Yields (cid, rest) from a CID-sorted, gzip'd TSV bulk file."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts or not parts[0]:
                continue
            yield int(parts[0]), parts[1:]


def _first_synonym_per_cid(synonym_path: Path):
    """CID-Synonym-filtered.gz has multiple rows per CID in relevance order;
    yields only the first (most relevant) synonym per CID."""
    last_cid = None
    for cid, rest in _iter_tsv(synonym_path):
        if cid == last_cid:
            continue
        last_cid = cid
        if rest and rest[0]:
            yield cid, rest[0]


def merge_by_cid(inchikey_path: Path, iupac_path: Path, synonym_path: Path):
    """Linear merge-join of the three CID-sorted bulk files, restricted to CIDs
    present in synonym_path (compounds with at least one known synonym).
    Yields (inchikey, iupac_name, trivial_name) rows; iupac_name is None if
    PubChem has no computed IUPAC name for that CID; a CID with no InChIKey
    at all is skipped (nothing to index it by)."""
    inchikey_rows = _iter_tsv(inchikey_path)             # (cid, [inchi, inchikey])
    iupac_rows = _iter_tsv(iupac_path)                   # (cid, [iupac_name])
    synonym_rows = _first_synonym_per_cid(synonym_path)  # (cid, first_synonym)

    ik_cid, ik_rest = next(inchikey_rows, (None, None))
    iu_cid, iu_rest = next(iupac_rows, (None, None))

    for syn_cid, trivial_name in synonym_rows:
        while ik_cid is not None and ik_cid < syn_cid:
            ik_cid, ik_rest = next(inchikey_rows, (None, None))
        while iu_cid is not None and iu_cid < syn_cid:
            iu_cid, iu_rest = next(iupac_rows, (None, None))

        if ik_cid != syn_cid:
            continue
        inchikey = ik_rest[-1]
        iupac_name = iu_rest[0] if iu_cid == syn_cid and iu_rest else None
        yield inchikey, iupac_name, trivial_name


def build_index(rows, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE names (inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)"
        )
        # OR IGNORE: if PubChem publishes more than one CID for the same InChIKey
        # (e.g. isotope/stereo variants that collapse to one standard InChIKey),
        # keep whichever row was inserted first rather than raising.
        conn.executemany(
            "INSERT OR IGNORE INTO names (inchikey, iupac_name, trivial_name) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def gzip_file(src: Path, dest: Path) -> None:
    with open(src, "rb") as f_in, gzip.open(dest, "wb") as f_out:
        while chunk := f_in.read(1 << 20):
            f_out.write(chunk)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Build the offline naming dataset SQLite index from PubChem bulk data."
    )
    parser.add_argument("--work-dir", type=Path, default=Path("build_dataset_work"))
    parser.add_argument("--output", type=Path, default=Path("naming_dataset.sqlite.gz"))
    args = parser.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    inchikey_path = args.work_dir / "CID-InChI-Key.gz"
    iupac_path = args.work_dir / "CID-IUPAC.gz"
    synonym_path = args.work_dir / "CID-Synonym-filtered.gz"
    db_path = args.work_dir / "names.sqlite"

    for url, dest in (
        (_INCHIKEY_URL, inchikey_path),
        (_IUPAC_URL, iupac_path),
        (_SYNONYM_URL, synonym_path),
    ):
        if not dest.exists():
            _download(url, dest)

    log.info("Joining bulk files by CID...")
    rows = merge_by_cid(inchikey_path, iupac_path, synonym_path)
    build_index(rows, db_path)

    log.info("Compressing %s -> %s", db_path, args.output)
    gzip_file(db_path, args.output)
    log.info("Done: %s", args.output)


if __name__ == "__main__":
    main()
