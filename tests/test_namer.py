import pytest
import requests as req
from unittest.mock import MagicMock, patch
from pipeline.namer import lookup_iupac, lookup_trivial_name


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.ok = status < 400
    resp.status_code = status
    resp.text = text
    resp.json.return_value = {
        "choices": [{"message": {"content": f"  {text}  "}}]
    }
    return resp


# --- lookup_iupac ---

def test_lookup_iupac_success(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", return_value=_mock_response("benzene")) as mock_post:
        result = lookup_iupac("c1ccccc1", "test-key")
    assert result == "benzene"
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"] if call_kwargs.kwargs else call_kwargs[1]["json"]
    assert payload["model"] == "openai/gpt-4o"
    assert payload["messages"][1]["content"] == "c1ccccc1"


def test_lookup_iupac_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    with patch("pipeline.namer.requests.post", return_value=_mock_response("ethanol")) as mock_post:
        result = lookup_iupac("CCO", "config-key")
    assert result == "ethanol"
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer env-key"


def test_lookup_iupac_no_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No OpenRouter API key"):
        lookup_iupac("CCO", "")


def test_lookup_iupac_non_200_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", return_value=_mock_response("Unauthorized", 401)):
        with pytest.raises(RuntimeError, match="401"):
            lookup_iupac("CCO", "bad-key")


def test_lookup_iupac_network_error_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", side_effect=req.RequestException("timeout")):
        with pytest.raises(RuntimeError, match="Network error"):
            lookup_iupac("CCO", "any-key")


# --- lookup_trivial_name ---

def test_lookup_trivial_name_success(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", return_value=_mock_response("benzene")) as mock_post:
        result = lookup_trivial_name("c1ccccc1", "test-key")
    assert result == "benzene"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["messages"][1]["content"] == "c1ccccc1"


def test_lookup_trivial_name_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    with patch("pipeline.namer.requests.post", return_value=_mock_response("aspirin")) as mock_post:
        result = lookup_trivial_name("CC(=O)Oc1ccccc1C(=O)O", "config-key")
    assert result == "aspirin"
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer env-key"


def test_lookup_trivial_name_no_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No OpenRouter API key"):
        lookup_trivial_name("CCO", "")


def test_lookup_trivial_name_non_200_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", return_value=_mock_response("Forbidden", 403)):
        with pytest.raises(RuntimeError, match="403"):
            lookup_trivial_name("CCO", "bad-key")


def test_lookup_trivial_name_network_error_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.namer.requests.post", side_effect=req.RequestException("timeout")):
        with pytest.raises(RuntimeError, match="Network error"):
            lookup_trivial_name("CCO", "any-key")
