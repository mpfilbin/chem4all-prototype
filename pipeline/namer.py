from __future__ import annotations
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o"

_SYSTEM_IUPAC = (
    "You are a chemistry expert. Given a SMILES string, respond with only the "
    "IUPAC name of the compound — no explanation, no punctuation, just the name."
)
_SYSTEM_TRIVIAL = (
    "You are a chemistry expert. Given a SMILES string, respond with only the most "
    "widely used common or trivial name of the compound (not the IUPAC systematic name) "
    "— no explanation, no punctuation, just the name. "
    "If no well-known trivial name exists, respond with the IUPAC name."
)


def _lookup(smiles: str, api_key: str, system_prompt: str) -> str:
    resolved_key = os.environ.get("OPENROUTER_API_KEY") or api_key
    if not resolved_key:
        raise RuntimeError(
            "No OpenRouter API key configured. "
            "Add one in Settings or set the OPENROUTER_API_KEY environment variable."
        )
    try:
        response = requests.post(
            _ENDPOINT,
            headers={
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "chem4all",
            },
            json={
                "model": _MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": smiles},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error during name lookup: {exc}") from exc

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter returned {response.status_code}: {response.text[:200]}"
        )

    return response.json()["choices"][0]["message"]["content"].strip()


def lookup_iupac(smiles: str, api_key: str) -> str:
    return _lookup(smiles, api_key, _SYSTEM_IUPAC)


def lookup_trivial_name(smiles: str, api_key: str) -> str:
    return _lookup(smiles, api_key, _SYSTEM_TRIVIAL)
