from __future__ import annotations


def strip_to_parent(smiles: str) -> str:
    fragments = smiles.split(".")
    if len(fragments) == 1:
        return smiles
    return max(fragments, key=len)
