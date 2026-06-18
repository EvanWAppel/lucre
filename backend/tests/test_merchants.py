import pytest

from services.merchants import merchant_key

# (raw transaction string, expected stable key)
CASES = [
    ("NETFLIX.COM 866-579-7172 CA", "netflix"),
    ("Netflix.com", "netflix"),
    ("STARBUCKS #1234", "starbucks"),
    ("STARBUCKS #5678", "starbucks"),
    ("SQ *COFFEE SHOP", "coffee shop"),
    ("TST* THE RESTAURANT", "the restaurant"),
    ("AMAZON.COM*A1B2C3", "amazon"),
    ("WHOLEFDS WFM #10256", "wholefds wfm"),
    ("SHELL OIL 5764123", "shell oil"),
    ("  Spotify   USA  ", "spotify usa"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_merchant_key(raw, expected):
    assert merchant_key(raw) == expected


def test_same_merchant_different_store_numbers_collapse():
    assert merchant_key("STARBUCKS #1234") == merchant_key("STARBUCKS #9999")


def test_empty_and_none_safe():
    assert merchant_key("") == ""
    assert merchant_key(None) == ""
