from __future__ import annotations
import base64
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o"

_SYSTEM_IUPAC = (
    "You are a chemistry expert. Given a SMILES string (and, if provided, an image of "
    "the compound's 2D structure), respond with only the IUPAC name of the compound — "
    "no explanation, no punctuation, just the name. Always give the systematic IUPAC "
    "name, even if you recognize the compound by a common, trivial, or trade name."
)
_SYSTEM_TRIVIAL = (
    "You are a chemistry expert. Given a SMILES string (and, if provided, an image of "
    "the compound's 2D structure), respond with only the most widely used common or "
    "trivial name of the compound (not the IUPAC systematic name) — no explanation, "
    "no punctuation, just the name. "
    "If no well-known trivial name exists, respond with the IUPAC name."
)


def _build_content(smiles: str, image_bytes: bytes | None):
    if not image_bytes:
        return smiles
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"
    return [
        {"type": "text", "text": smiles},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]


def _lookup(smiles: str, api_key: str, system_prompt: str, image_bytes: bytes | None = None) -> str:
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
                    {"role": "user", "content": _build_content(smiles, image_bytes)},
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


def lookup_iupac(smiles: str, api_key: str, image_bytes: bytes | None = None) -> str:
    return _lookup(smiles, api_key, _SYSTEM_IUPAC, image_bytes)


def lookup_trivial_name(smiles: str, api_key: str, image_bytes: bytes | None = None) -> str:
    return _lookup(smiles, api_key, _SYSTEM_TRIVIAL, image_bytes)
