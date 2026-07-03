from __future__ import annotations
import base64
import os
import requests

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o"
_SYSTEM = (
    "You are an educational accessibility assistant. Given an image from a science "
    "course, respond with a single sentence suitable for use as alt-text. Describe "
    "what is depicted and its scientific significance."
)


def describe_image(image_bytes: bytes, api_key: str) -> str:
    resolved_key = os.environ.get("OPENROUTER_API_KEY") or api_key
    if not resolved_key:
        raise RuntimeError(
            "No OpenRouter API key configured. "
            "Add one in Settings or set the OPENROUTER_API_KEY environment variable."
        )
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"
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
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error during image description: {exc}") from exc

    if not response.ok:
        raise RuntimeError(
            f"OpenRouter returned {response.status_code}: {response.text[:200]}"
        )

    return response.json()["choices"][0]["message"]["content"].strip()
