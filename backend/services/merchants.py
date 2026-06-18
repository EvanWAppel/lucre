"""Normalize raw transaction descriptors into a stable merchant key.

The goal is *stability*, not prettiness: the same real-world merchant should map
to the same key across transactions, even as store numbers, cities, phone numbers
and processor prefixes vary. Used by merchant rules and recurring detection.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Payment-processor / network prefixes that precede the real merchant name.
_PREFIX = re.compile(
    r"^(sq|tst|tstx|pp|pypl|paypal|pos|ach|chkcard|pmnt|dd|ec)\s*\*\s*",
    re.IGNORECASE,
)
_PHONE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_STORE_NUM = re.compile(r"#\s*\d+")
_TLD = re.compile(r"\.(com|net|org|co|io)\b", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# A trailing token is noise if it's all digits (store/ref number) or a 2-letter
# state/country code (CA, NY, US).
_TRAILING_NOISE = re.compile(r"^(\d+|[a-z]{2})$")


def merchant_key(raw: str | None) -> str:
    if not raw:
        return ""

    s = raw.lower()
    s = _PREFIX.sub("", s)
    s = s.split("*", 1)[0]  # drop trailing transaction id after '*'
    s = _PHONE.sub(" ", s)
    s = _STORE_NUM.sub(" ", s)
    s = _TLD.sub(" ", s)
    s = _NON_ALNUM.sub(" ", s).strip()

    tokens = s.split()
    while len(tokens) > 1 and _TRAILING_NOISE.match(tokens[-1]):
        tokens.pop()

    return " ".join(tokens)
