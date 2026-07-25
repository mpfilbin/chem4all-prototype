from pathlib import Path
from pipeline.name_cache import get_cached, set_cached


def test_get_cached_returns_none_when_no_row(tmp_path):
    db = tmp_path / "cache.db"
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) is None


def test_set_then_get_cached_found(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)


def test_set_cached_none_records_not_found(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("XYZ123", "iupac", "pubchem", None, db_path=db)
    assert get_cached("XYZ123", "iupac", "pubchem", db_path=db) == (None, False)


def test_cache_is_independent_per_source(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "cir", db_path=db) is None


def test_cache_is_independent_per_name_type(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "trivial", "pubchem", db_path=db) is None


def test_set_cached_upserts_existing_row(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "wrong-name", db_path=db)
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)


def test_cache_persists_across_connections(tmp_path):
    db = tmp_path / "cache.db"
    set_cached("CCO", "iupac", "pubchem", "ethanol", db_path=db)
    # Simulate app restart: a fresh call re-opens the same file.
    assert get_cached("CCO", "iupac", "pubchem", db_path=db) == ("ethanol", True)
