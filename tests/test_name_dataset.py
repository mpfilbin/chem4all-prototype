import sqlite3
import pytest
from pipeline import name_dataset

ETHANOL_INCHIKEY = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"


def _make_fixture_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE names (inchikey TEXT PRIMARY KEY, iupac_name TEXT, trivial_name TEXT)")
    conn.execute("INSERT INTO names VALUES (?, ?, ?)", (ETHANOL_INCHIKEY, "ethanol", "alcohol"))
    conn.commit()
    conn.close()


def test_dataset_path_uses_chem4all_naming_pystow_home(monkeypatch):
    monkeypatch.setattr("pipeline.name_dataset.pystow.join", lambda *parts: "/fake/home/" + "/".join(parts))
    assert str(name_dataset.dataset_path()) == "/fake/home/chem4all/naming/names.sqlite"


def test_is_dataset_ready_false_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: tmp_path / "names.sqlite")
    assert name_dataset.is_dataset_ready() is False


def test_is_dataset_ready_true_when_file_exists(tmp_path, monkeypatch):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    monkeypatch.setattr(name_dataset, "dataset_path", lambda: db)
    assert name_dataset.is_dataset_ready() is True


def test_lookup_returns_names_on_hit(tmp_path):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    assert name_dataset.lookup(ETHANOL_INCHIKEY, db_path=db) == ("ethanol", "alcohol")


def test_lookup_returns_none_none_on_miss(tmp_path):
    db = tmp_path / "names.sqlite"
    _make_fixture_db(db)
    assert name_dataset.lookup("AAAAAAAAAAAAAA-AAAAAAAAAA-A", db_path=db) == (None, None)


def test_lookup_raises_when_dataset_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.sqlite"
    with pytest.raises(sqlite3.Error):
        name_dataset.lookup(ETHANOL_INCHIKEY, db_path=missing)


def test_lookup_raises_on_corrupt_dataset_file(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a real sqlite database")
    with pytest.raises(sqlite3.Error):
        name_dataset.lookup(ETHANOL_INCHIKEY, db_path=corrupt)
