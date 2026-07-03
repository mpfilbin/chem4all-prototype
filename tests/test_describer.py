import pytest
import requests as req
from unittest.mock import MagicMock, patch
from pipeline.describer import describe_image


def _mock_response(text: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.ok = status < 400
    resp.status_code = status
    resp.text = text
    resp.json.return_value = {
        "choices": [{"message": {"content": f"  {text}  "}}]
    }
    return resp


def test_describe_image_success(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    image_bytes = b"fake-png-data"
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Diagram of ATP synthase complex.")) as mock_post:
        result = describe_image(image_bytes, "test-key")
    assert result == "Diagram of ATP synthase complex."
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "openai/gpt-4o"
    user_content = payload["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "image_url"
    assert user_content[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_describe_image_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Cell membrane diagram.")) as mock_post:
        result = describe_image(b"img", "config-key")
    assert result == "Cell membrane diagram."
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer env-key"


def test_describe_image_no_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="No OpenRouter API key"):
        describe_image(b"img", "")


def test_describe_image_non_200_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.describer.requests.post",
               return_value=_mock_response("Unauthorized", 401)):
        with pytest.raises(RuntimeError, match="401"):
            describe_image(b"img", "bad-key")


def test_describe_image_network_error_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("pipeline.describer.requests.post",
               side_effect=req.RequestException("timeout")):
        with pytest.raises(RuntimeError, match="Network error"):
            describe_image(b"img", "any-key")
