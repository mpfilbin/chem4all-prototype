from __future__ import annotations
import time
import requests

_PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CIR_BASE = "https://cactus.nci.nih.gov/chemical/structure"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class NameLookupError(RuntimeError):
    """All applicable sources failed after retries — distinct from a confirmed 'not found'."""


class _RetriesExhausted(Exception):
    pass


def _request_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.request(method, url, timeout=15, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(_BACKOFF_BASE_SECONDS * (2 ** attempt))
            continue
        if resp.status_code in _RETRYABLE_STATUS:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else _BACKOFF_BASE_SECONDS * (2 ** attempt)
            time.sleep(min(wait, 30))
            last_exc = RuntimeError(f"{url} returned {resp.status_code}")
            continue
        return resp
    raise _RetriesExhausted(str(last_exc))


def _pubchem_property(smiles: str, prop: str) -> str | None:
    resp = _request_with_backoff(
        "POST", f"{_PUBCHEM_BASE}/compound/smiles/property/{prop}/TXT", data={"smiles": smiles}
    )
    return resp.text.strip() if resp.status_code == 200 else None


def _pubchem_synonyms(smiles: str) -> list[str]:
    resp = _request_with_backoff(
        "POST", f"{_PUBCHEM_BASE}/compound/smiles/synonyms/TXT", data={"smiles": smiles}
    )
    if resp.status_code != 200:
        return []
    return [line for line in resp.text.strip().splitlines() if line]


def _cir_iupac_name(smiles: str) -> str | None:
    encoded = requests.utils.quote(smiles, safe="")
    resp = _request_with_backoff("GET", f"{_CIR_BASE}/{encoded}/iupac_name")
    return resp.text.strip() if resp.status_code == 200 else None
