from models.image_record import ImageRecord


def test_image_record_defaults():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
    )
    assert record.predicted_smiles is None
    assert record.confidence is None
    assert record.iupac_name is None
    assert record.trivial_name is None
    assert record.approved_value is None
    assert record.is_chemical is None
    assert record.description is None
    assert record.prediction_types == ["smiles"]


def test_image_record_to_review_dict_excludes_bytes():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"thumb",
        recognition_bytes=b"recog",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        iupac_name="benzene",
        trivial_name="benzene",
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    assert "thumbnail_bytes" not in d
    assert "recognition_bytes" not in d
    assert d["id"] == "abc123"
    assert d["predicted_smiles"] == "C1=CC=CC=C1"
    assert d["iupac_name"] == "benzene"
    assert d["trivial_name"] == "benzene"
    assert d["approved_value"] == "C1=CC=CC=C1"
    assert d["is_chemical"] is True
    assert d["description"] is None
    assert d["prediction_types"] == ["smiles"]


def test_image_record_from_review_dict_roundtrip():
    record = ImageRecord(
        id="abc123",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        confidence=0.95,
        iupac_name="benzene",
        trivial_name="benzene",
        approved_value="C1=CC=CC=C1",
        is_chemical=True,
    )
    d = record.to_review_dict()
    restored = ImageRecord.from_review_dict(d)
    assert restored.id == record.id
    assert restored.iupac_name == "benzene"
    assert restored.trivial_name == "benzene"
    assert restored.approved_value == record.approved_value
    assert restored.thumbnail_bytes == b""
    assert restored.recognition_bytes == b""
    assert restored.description is None
    assert restored.prediction_types == ["smiles"]


def test_image_record_prediction_types_default():
    record = ImageRecord(
        id="x",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )
    assert record.prediction_types == ["smiles"]


def test_result_lines_returns_smiles_by_default():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        prediction_types=["smiles"],
    )
    assert record.result_lines() == ["C1=CC=CC=C1"]


def test_result_lines_returns_iupac_name():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        iupac_name="benzene",
        prediction_types=["iupac"],
    )
    assert record.result_lines() == ["benzene"]


def test_result_lines_returns_trivial_name():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        trivial_name="benzene",
        prediction_types=["trivial"],
    )
    assert record.result_lines() == ["benzene"]


def test_result_lines_skips_type_when_name_not_yet_loaded():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        prediction_types=["iupac"],  # iupac_name not set yet
    )
    assert record.result_lines() == []


def test_image_record_description_default():
    record = ImageRecord(
        id="x",
        source_ref="slide 1, shape 1",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
    )
    assert record.description is None


def test_result_lines_returns_description():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        description="Diagram of ATP synthase embedded in the inner mitochondrial membrane.",
        prediction_types=["description"],
    )
    assert record.result_lines() == [
        "Diagram of ATP synthase embedded in the inner mitochondrial membrane."
    ]


def test_result_lines_skips_description_when_not_yet_loaded():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        prediction_types=["description"],  # description not set yet
    )
    assert record.result_lines() == []


def test_result_lines_returns_multiple_types_in_fixed_order():
    record = ImageRecord(
        id="x",
        source_ref="s",
        thumbnail_bytes=b"",
        recognition_bytes=b"",
        predicted_smiles="C1=CC=CC=C1",
        iupac_name="benzene",
        description="A benzene ring diagram.",
        prediction_types=["description", "smiles", "iupac"],  # list order shouldn't matter
    )
    assert record.result_lines() == [
        "C1=CC=CC=C1",
        "benzene",
        "A benzene ring diagram.",
    ]
