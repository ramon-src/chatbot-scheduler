import pytest

from app.channels.phone import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5551999998888@s.whatsapp.net", "5551999998888"),
        ("5551999998888@c.us", "5551999998888"),
        ("+55 (51) 99999-8888", "5551999998888"),
        ("5551999998888", "5551999998888"),
        ("51999998888", "5551999998888"),       # 11 digits -> prepend 55
        ("(51) 99999-8888", "5551999998888"),    # 11 digits after strip
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected
