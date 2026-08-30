from __future__ import annotations
import sqlite3

from rdkit import Chem
from pipeline import name_dataset
from pipeline.salts import strip_to_parent


class NameLookupError(RuntimeError):
    """Unparseable SMILES, or the local dataset isn't downloaded yet — distinct
    from a confirmed 'not found', which returns None instead."""


def _inchikey_for(smiles: str) -> str:
    canonical = strip_to_parent(smiles)
    mol = Chem.MolFromSmiles(canonical)
    if mol is None:
        raise NameLookupError(f"Could not parse SMILES: {canonical}")
    return Chem.MolToInchiKey(mol)


def _lookup_safe(inchikey: str) -> tuple[str | None, str | None]:
    """Wraps name_dataset.lookup so a missing/corrupt dataset file surfaces as
    NameLookupError. A bare sqlite3.Error would escape RecognizerWorker's
    except clause and abort the whole recognition batch."""
    try:
        return name_dataset.lookup(inchikey)
    except sqlite3.Error as exc:
        raise NameLookupError(f"Naming dataset could not be read: {exc}") from exc


def lookup_iupac(smiles: str) -> str | None:
    if not name_dataset.is_dataset_ready():
        raise NameLookupError("Naming dataset not downloaded — see Settings.")
    iupac_name, _ = _lookup_safe(_inchikey_for(smiles))
    return iupac_name


def lookup_trivial_name(smiles: str) -> str | None:
    if not name_dataset.is_dataset_ready():
        raise NameLookupError("Naming dataset not downloaded — see Settings.")
    _, trivial_name = _lookup_safe(_inchikey_for(smiles))
    return trivial_name
