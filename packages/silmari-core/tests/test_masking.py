from silmari_core.masking import ColumnMasking, NoMasking, default_masking
from silmari_core.mock import MockSource


def test_no_masking() -> None:
    assert NoMasking().mask({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_column_masking_redacts_configured_case_insensitive() -> None:
    m = ColumnMasking(["ssn", "email"])
    assert m.mask({"id": 1, "ssn": "x", "Email": "a@b"}) == {
        "id": 1,
        "ssn": "***",
        "Email": "***",
    }


def test_column_masking_case_sensitive() -> None:
    m = ColumnMasking(["SSN"], case_insensitive=False)
    assert m.mask({"ssn": "x"}) == {"ssn": "x"}  # different case not masked
    assert m.mask({"SSN": "x"}) == {"SSN": "***"}


def test_custom_mask_token() -> None:
    assert ColumnMasking(["ssn"], mask="<redacted>").mask({"ssn": "x"}) == {"ssn": "<redacted>"}


def test_default_masking_includes_common_pii() -> None:
    out = default_masking().mask({"email": "a@b", "id": 1})
    assert out == {"email": "***", "id": 1}


def test_source_sample_applies_masking() -> None:
    src = MockSource({"t": [{"id": 1, "ssn": "x"}]}, masking=ColumnMasking(["ssn"]))
    assert src.sample("t") == [{"id": 1, "ssn": "***"}]
