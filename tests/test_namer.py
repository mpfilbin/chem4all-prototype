import pytest
import requests as req
from unittest.mock import MagicMock, patch
from pipeline.namer import _pubchem_property, _pubchem_synonyms, _cir_iupac_name, _RetriesExhausted


def _mock_response(status: int, text: str = "", headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.headers = headers or {}
    return resp


# --- _pubchem_property ---

def test_pubchem_property_success_returns_stripped_text():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "  ethanol  ")) as mock_req:
        result = _pubchem_property("CCO", "IUPACName")
    assert result == "ethanol"
    args, kwargs = mock_req.call_args
    assert args[0] == "POST"
    assert args[1] == "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/IUPACName/TXT"
    assert kwargs["data"] == {"smiles": "CCO"}


def test_pubchem_property_404_returns_none():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _pubchem_property("not_a_smiles", "IUPACName") is None


def test_pubchem_property_retries_503_then_succeeds(monkeypatch):
    monkeypatch.setattr("pipeline.namer.time.sleep", lambda _s: None)
    responses = [_mock_response(503, headers={"Retry-After": "1"}), _mock_response(200, "ethanol")]
    with patch("pipeline.namer.requests.request", side_effect=responses):
        result = _pubchem_property("CCO", "IUPACName")
    assert result == "ethanol"


def test_pubchem_property_exhausts_retries_raises():
    with patch("pipeline.namer.time.sleep"):
        with patch("pipeline.namer.requests.request", return_value=_mock_response(503)):
            with pytest.raises(_RetriesExhausted):
                _pubchem_property("CCO", "IUPACName")


def test_pubchem_property_network_error_retries_then_raises():
    with patch("pipeline.namer.time.sleep"):
        with patch("pipeline.namer.requests.request", side_effect=req.RequestException("timeout")):
            with pytest.raises(_RetriesExhausted):
                _pubchem_property("CCO", "IUPACName")


# --- _pubchem_synonyms ---

def test_pubchem_synonyms_success_returns_line_list():
    text = "2-acetyloxybenzoic acid\n2-Acetoxybenzoic acid\n50-78-2\n"
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, text)):
        result = _pubchem_synonyms("CC(=O)Oc1ccccc1C(=O)O")
    assert result == ["2-acetyloxybenzoic acid", "2-Acetoxybenzoic acid", "50-78-2"]


def test_pubchem_synonyms_404_returns_empty_list():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _pubchem_synonyms("not_a_smiles") == []


# --- _cir_iupac_name ---

def test_cir_iupac_name_success():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "ethanol")) as mock_req:
        result = _cir_iupac_name("CCO")
    assert result == "ethanol"
    args, kwargs = mock_req.call_args
    assert args[0] == "GET"
    assert args[1] == "https://cactus.nci.nih.gov/chemical/structure/CCO/iupac_name"


def test_cir_iupac_name_url_encodes_slash_characters():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(200, "but-2-ene")) as mock_req:
        _cir_iupac_name("C/C=C/C")
    args, _ = mock_req.call_args
    assert "/" not in args[1].split("chemical/structure/")[1].split("/iupac_name")[0]


def test_cir_iupac_name_404_returns_none():
    with patch("pipeline.namer.requests.request", return_value=_mock_response(404)):
        assert _cir_iupac_name("some_smiles") is None
