import pytest
from pipeline.namer import lookup_iupac, lookup_trivial_name, NameLookupError, _inchikey_for

ETHANOL_SMILES = "CCO"
ETHANOL_INCHIKEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


# --- _inchikey_for ---

def test_inchikey_for_computes_expected_key():
    assert _inchikey_for(ETHANOL_SMILES) == ETHANOL_INCHIKEY


def test_inchikey_for_strips_salts_before_computing():
    # Sodium acetate: without stripping the [Na+] fragment first, RDKit would compute
    # a different, salt-inclusive InChIKey that wouldn't match the parent compound's
    # entry in the dataset.
    assert _inchikey_for("CC(=O)[O-].[Na+]") == "QTBSBXVTEAMEQO-UHFFFAOYSA-M"


def test_inchikey_for_raises_on_unparseable_smiles():
    with pytest.raises(NameLookupError):
        _inchikey_for("not_a_smiles")


# --- lookup_iupac ---

def test_lookup_iupac_returns_name_on_hit(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: ("ethanol", "alcohol"))
    assert lookup_iupac(ETHANOL_SMILES) == "ethanol"


def test_lookup_iupac_returns_none_on_confirmed_miss(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: (None, None))
    assert lookup_iupac(ETHANOL_SMILES) is None


def test_lookup_iupac_raises_when_dataset_not_downloaded(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: False)
    with pytest.raises(NameLookupError):
        lookup_iupac(ETHANOL_SMILES)


def test_lookup_iupac_raises_on_unparseable_smiles(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    with pytest.raises(NameLookupError):
        lookup_iupac("not_a_smiles")


# --- lookup_trivial_name ---

def test_lookup_trivial_name_returns_name_on_hit(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: ("ethanol", "alcohol"))
    assert lookup_trivial_name(ETHANOL_SMILES) == "alcohol"


def test_lookup_trivial_name_returns_none_on_confirmed_miss(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", lambda inchikey: (None, None))
    assert lookup_trivial_name(ETHANOL_SMILES) is None


def test_lookup_trivial_name_raises_when_dataset_not_downloaded(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: False)
    with pytest.raises(NameLookupError):
        lookup_trivial_name(ETHANOL_SMILES)


# --- both call sites use the computed InChIKey, not the raw SMILES ---

def test_lookup_uses_computed_inchikey(monkeypatch):
    monkeypatch.setattr("pipeline.namer.name_dataset.is_dataset_ready", lambda: True)
    calls = []

    def _fake_lookup(inchikey):
        calls.append(inchikey)
        return (None, None)

    monkeypatch.setattr("pipeline.namer.name_dataset.lookup", _fake_lookup)
    lookup_iupac(ETHANOL_SMILES)
    assert calls == [ETHANOL_INCHIKEY]
